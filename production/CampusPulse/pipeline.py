"""
感知层流水线（常驻、低成本）

每个批次分两阶段提交，保证“看到的话题”与“最新数据”的关系始终可解释：
  1. 抓取阶段：公开热榜 + 狐友（本校圈 / 全国推荐）+ B 站热门 → 快照与批次记录一起落库（status=fetched）
  2. 分析阶段：公开话题聚类与标注、梗/玩法发现（近 24 小时窗口）、本校声音聚合、加速度草图更新
     → 话题、草图、梗信号、本校声音与 status=complete 在同一事务提交
进程在两阶段之间中断时，重启后会自动补做最新的未完成批次；状态栏分别展示“最近抓取”和
“最近完整分析”，二者不一致时告警。

LLM 只用于标注新出现的话题 / 帖子，且全部按内容缓存。梗候选发现与排序使用语料统计。
"""

import json
import re
import threading
import time
from typing import Dict, List, Optional

from loguru import logger

from . import campus, collectors, lens, memes, metrics, storage, transitions, video_features
from .burst import AccelerationSketch, batch_observations
from .config import settings
from .sources import bilibili, huyou, tieba
from .topics import build_topics

_run_lock = threading.Lock()
_state: Dict = {"running": False, "stage": None, "last_error": None, "enriching": None}

FORUM_SOURCES = ["huyou-school", "huyou-national", "tieba-school"]
UGC_SOURCES = ["bilibili-popular", *FORUM_SOURCES]


# ------------------------------------------------------------------ 设置（页面可改，无需重启）

def get_circles() -> List[str]:
    blob = storage.kv_get("config:huyou_circles")
    if blob:
        return json.loads(blob)
    return settings.huyou_circles


def set_circles(raw: str) -> List[str]:
    ids = re.findall(r"(?:circle/|circleId=|id=)?(\d{12,20})", raw or "")
    ids = list(dict.fromkeys(ids))[:5]
    storage.kv_set("config:huyou_circles", json.dumps(ids).encode("utf-8"))
    return ids


def get_forums() -> List[str]:
    blob = storage.kv_get("config:tieba_forums")
    if blob:
        return json.loads(blob)
    return settings.tieba_forums


def set_forums(raw: str) -> List[str]:
    """接受吧名或贴吧链接（kw 参数可能被多次 URL 编码）。"""
    from urllib.parse import unquote

    names = []
    for part in re.split(r"[\s,，]+", raw or ""):
        if not part:
            continue
        m = re.search(r"kw=([^&]+)", part)
        name = m.group(1) if m else part
        for _ in range(3):
            name = unquote(name)
        name = name.strip().removesuffix("吧")
        if name and len(name) <= 30:
            names.append(name)
    names = list(dict.fromkeys(names))[:3]
    storage.kv_set("config:tieba_forums", json.dumps(names, ensure_ascii=False).encode("utf-8"))
    return names


# ------------------------------------------------------------------ 抓取

def _fetch_all() -> Dict:
    batch = collectors.collect_hotlists()
    items, errors, meta = list(batch["items"]), dict(batch["errors"]), {}
    if settings.huyou_enabled:
        try:
            hy = huyou.collect(get_circles(), include_recommend=True)
            items += hy["items"]
            errors.update(hy["errors"])
            meta["circles"] = hy["circles"]
        except Exception as exc:
            errors["huyou"] = str(exc)[:200]
    forums = get_forums()
    if forums:
        try:
            tb = tieba.collect(forums)
            items += tb["items"]
            errors.update(tb["errors"])
        except Exception as exc:
            errors["tieba"] = str(exc)[:200]
    if settings.bilibili_enabled:
        try:
            bl = bilibili.collect()
            items += bl["items"]
            errors.update(bl["errors"])
        except Exception as exc:
            errors["bilibili"] = str(exc)[:200]
    return {"batch_ts": batch["batch_ts"], "items": items, "errors": errors, "meta": meta}


# ------------------------------------------------------------------ 分析

