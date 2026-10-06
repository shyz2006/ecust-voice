"""
Flask Blueprint：/pulse 页面与接口

深度分析耗时 1~3 分钟，采用"提交任务 + 轮询进度"而不是长连接，
以兼容反向代理 / CDN 的超时限制。
"""

import json
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, send_from_directory, session

from . import pipeline, storage
from .agents import analysis_options, router, workflows, workers
from .agents.orchestrator import Orchestrator

pulse_bp = Blueprint("campus_pulse", __name__)
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_jobs = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 50
_MAX_CONCURRENT = 3


def _username() -> str:
    """登录账号来自主应用的 Flask 会话（nginx 已校验登录），未登录的本地调试记为空。"""
    try:
        return str(session.get("username") or "")
    except Exception:
        return ""


@pulse_bp.route("")
def pulse_redirect():
    return redirect(request.path + "/")


@pulse_bp.route("/")
def pulse_page():
    return send_from_directory(_TEMPLATE_DIR, "pulse.html")


@pulse_bp.route("/api/status")
def api_status():
    return jsonify({"success": True, **pipeline.status()})


@pulse_bp.route("/api/topics")
def api_topics():
    return jsonify({"success": True, **storage.latest_topics("public")})


@pulse_bp.route("/api/meme-trends")
def api_meme_trends():
    """梗 / 短视频玩法候选（含扩散时间线与视频剪辑风格统计）。"""
    return jsonify({"success": True, **storage.latest_topics("meme")})


@pulse_bp.route("/api/campus")
def api_campus():
    blob = storage.kv_get("campus_voice")
    return jsonify({"success": True, "voice": json.loads(blob) if blob else None,
                    "circles": pipeline.get_circles(), "forums": pipeline.get_forums()})


@pulse_bp.route("/api/campus/posts")
def api_campus_posts():
    from . import campus

    theme = str(request.args.get("theme", "")).strip()[:30]
    if not theme:
        return jsonify({"success": False, "message": "缺少主题"}), 400
    return jsonify({"success": True, **campus.theme_posts(theme, int(time.time()))})


@pulse_bp.route("/api/plans/<int:plan_id>/export")
def export_activity_plan(plan_id: int):
    if plan_id not in (0, 1, 2):
        return jsonify({"success": False, "message": "方案不存在"}), 404
    return send_from_directory(
        Path(__file__).resolve().parent / "activity_plans", f"{plan_id}.md",
        as_attachment=True, download_name=f"心育活动方案摘要-{plan_id + 1}.md",
        mimetype="text/markdown",
    )


@pulse_bp.route("/api/meme-feedback", methods=["POST"])
def api_meme_feedback():
    """梗候选人工快捷标注：确认流行 / 不是梗 / 过时词 / 普通词 / 重复候选；用于过滤与精筛提示。"""
    from . import memes

    body = request.get_json(silent=True) or {}
    key, label = str(body.get("key", ""))[:120], body.get("label")
    if not key or label not in memes.FEEDBACK_LABELS and label != "clear":
        return jsonify({"success": False, "message": "参数错误"}), 400
    if label == "clear":
        with storage.connect() as conn:
            conn.execute("DELETE FROM kv WHERE key=?", ("memefb:" + key,))
        return jsonify({"success": True})
    storage.kv_set("memefb:" + key, json.dumps({"label": label, "by": _username(), "ts": int(time.time())},
                                                ensure_ascii=False).encode("utf-8"))
    return jsonify({"success": True, "label": label, "label_text": memes.FEEDBACK_LABELS[label]})


@pulse_bp.route("/api/metrics")
def api_metrics():
    """运行监控：最近批次各阶段耗时、模型调用 / token / 失败、缓存命中率；分析任务成本。"""
    from . import metrics

    batches = storage.recent_batches(30)
    costs = storage.analysis_costs(100)
    by_intent: dict = {}
    for c in costs:
        if c["tokens"] is None:
            continue
        d = by_intent.setdefault(c["intent"] or "?", {"n": 0, "tokens": 0, "seconds": 0.0})
        d["n"] += 1
        d["tokens"] += c["tokens"] or 0
        d["seconds"] += c["seconds"] or 0
    for d in by_intent.values():
        d["avg_tokens"] = round(d["tokens"] / d["n"])
        d["avg_seconds"] = round(d["seconds"] / d["n"], 1)
    return jsonify({"success": True, "batches": batches, "analysis_by_intent": by_intent,
                    "process": metrics.snapshot()})


# ------------------------------------------------------------------ 匿名投票
# 老师端（需登录）：/pulse/api/polls*；学生端（免登录，nginx 单独放行）：/pulse/poll/<token>*
import hashlib as _hashlib
import secrets as _secrets
from collections import deque as _deque

_POLL_TOKEN_RE = __import__("re").compile(r"^[A-Za-z0-9_-]{12,32}$")
_vote_rate: dict = {}
_VOTE_LIMIT_PER_HOUR = 20


@pulse_bp.route("/api/polls", methods=["GET", "POST"])
def api_polls():
    if request.method == "GET":
        return jsonify({"success": True, "polls": storage.list_polls()})
    body = request.get_json(silent=True) or {}
    keys = [str(k)[:120] for k in (body.get("keys") or [])][:8]
    meme = {t["key"]: t for t in storage.latest_topics("meme")["topics"]}
    items = [{"key": k, "label": meme[k]["label"].split("：", 1)[-1].lstrip("#")[:30],
              "meaning": ((meme[k].get("lens") or {}).get("meaning") or "")[:60]} for k in keys if k in meme]
    if not items:
        return jsonify({"success": False, "message": "请至少选择一个候选"}), 400
    token = _secrets.token_urlsafe(12)
    title = str(body.get("title") or "你最近在网上见过这些梗 / 玩法吗？")[:60]
    storage.create_poll(token, title, items, _username(), days=int(body.get("days") or 14))
    return jsonify({"success": True, "token": token, "path": f"poll/{token}"})


@pulse_bp.route("/api/polls/<token>/close", methods=["POST"])
def api_poll_close(token: str):
    storage.close_poll(token)
    return jsonify({"success": True})


def _public_poll(token: str):
    if not _POLL_TOKEN_RE.match(token or ""):
        return None
    poll = storage.get_poll(token)
    return poll if poll else None


@pulse_bp.route("/poll/<token>")
def poll_page(token: str):
    if not _public_poll(token):
        return "投票不存在", 404
    resp = send_from_directory(_TEMPLATE_DIR, "poll.html")
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Robots-Tag"] = "noindex"
    if not request.cookies.get("pulse_voter"):
        resp.set_cookie("pulse_voter", _secrets.token_hex(16), max_age=365 * 86400, httponly=True,
                        samesite="Lax", secure=request.headers.get("X-Forwarded-Proto") == "https",
                        path=request.path.rsplit("/poll/", 1)[0] + "/poll/")
    return resp


@pulse_bp.route("/poll/<token>/data")
def poll_data(token: str):
    poll = _public_poll(token)
    if not poll:
        return jsonify({"success": False, "message": "投票不存在"}), 404
    # 只返回题目本身，不返回结果、创建者或任何系统数据
    return jsonify({"success": True, "title": poll["title"], "open": poll["open"],
                    "items": [{"key": i["key"], "label": i["label"], "meaning": i["meaning"]} for i in poll["items"]]})


@pulse_bp.route("/poll/<token>/vote", methods=["POST"])
def poll_vote(token: str):
    poll = _public_poll(token)
    if not poll or not poll["open"]:
        return jsonify({"success": False, "message": "投票已结束或不存在"}), 400
    ip = request.headers.get("X-Real-IP") or request.remote_addr or "?"
    now = time.time()
    q = _vote_rate.setdefault(ip, _deque())  # 仅内存计数，不落库
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= _VOTE_LIMIT_PER_HOUR:
        return jsonify({"success": False, "message": "提交过于频繁，请稍后再试"}), 429
    cookie = request.cookies.get("pulse_voter")
    if not cookie or len(cookie) > 64:
        return jsonify({"success": False, "message": "请刷新页面后再提交"}), 400
    body = request.get_json(silent=True) or {}
    valid = {i["key"] for i in poll["items"]}
    answers = {}
    for key, a in (body.get("answers") or {}).items():
        if key in valid and isinstance(a, dict):
            try:
                seen = max(0, min(2, int(a.get("seen", 0) or 0)))
            except (TypeError, ValueError):
                continue
            answers[key] = {"seen": seen, "follow": bool(a.get("follow"))}
    if not answers:
        return jsonify({"success": False, "message": "请至少回答一题"}), 400
    q.append(now)
    voter = _hashlib.sha256((cookie + token).encode()).hexdigest()[:32]
    if not storage.add_vote(token, voter, answers):
        return jsonify({"success": False, "message": "你已经提交过了，谢谢！"}), 409
    return jsonify({"success": True, "message": "提交成功，谢谢参与！"})


@pulse_bp.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        body = request.get_json(silent=True) or {}
        ids = pipeline.set_circles(str(body.get("circles", "")))
        forums = pipeline.set_forums(str(body.get("forums", "")))
        return jsonify({"success": True, "circles": ids, "forums": forums,
                        "message": f"已保存：狐友圈子 {len(ids)} 个，贴吧 {len(forums)} 个（{'、'.join(forums) or '无'}），下次采集生效"})
    return jsonify({"success": True, "circles": pipeline.get_circles(), "forums": pipeline.get_forums()})