def _build_views(batch_ts: int, items: List[Dict], use_llm: bool, sketch: AccelerationSketch) -> Dict:
    """从一个批次的条目构建页面视图（公开话题、梗与玩法、本校声音）。use_llm=False 时只用规则与缓存。"""
    public = [i for i in items if i["source"] not in FORUM_SOURCES]
    if not any(i["source"] in settings.sources for i in public):
        # 公开热榜源全部失败（如 newsnow 故障）：沿用上一批的公开话题并标注来源时间，避免雷达只剩 B 站内容
        prev = storage.latest_topics("public")
        topics = [{**t, "stale_from": t.get("stale_from") or prev["batch_ts"]} for t in prev["topics"]]
        for t in topics:
            t.pop("id", None)
    else:
        topics = build_topics(public, sketch, storage.previous_batch_titles(batch_ts))
        topics = lens.annotate_topics(topics, use_llm=use_llm)
        for t in topics:
            t["scope"] = "public"
            t["campus_score"] = round(lens.campus_score(t), 4)
        topics.sort(key=lambda t: -t["campus_score"])

    # 梗 / 玩法发现：近 24 小时的用户生成内容，样本量足够才有统计意义
    window = storage.recent_items(UGC_SOURCES, batch_ts - 86400)
    seen, ugc = set(), []
    for it in [*window, *[i for i in items if i["source"] in UGC_SOURCES]]:
        key = (it["source"], it["title"])
        if key not in seen:
            seen.add(key)
            ugc.append(it)
    videos = [i.get("extra") or {} for i in items if i["source"] == "bilibili-popular"]
    vfeat = {v["bvid"]: video_features.cached(v["bvid"]) for v in videos if v.get("bvid")}
    vfeat = {k: v for k, v in vfeat.items() if v}
    feedback = memes.feedback_map()
    cands = memes.discover(ugc, vfeat, feedback)
    cands += transitions.template_candidates(videos)
    # 校园梗榜改为真实语料统计：停止模型检索召回与模型精筛，避免把AI词典当作流行证据。
    web = []
    labels = {c["label"] for c in cands}
    cands += [w for w in web if w["label"] not in labels
              and (feedback.get(w["key"]) or {}).get("label") not in memes._BLOCK_LABELS]
    history = storage.meme_history([c["key"] for c in cands], batch_ts - 3 * 86400, before_ts=batch_ts)
    memes.attach_history(cands, history, batch_ts, feedback)
    cands.sort(key=lambda c: -c["score"])
    shown = cands[:60]
    meme_topics = []
    for c in shown[:40]:
        c["scope"] = "meme"
        meme_topics.append(c)
    voice = campus.summarize(batch_ts, use_llm)
    return {"topics": topics, "meme_topics": meme_topics, "cands": cands, "voice": voice,
            "videos": videos, "vfeat": vfeat}


def analyze_batch(batch_ts: int, items: List[Dict], use_llm: bool = True) -> Dict:
    """阶段 2（快速）：只用规则与缓存完成分析并原子提交；模型标注交给独立的增强队列。"""
    started = time.time()
    sketch = AccelerationSketch.load()
    if not (sketch.last_ts and batch_ts <= sketch.last_ts):  # 同一批次重复分析时不重复计入
        public = [i for i in items if i["source"] not in FORUM_SOURCES]
        sketch.update(batch_observations(public), batch_ts, max(300, settings.collect_interval_min * 60))
    before = metrics.snapshot()
    views = _build_views(batch_ts, items, use_llm=False, sketch=sketch)
    stats = {
        "items": len(items),
        "by_source": {s: sum(1 for i in items if i["source"] == s) for s in sorted({i["source"] for i in items})},
        "topics": len(views["topics"]),
        "meme_candidates": len(views["cands"]),
        "meme_shown": len(views["meme_topics"]),
        "school_posts_7d": views["voice"]["school_posts"],
        "videos_analyzed": len(views["vfeat"]),
        "sketch_batches": sketch.n_batches,
        "analyze_seconds": round(time.time() - started, 1),
        "seconds": round(time.time() - started, 1),
        "enriched": False,
        **{"analyze_" + k: v for k, v in metrics.summarize_delta(metrics.delta(before)).items()},
    }
    storage.commit_analysis(
        batch_ts, views["topics"] + views["meme_topics"],
        {AccelerationSketch.KEY: sketch.dumps(),
         "campus_voice": json.dumps(views["voice"], ensure_ascii=False).encode("utf-8")},
        stats, meme_rows=views["cands"])
    if settings.video_analysis_enabled:
        video_features.enqueue(views["videos"], limit=settings.video_per_batch)
    storage.prune()
    if use_llm and settings.llm_ready:
        start_enrichment(batch_ts, items)
    return stats