@pulse_bp.route("/api/topic/<int:topic_id>/history")
def api_topic_history(topic_id: int):
    topic = storage.get_topic(topic_id)
    if not topic:
        return jsonify({"success": False, "message": "话题不存在"}), 404
    since = int(time.time()) - 3 * 86400
    history = storage.title_history(topic.get("titles", [])[:8], since)
    return jsonify({"success": True, "topic": topic, "history": history})


@pulse_bp.route("/api/collect", methods=["POST"])
def api_collect():
    if pipeline.status()["running"]:
        return jsonify({"success": False, "message": "采集正在进行中"})
    threading.Thread(target=pipeline.run_once, daemon=True).start()
    return jsonify({"success": True, "message": "已开始采集，约 30~90 秒后刷新"})


@pulse_bp.route("/api/route", methods=["POST"])
def api_route():
    query = (request.get_json(silent=True) or {}).get("query", "").strip()
    return jsonify({"success": True, "profile": router.route(query).as_dict()})


@pulse_bp.route("/api/analyze", methods=["POST"])
def api_analyze():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify(success=False, message='任务参数格式不正确'), 400
    try:
        options = analysis_options.normalize(body.get('analysis_options'))
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400
    query = str(body.get("query", "")).strip()[:200]
    if not query:
        return jsonify({"success": False, "message": "请输入问题"}), 400
    with _jobs_lock:
        running = sum(1 for j in _jobs.values() if j["status"] == "running")
        if running >= _MAX_CONCURRENT:
            return jsonify({"success": False, "message": "当前分析任务较多，请稍后再试"}), 429
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "query": query, "status": "running", "trace": [], "result": None,
               "error": None, "created": time.time()}
        _jobs[job_id] = job
        for old in sorted(_jobs.values(), key=lambda j: j["created"])[:-_MAX_JOBS]:
            _jobs.pop(old["id"], None)

    def work():
        try:
            orch = Orchestrator(on_event=lambda step: job["trace"].append(step))
            job["result"] = orch.run(query, body.get("intent"), body.get("workflow"), analysis_options=options)
            job["status"] = "done"
        except Exception as exc:
            job["error"] = str(exc)
            job["status"] = "error"

    threading.Thread(target=work, name=f"pulse-job-{job_id}", daemon=True).start()
    return jsonify({"success": True, "job_id": job_id})


@pulse_bp.route("/api/job/<job_id>")
def api_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return jsonify({"success": False, "message": "任务不存在或已过期"}), 404
    return jsonify({"success": True, **{k: job[k] for k in ("id", "query", "status", "trace", "result", "error")}})


@pulse_bp.route("/api/analyses")
def api_analyses():
    return jsonify({"success": True, "items": storage.recent_analyses()})


@pulse_bp.route("/api/analysis/<int:analysis_id>")
def api_analysis(analysis_id: int):
    row = storage.get_analysis(analysis_id)
    if not row:
        return jsonify({"success": False, "message": "记录不存在"}), 404
    payload = row["payload"]
    payload["id"] = row["id"]
    payload["feedback"] = storage.feedback_summary(analysis_id, _username())
    payload["status"] = row.get("status") or payload.get("status") or "formal"
    return jsonify({"success": True, "result": payload, "query": row["query"], "generated_at":row['ts']})


@pulse_bp.route("/api/review", methods=["POST"])
def api_review():
    """教师复核：待复核草稿 / AI 验证稿 → 教师已复核（活动方案可执行，写入梗词典）或驳回。"""
    body = request.get_json(silent=True) or {}
    decision = body.get("decision")
    try:
        analysis_id = int(body["analysis_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"success": False, "message": "参数错误"}), 400
    if decision not in ("approve", "reject"):
        return jsonify({"success": False, "message": "参数错误"}), 400
    payload = storage.review_analysis(analysis_id, decision, _username(), str(body.get("note") or ""))
    if payload is None:
        return jsonify({"success": False, "message": "该结果已复核或不可复核"}), 400
    if decision == "approve":
        workers.remember_memes(payload.get("result") or {})
    return jsonify({"success": True, "status": payload["status"]})


@pulse_bp.route("/api/feedback", methods=["POST"])
def api_feedback():
    body = request.get_json(silent=True) or {}
    try:
        analysis_id = int(body["analysis_id"])
        rating = int(body["rating"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"success": False, "message": "参数错误"}), 400
    row = storage.get_analysis(analysis_id)
    if not 1 <= rating <= 5 or not row:
        return jsonify({"success": False, "message": "参数错误"}), 400
    if row.get("status") not in ("formal", "approved"):
        return jsonify({"success": False, "message": "草稿或降级结果不参与评分，请先完成人工复核"}), 400
    user = _username()
    storage.save_feedback(analysis_id, rating, str(body.get("comment") or "")[:500], user)
    return jsonify({"success": True, "feedback": storage.feedback_summary(analysis_id, user)})


@pulse_bp.route("/api/workflows")
def api_workflows():
    return jsonify({"success": True, "items": workflows.leaderboard()})


@pulse_bp.route("/api/memes")
def api_memes():
    items = []
    for row in storage.kv_prefix("meme:"):
        try:
            items.append({"term": row["key"], **json.loads(row["value"])})
        except (TypeError, ValueError):
            continue
    return jsonify({"success": True, "items": items})


def init_campus_pulse(app, url_prefix: str = "/pulse") -> None:
    # 启动即初始化台账与调度日期锚点，不以首次打开网页的时间决定周期。
    with storage.connect():
        pass
    app.register_blueprint(pulse_bp, url_prefix=url_prefix)
    pipeline.start_scheduler()
    from . import auto_reports
    auto_reports.start_scheduler()


@pulse_bp.route('/api/observatory')
def api_observatory():
    from . import observatory
    data = observatory.snapshot()
    return jsonify({k:v for k,v in data.items() if k != 'posts'})


@pulse_bp.route('/api/observatory/posts')
def api_observatory_posts():
    from . import observatory
    data = observatory.snapshot()
    posts = data['posts']
    source = request.args.get('source','all')
    if source not in ('all',*observatory.SOURCES):
        return jsonify(success=False,message='无效来源'),400
    if source != 'all':
        posts = [p for p in posts if p['source'] == source]
    theme = request.args.get('theme','')[:30]
    if theme:
        posts = [p for p in posts if p['theme'] == theme]
    try:
        start = int(request.args['from']) if 'from' in request.args else None
        end = int(request.args['until']) if 'until' in request.args else None
    except (ValueError, TypeError):
        return jsonify(success=False,message='无效时间窗口'),400
    if start is not None and end is not None and start >= end:
        return jsonify(success=False,message='时间窗口起点必须早于终点'),400
    if start is not None:
        posts = [p for p in posts if p['published'] >= start]
    if end is not None:
        posts = [p for p in posts if p['published'] < end]
    if request.args.get('red') == '1':
        ids = set(data['red']['post_ids'])
        posts = [p for p in posts if p['id'] in ids]
    meme = request.args.get('meme','')[:40]
    if meme:
        ids = next((set(m['post_ids']) for m in data['memes']+data.get('meme_candidates',[]) if m['term'] == meme),set())
        posts = [p for p in posts if p['id'] in ids]
    sort = request.args.get('sort','heat')
    if sort not in ('heat','newest'):
        return jsonify(success=False,message='无效排序'),400
    if sort == 'newest':
        posts = sorted(posts,key=lambda p:-p['published'])
    return jsonify(success=True,posts=posts,total=len(posts),window_days=10,generated_at=data['generated_at'])


@pulse_bp.route('/api/dashboard')
def api_dashboard():
    from . import telemetry,auto_reports
    return jsonify({**telemetry.dashboard(),'schedule':auto_reports.scheduler_status()})


@pulse_bp.route('/api/auto-reports')
def api_auto_reports():
    from . import auto_reports
    return jsonify(success=True,items=auto_reports.recent(),schedule=auto_reports.scheduler_status())


@pulse_bp.route('/api/auto-reports/<int:report_id>')
def api_auto_report(report_id):
    from . import auto_reports
    row = auto_reports.get(report_id)
    return (jsonify(success=True,item=row) if row else (jsonify(success=False,message='报告不存在'),404))


@pulse_bp.route('/api/auto-reports/<int:report_id>/export')
def api_auto_report_export(report_id):
    from . import auto_reports
    from flask import Response
    row = auto_reports.get(report_id)
    if not row or row['status'] != 'complete' or not row['payload']:
        return jsonify(success=False,message='报告未完成或不存在'),404
    return Response(auto_reports.markdown(row),content_type='text/markdown; charset=utf-8',
                    headers={'Content-Disposition':f'attachment; filename="campus-report-{report_id}.md"'})

@pulse_bp.route('/api/cost-pricing', methods=['GET','POST'])
def api_cost_pricing():
    from . import costs
    if request.method == 'POST':
        if not request.is_json:
            return jsonify(success=False,message='请使用JSON提交计价设置'),400
        try:
            pricing = costs.save(request.get_json(silent=True))
        except ValueError as e:
            return jsonify(success=False,message=str(e)),400
        return jsonify(success=True,pricing=pricing)
    with storage.connect() as conn:
        return jsonify(success=True,pricing=costs.read(conn))