# ------------------------------------------------------------------ 模型增强队列（独立线程）
_enrich_lock = threading.Lock()


def enrich_batch(batch_ts: int, items: List[Dict]) -> Dict:
    """阶段 3：对新内容做模型标注（缓存命中的直接复用），然后原子刷新该批次的视图。"""
    started = time.time()
    before = metrics.snapshot()
    sketch = AccelerationSketch.load()  # 已包含本批次，不再推进
    views = _build_views(batch_ts, items, use_llm=True, sketch=sketch)
    enrich = {"enrich_seconds": round(time.time() - started, 1),
              **{"enrich_" + k: v for k, v in metrics.summarize_delta(metrics.delta(before)).items()}}
    ok = storage.refresh_views(
        batch_ts, views["topics"] + views["meme_topics"],
        {"campus_voice": json.dumps(views["voice"], ensure_ascii=False).encode("utf-8")},
        {"enriched": True, "meme_shown": len(views["meme_topics"]), **enrich})
    if not ok:
        logger.info(f"[CampusPulse] 批次 {batch_ts} 已被更新的批次取代，放弃增强结果")
    return enrich


def start_enrichment(batch_ts: int, items: List[Dict]) -> None:
    def work():
        if not _enrich_lock.acquire(blocking=False):
            return  # 上一批次仍在增强：跳过本批，由下一批次统一补标注（缓存保证不重复）
        _state["enriching"] = batch_ts
        try:
            enrich_batch(batch_ts, items)
        except Exception as exc:
            logger.exception(f"[CampusPulse] 模型增强失败: {exc}")
            _state["last_error"] = f"模型增强失败：{str(exc)[:200]}"
        finally:
            _state["enriching"] = None
            _enrich_lock.release()

    threading.Thread(target=work, name=f"pulse-enrich-{batch_ts}", daemon=True).start()


def run_once(use_llm: bool = True) -> Dict:
    if not _run_lock.acquire(blocking=False):
        return {"skipped": True, "reason": "已有采集任务在运行"}
    _state.update(running=True, stage="抓取中", last_error=None)
    batch_ts = None
    try:
        t0 = time.time()
        fetched = _fetch_all()
        fetched["meta"]["fetch_seconds"] = round(time.time() - t0, 1)
        if not fetched["items"]:
            raise RuntimeError(f"所有数据源均获取失败: {fetched['errors']}")
        batch_ts = fetched["batch_ts"]
        storage.record_fetch(batch_ts, fetched["items"],
                             {"items": len(fetched["items"]), "errors": fetched["errors"],
                              "fetch_seconds": round(time.time() - t0, 1), **fetched["meta"]})
        _state["stage"] = "分析中"
        stats = analyze_batch(batch_ts, fetched["items"], use_llm)
        stats["errors"] = fetched["errors"]
        stats["fetch_seconds"] = fetched["meta"]["fetch_seconds"]
        return stats
    except Exception as exc:
        logger.exception(f"[CampusPulse] 流水线失败: {exc}")
        _state["last_error"] = str(exc)[:300]
        if batch_ts:
            storage.mark_batch_failed(batch_ts, str(exc))
        return {"error": str(exc)}
    finally:
        _state.update(running=False, stage=None)
        _run_lock.release()


def recover_pending() -> Optional[Dict]:
    """启动时补做最新的“已抓取未完成”批次（例如分析阶段进程被重启）。"""
    latest = storage.latest_batch()
    complete = storage.latest_batch("complete")
    if not latest or latest["status"] not in ("fetched", "failed"):
        return None
    if complete and complete["batch_ts"] >= latest["batch_ts"]:
        return None
    if time.time() - latest["batch_ts"] > 3 * max(settings.collect_interval_min, 10) * 60:
        return None  # 太旧的批次不再补做，等待下一次正常采集
    if not _run_lock.acquire(blocking=False):
        return None
    _state.update(running=True, stage="补做未完成批次")
    try:
        items = storage.load_batch_items(latest["batch_ts"])
        logger.info(f"[CampusPulse] 补做未完成批次 {latest['batch_ts']}（{len(items)} 条）")
        return analyze_batch(latest["batch_ts"], items)
    except Exception as exc:
        storage.mark_batch_failed(latest["batch_ts"], str(exc))
        _state["last_error"] = str(exc)[:300]
        return {"error": str(exc)}
    finally:
        _state.update(running=False, stage=None)
        _run_lock.release()


def _fmt(ts: int) -> str:
    """北京时间（容器时区为 UTC）。"""
    return time.strftime("%m-%d %H:%M", time.gmtime(ts + 8 * 3600))


def status() -> Dict:
    fetch = storage.latest_batch()
    complete = storage.latest_batch("complete")
    lagging = bool(fetch and (not complete or fetch["batch_ts"] != complete["batch_ts"]))
    alert = None
    if lagging and not _state["running"]:
        alert = (f"最新抓取的数据（{_fmt(fetch['batch_ts'])}）"
                 f"尚未完成分析，页面展示的是上一个完整批次"
                 + (f"：{fetch.get('error')}" if fetch.get("error") else ""))
    errors = ((complete or {}).get("stats") or {}).get("errors") or {}
    failed_hot = [s for s in settings.sources if s in errors]
    if not alert and failed_hot:
        alert = (f"公开热榜源异常：{len(failed_hot)}/{len(settings.sources)} 个获取失败（第三方聚合服务 newsnow）"
                 + ("，热点雷达沿用上一批数据" if len(failed_hot) == len(settings.sources) else ""))
    return {
        "source_errors": errors,
        "running": _state["running"],
        "stage": _state["stage"],
        "enriching": bool(_state.get("enriching")),
        "last_error": _state["last_error"],
        "last_fetch": fetch["batch_ts"] if fetch else None,
        "last_fetch_status": fetch["status"] if fetch else None,
        "last_complete": complete["batch_ts"] if complete else None,
        "last_complete_stats": complete["stats"] if complete else None,
        "lagging": lagging,
        "alert": alert,
        "interval_min": settings.collect_interval_min,
        "llm_ready": settings.llm_ready,
        "search_ready": settings.search_ready,
        "search_tool": settings.search_tool,
        "huyou_circles": get_circles(),
        "tieba_forums": get_forums(),
        "video_queue": video_features.queue_size(),
    }


_scheduler: Optional[threading.Thread] = None


def start_scheduler() -> None:
    """在 Flask 进程内启动后台采集线程（守护线程，随主进程退出）。"""
    global _scheduler
    if settings.collect_interval_min <= 0 or (_scheduler and _scheduler.is_alive()):
        return

    def loop():
        time.sleep(20)  # 等待主应用完成启动
        try:
            recover_pending()
        except Exception as exc:
            logger.warning(f"[CampusPulse] 补做批次失败: {exc}")
        while True:
            latest = storage.latest_batch()
            last = latest["fetched_at"] if latest else 0
            if time.time() - last >= settings.collect_interval_min * 60 - 30:
                run_once()
            time.sleep(60)

    _scheduler = threading.Thread(target=loop, name="campus-pulse-scheduler", daemon=True)
    _scheduler.start()
    logger.info(f"[CampusPulse] 后台热点雷达已启动，间隔 {settings.collect_interval_min} 分钟")
