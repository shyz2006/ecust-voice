"""
CampusPulse 离线测试：用假 LLM / 假搜索验证感知层与编排层的控制流。

运行：PULSE_DB_PATH=/tmp/pulse_test.db python -m pytest CampusPulse/tests -q
"""

import os
import tempfile
import time

os.environ.setdefault("PULSE_DB_PATH", os.path.join(tempfile.mkdtemp(), "pulse_test.db"))
os.environ.setdefault("PULSE_LLM_API_KEY", "test")
os.environ.setdefault("PULSE_LLM_MODEL_NAME", "fake")
os.environ.setdefault("BOCHA_WEB_SEARCH_API_KEY", "test")

import pytest

from CampusPulse import burst, llm, memes, search, storage
from CampusPulse.agents import orchestrator, router, verifier, workers, workflows
from CampusPulse.topics import build_topics


def _items(titles, source="weibo"):
    return [{"source": source, "rank": i + 1, "title": t} for i, t in enumerate(titles)]


def test_router_topologies():
    assert router.route("哈基米是什么梗").topology == "SAS"
    assert router.route("最近大学生在关注什么热点").topology == "Centralized"
    assert router.route("借班味策划一次减压活动").intent == "activity_design"
    assert router.route("对某高校事件做全网舆情深度分析").topology == "Escalate"
    assert router.route("某地发生地震").topology == "Adaptive"


def test_sketch_detects_acceleration():
    sk = burst.AccelerationSketch()
    t = 1_700_000_000
    steady = {"考研": 1.0, "天气": 1.0}
    for i in range(24):  # 12 小时稳定出现
        sk.update(steady, t + i * 1800)
    sk.update({**steady, "班味": 3.0}, t + 24 * 1800)
    assert sk.burst_score("班味") > sk.burst_score("考研") + 1
    assert abs(sk.burst_score("考研")) < 1.0


def test_clustering_merges_cross_platform_titles():
    items = _items(["王楚钦3比2林昀儒夺冠", "今天天气不错"]) + \
        _items(["实拍王楚钦3比2林昀儒后庆祝", "考研报名开始"], source="douyin")
    topics = build_topics(items, burst.AccelerationSketch())
    wang = [t for t in topics if "王楚钦" in t["label"]]
    assert len(wang) == 1 and set(wang[0]["sources"]) == {"weibo", "douyin"}
    assert topics[0] is wang[0]  # 跨平台扩散的话题排在最前


def test_verifier_flags_fabricated_evidence_and_missing_crisis_guide():
    pool = workers.EvidencePool()
    pool.add("W", {"title": "某校学生轻生事件", "url": "u1", "snippet": "..."})
    result = {
        "summary": "某事件引发关注",
        "topics": [{"name": "某事件", "why_students_care": "共鸣", "evidence": ["W1", "W9"], "risk": "重点"}],
        "activities": [],
    }
    v = verifier.verify("某事件", "event_brief", result, pool, [], use_judge=False)
    assert not v["passed"]
    joined = " ".join(v["issues"])
    assert "W9" in joined and "危机干预" in joined


class FakeLLM:
    """按调用内容返回预设 JSON；第一版草稿故意缺证据，用来触发修订。"""

    def __init__(self):
        self.calls = []

    def __call__(self, system, user, temperature=0.2, meter=None, **kw):
        self.calls.append(user[:40])
        if meter:
            meter.add(None, 0.01)
        if "建立任务账本" in user:
            return {"keywords": ["班味"], "search_queries": ["班味 梗 含义"], "facts_to_lookup": ["出处"]}
        if "修正问题" in user:
            return {"summary": "班味指上班后的疲惫气质", "topics": [{
                "name": "班味", "what_happened": "源于社交平台", "why_students_care": "实习焦虑",
                "meme": {"form": "谐音/造词", "function": "自嘲解压", "meaning": "上班后的疲惫感"},
                "evidence": ["W1"]}], "activities": []}
        if "独立完成全部分析" in user:
            return {"summary": "班味指上班后的疲惫气质", "topics": [{
                "name": "班味", "why_students_care": "实习焦虑",
                "meme": {"form": "谐音/造词", "function": "自嘲解压", "meaning": "上班后的疲惫感"},
                "evidence": ["W7"]}]}
        if "独立审稿人" in user:
            return {"groundedness": 4, "usefulness": 4, "issues": []}
        if "逐条判断每个“主张”" in user:
            return [{"i": i, "verdict": "支持", "note": ""} for i in range(1, 20)]
        raise AssertionError("unexpected prompt: " + user[:80])


@pytest.fixture
def fake_env(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "chat_json", fake)
    monkeypatch.setattr(search, "web_search", lambda q, count=8, freshness="oneMonth": [
        {"title": f"{q} 百科", "url": f"https://example.com/{hash(q)}", "site": "example", "date": "", "snippet": "班味是……"}])
    return fake


def test_orchestrator_revises_until_grounded(fake_env):
    out = orchestrator.Orchestrator().run("班味是什么梗", force_workflow="lean_verified")
    agents = [s["agent"] for s in out["trace"]]
    assert agents[:2] == ["Router", "WorkflowSelector"]
    verdicts = [s for s in out["trace"] if s["agent"] == "Verifier"]
    assert len(verdicts) == 2 and verdicts[1]["score"] > verdicts[0]["score"]
    assert out["result"]["topics"][0]["evidence"] == ["W1"]
    assert storage.get_analysis(out["id"]) is not None
    # 通过验证的梗进入记忆
    assert storage.kv_get("meme:班味") is not None


def test_workflow_selector_prefers_rewarded_variant(fake_env):
    for wid, score in [("lean", 0.2), ("lean_verified", 0.9)]:
        for _ in range(4):
            storage.save_analysis("q", wid, "SAS", {}, score)
    picks = [workflows.select(["lean", "lean_verified"])["workflow"].id for _ in range(5)]
    assert picks.count("lean_verified") == 5


def test_orchestrator_degrades_when_llm_down(fake_env, monkeypatch):
    def down(system, user, temperature=0.2, meter=None, **kw):
        if "建立任务账本" in user:
            return {"search_queries": ["哈基米 梗"]}
        raise llm.LLMUnavailable("502")
    monkeypatch.setattr(llm, "chat_json", down)
    before = {r["workflow_id"]: r["n"] for r in storage.workflow_rewards()}
    out = orchestrator.Orchestrator().run("哈基米是什么梗", force_workflow="central_verified")
    assert out["degraded"] and out["reward"] is None
    assert out["evidence"] and "模型服务暂时不可用" in out["result"]["summary"]
    after = {r["workflow_id"]: r["n"] for r in storage.workflow_rewards()}
    assert after.get("central_verified", 0) == before.get("central_verified", 0)


def test_normalize_result_maps_free_text_labels():
    from CampusPulse import lens
    result = {"topics": [{
        "name": "班味",
        "meme": {"form": "以“有班味”“班味很重”等短句、评论、弹幕和社交文案出现。",
                 "function": "主要用于自嘲、调侃同事或朋友。", "meaning": "上班后的疲惫感"},
        "psych_dimensions": ["工作或实习适应压力", "疲惫感与情绪耗竭", "情绪调节"],
    }]}
    t = lens.normalize_result(result)["topics"][0]
    assert t["meme"]["form"] == "句式模板" and t["meme"]["function"] == "自嘲解压"
    assert t["meme"]["form_detail"].startswith("以“有班味”")
    assert t["psych_dimensions"] == ["就业焦虑", "情绪调节"]
    assert "工作或实习适应压力" in t["psych_detail"]


def test_feedback_is_per_teacher_and_overwritable():
    aid = storage.save_analysis("q", "lean", "SAS", {}, 0.8)
    storage.save_feedback(aid, 2, "", "teacher_a")
    storage.save_feedback(aid, 5, "", "teacher_a")  # 改主意：覆盖而不是累加
    storage.save_feedback(aid, 3, "", "teacher_b")
    fb = storage.feedback_summary(aid, "teacher_a")
    assert fb == {"my_rating": 5, "n_ratings": 2, "avg_rating": 4.0}
    assert storage.feedback_summary(aid, "teacher_c")["my_rating"] is None


# ---------------------------------------------------------------- 问题 3：验证门
def test_schema_extracts_ids_from_evidence_sentences_and_flattens_objects():
    from CampusPulse.agents import schema
    r = schema.normalize_output({
        "summary": "s",
        "topics": [{"name": "张展硕夺冠", "why_students_care": "x", "risk": "重点",
                    "evidence": ["[H1] 哔哩哔哩热榜出现……", "[W1][W2] 相关报道", "证据不足：无学生数据"]}],
        "risk_notes": [{"note": "不要神化冠军", "evidence": ["W3"]}],
        "talking_points": [{"text": "你怎么看？"}],
    })
    t = r["topics"][0]
    assert t["evidence"] == ["H1", "W1", "W2"] and len(t["evidence_notes"]) == 3
    assert r["risk_notes"] == ["不要神化冠军 [W3]"] and r["talking_points"] == ["你怎么看？"]
    assert t["crisis_level"] == "无" and t["content_risk"] == "中" and "risk" not in t


def test_failed_verification_becomes_draft_without_reward_or_memory(fake_env, monkeypatch):
    def writer(system, user, temperature=0.2, meter=None, **kw):
        if "建立任务账本" in user:
            return {"search_queries": ["躺平 梗"]}
        # 伪造证据编号 → 硬约束失败，且修订也修不好
        return {"summary": "躺平", "topics": [{"name": "躺平", "why_students_care": "x",
                "meme": {"meaning": "放弃内卷"}, "evidence": ["W99"]}]}
    monkeypatch.setattr(llm, "chat_json", writer)
    before = {r["workflow_id"]: r["n"] for r in storage.workflow_rewards()}
    out = orchestrator.Orchestrator().run("躺平是什么梗", force_workflow="lean_verified")
    assert out["status"] == "draft" and out["reward"] is None
    assert storage.kv_get("meme:躺平") is None
    assert {r["workflow_id"]: r["n"] for r in storage.workflow_rewards()} == before
    row = storage.get_analysis(out["id"])
    assert row["status"] == "draft"
    # 草稿不能评分；人工复核通过后才转正式
    assert storage.review_analysis(out["id"], "approve", "t1")["status"] == "approved"
    assert storage.review_analysis(out["id"], "approve", "t1") is None  # 只能复核一次


# ---------------------------------------------------------------- 问题 4：批次原子性
def test_batch_is_atomic_and_recoverable(monkeypatch):
    from CampusPulse import pipeline, campus
    items = _items(["考研报名开始", "王楚钦夺冠"]) + _items(["考研报名今日开始"], source="douyin")
    monkeypatch.setattr(pipeline, "_fetch_all", lambda: {"batch_ts": 2_000_000_000, "items": items,
                                                         "errors": {}, "meta": {}})
    monkeypatch.setattr(pipeline.settings, "collect_interval_min", 30)
    real_voice = campus.summarize
    monkeypatch.setattr(campus, "summarize", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("进程被中断")))
    out = pipeline.run_once(use_llm=False)
    assert "error" in out
    st = pipeline.status()
    assert st["last_fetch"] == 2_000_000_000 and st["last_complete"] != 2_000_000_000 and st["lagging"]
    assert storage.latest_topics()["batch_ts"] != 2_000_000_000       # 没有半截结果
    sketch_blob = storage.kv_get("burst_sketch_v1")
    # 恢复：补做同一批次
    monkeypatch.setattr(campus, "summarize", real_voice)
    monkeypatch.setattr(pipeline.time, "time", lambda: 2_000_000_100)
    assert "error" not in pipeline.recover_pending()
    st = pipeline.status()
    assert st["last_complete"] == 2_000_000_000 and not st["lagging"]
    assert storage.latest_topics()["batch_ts"] == 2_000_000_000
    assert storage.kv_get("burst_sketch_v1") != sketch_blob


# ---------------------------------------------------------------- 问题 5：风险分层
def test_scam_news_is_content_risk_not_crisis():
    from CampusPulse import lens
    scam = lens.rule_annotate({"label": "“民惠通APP可发高龄补贴”不实", "titles": ["公安打掉跨国诈骗团伙"]})
    assert scam["crisis_level"] == "无" and scam["content_risk"] == "中"
    crisis = lens.rule_annotate({"label": "某地学生轻生事件", "titles": []})
    assert crisis["crisis_level"] == "关注"


# ---------------------------------------------------------------- 问题 1：本校论坛
def test_huyou_parsing_drops_identity_and_masks_pii():
    import json as _json
    from CampusPulse.sources import huyou
    feed = {"sourceFeed": {"feedId": "1", "content": "有偿代取快递 微信abc12345 电话13812345678 卡号25122542",
                           "exposureCount": 10, "commentCount": 2, "score": 1790000000000,
                           "userName": "张三", "userId": "999", "avatar": "x", "circle": {"circleName": "上海大学"}}}
    data = [["ShallowReactive", 1], {"data": 2}, {"feed-circle-1": 3},
            {"feedList": 4}, [5], feed]
    html = f'<script type="application/json" id="__NUXT_DATA__">{_json.dumps(data, ensure_ascii=False)}</script>'
    root = huyou._decode_nuxt(html)
    post = huyou._post(root["data"]["feed-circle-1"]["feedList"][0], "school", False)
    assert "13812345678" not in post["content"] and "abc12345" not in post["content"]
    assert "25122542" not in post["content"]
    assert not {"userName", "userId", "avatar"} & set(post)


# ---------------------------------------------------------------- 问题 2：梗与剪辑
def test_meme_discovery_finds_unnamed_new_word_and_video_signal():
    docs_items = [{"source": "huyou-school", "title": t, "extra": {"content": t}} for t in [
        "今天又被导师骂了真的很班味", "上了一天课身上全是班味", "室友说我班味好重", "周五晚上终于没有班味了",
        "早八人的班味谁懂", "图书馆坐一天班味拉满"]]
    # 背景语料：真实窗口有上万字，凝固度（PMI）才有区分度
    background = ["食堂今天的红烧肉很好吃", "有没有人一起去操场跑步", "期末复习资料哪里可以找到",
                  "宿舍空调坏了找谁修", "周末想去看电影求推荐", "快递站几点关门", "图书馆三楼有空位吗",
                  "体测八百米怎么准备", "选修课推荐一下", "社团招新什么时候开始"] * 6
    docs_items += [{"source": "huyou-national", "title": t, "extra": {"content": t}} for t in background]
    videos = [{"source": "bilibili-popular", "title": f"视频{i}", "url": None,
               "extra": {"bvid": f"BV{i}", "bgm": "打上花火", "tags": ["变装挑战"], "comments": []}} for i in range(3)]
    cands = memes.discover(docs_items + videos, {"BV0": {"style": "卡点剪辑"}, "BV1": {"style": "卡点剪辑"}})
    labels = {c["label"]: c for c in cands}
    assert "班味" in labels
    assert labels["BGM：打上花火"]["edit_styles"]["卡点剪辑"] == 2
    assert "#变装挑战" in labels


def test_edit_features_detects_beat_synced_cutting():
    import numpy as np
    from CampusPulse import video_features as vf
    peaks = np.arange(0.5, 30, 0.5)             # 120 BPM
    synced = list(peaks[::2][:20])               # 切点全部踩在拍点上
    f = vf.edit_features(synced, peaks, 30.0, 120.0)
    assert f["style"] == "卡点剪辑" and f["beat_sync_ratio"] == 1.0
    offbeat = [p + 0.25 for p in peaks[::2][:20]]
    assert vf.edit_features(offbeat, peaks, 30.0, 120.0)["style"] != "卡点剪辑"


def test_web_recall_requires_citations_and_checks_corpus(monkeypatch):
    monkeypatch.setattr(search, "web_search", lambda q, count=6, freshness="oneWeek": [
        {"title": "本周热梗盘点", "url": "https://example.com/a", "snippet": "“city不city”爆火……"}])
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **k: [
        {"name": "city不city", "type": "网络流行语", "meaning": "洋不洋气", "evidence": ["W1"]},
        {"name": "编造梗", "type": "网络流行语", "meaning": "无来源", "evidence": []}])
    storage.kv_set("webrecall:cands", b'{"ts": 0, "items": []}')
    docs = [("这也太city不city了", "bilibili-comment"), ("今天食堂好吃", "huyou-school")]
    out = memes.web_recall(docs, 2_100_000_000, use_llm=True)
    assert [c["label"] for c in out] == ["city不city"]          # 没有引用来源的被丢弃
    assert out[0]["df"] == 1 and out[0]["in_corpus"] and out[0]["web_links"][0]["url"] == "https://example.com/a"


def test_school_source_settings_accept_raw_links():
    from CampusPulse import pipeline
    assert pipeline.set_forums("https://tieba.baidu.com/f?kw=%25E5%258D%258E%25E4%25B8%259C%25E7%2590%2586%25E5%25B7%25A5%25E5%25A4%25A7%25E5%25AD%25A6") == ["华东理工大学"]
    assert pipeline.set_forums("华东理工大学吧") == ["华东理工大学"]
    assert pipeline.set_circles("https://hy.sns.sohu.com/circle/947622289439129600 842183276495059072") == \
        ["947622289439129600", "842183276495059072"]


def test_ads_filtered_and_theme_details_are_deidentified(monkeypatch):
    from CampusPulse import campus
    from CampusPulse.sources.huyou import mask_names
    assert campus.is_ad("💥王炸推出💥红力健身海湾本土高端连锁健身房｜双节同庆·双店同贺钜惠开启✅")
    assert not campus.is_ad("出一本二手高数课本，有需要的同学私聊")
    assert "陈贻鹏" not in mask_names("本人陈贻鹏，史上最惨高考冲刺者")
    ts = 2_200_000_000
    posts = [("大一第一节课啥也没听明白正常吗｜老师讲太快了", 7), ("钜惠开启！高端连锁健身房办卡低至五折", 50),
             ("高数作业好难，本人陈贻鹏求助", 3), ("不想活了，考试又挂了", 2)]
    storage.record_fetch(ts, [{"source": "tieba-school", "rank": i + 1, "title": c[:80],
                               "extra": {"content": c, "comments": n, "link": f"https://tieba.baidu.com/p/{i}"}}
                              for i, (c, n) in enumerate(posts)], {})
    v = campus.summarize(ts, use_llm=False)
    assert v["ads_filtered"] == 1 and v["crisis"]["高危"] == 1
    d = campus.theme_posts("学业课程", ts)
    texts = [p["content"] for p in d["posts"]]
    assert any("大一第一节课" in t for t in texts) and not any("健身房" in t for t in texts)
    assert not any("陈贻鹏" in t for t in texts)
    assert not any("不想活" in t for t in texts)       # 危机帖默认不展示原文
    assert campus.theme_posts("__crisis__", ts)["hidden_crisis"] == 1


# ---------------------------------------------------------------- 第三轮：精度 / 口径 / 可信度 / 成本
def test_meme_tiers_and_feedback():
    base = 2_300_000_000
    hist = {"w:班味": [{"batch_ts": base - 3600 * k, "df": 3 + (3 - k)} for k in (3, 2, 1)]}
    cands = [
        {"key": "w:班味", "kind": "word", "label": "班味", "df": 8, "sources": ["huyou-school", "bilibili-comment"], "score": 1},
        {"key": "x:跺脚换装", "kind": "web", "label": "跺脚换装", "df": 0, "sources": ["web"], "score": 1},
        {"key": "w:吐槽", "kind": "word", "label": "吐槽", "df": 5, "sources": ["bilibili-comment"], "score": 1},
    ]
    memes.attach_history(cands, hist, base, feedback={})
    tiers = {c["label"]: c["tier"] for c in cands}
    assert tiers == {"班味": "verified", "跺脚换装": "lead", "吐槽": "observed"}
    assert not cands[1]["is_new"]                               # 外部线索永远不标“新出现”
    # 人工标注“普通词”后，discover 不再产出该词
    docs = [{"source": "huyou-school", "title": t, "extra": {"content": t}} for t in ["吐槽一下食堂", "又来吐槽了", "想吐槽宿舍"] * 3]
    assert not any(c["label"] == "吐槽" for c in memes.discover(docs, {}, {"w:吐槽": {"label": "common"}}))


def test_campus_dedupe_and_normalized_heat():
    from CampusPulse import campus
    a = campus.simhash("嘉定校区二食堂早餐能不能再加一个窗口，排队到七点五十二")
    b = campus.simhash("嘉定校区二食堂早餐能不能再加一个窗口？排队到七点五十二！")
    c = campus.simhash("图书馆三楼有没有空位")
    assert campus._near_dup(a, b) and not campus._near_dup(a, c)
    posts = [{"scope": "huyou-school", "exposure": e, "comments": 0} for e in (100, 5000, 90000)] + \
            [{"scope": "tieba-school", "exposure": 0, "comments": n} for n in (1, 3, 400)]
    campus._percentiles(posts)
    # 两个平台各自的最高互动都得到 1.0，而不是狐友曝光量压倒贴吧回复数
    assert posts[2]["heat_pct"] == 1.0 and posts[5]["heat_pct"] == 1.0


def test_source_quality_and_entailment_gate(monkeypatch):
    from CampusPulse.agents import sources_quality as sq
    assert sq.classify("W", "https://www.moe.gov.cn/x") == "A"
    assert sq.classify("W", "https://www.bilibili.com/video/BV1") == "B"
    assert sq.classify("W", "https://baike.baidu.com/item/x") == "D"
    pool = workers.EvidencePool()
    pool.add("W", {"title": "某梗百科", "url": "https://baike.baidu.com/item/x", "snippet": "班味指上班后疲惫"})
    result = {"summary": "s", "topics": [{"name": "班味", "why_students_care": "可能因实习",
                                          "what_happened": "班味源于2019年的一部电视剧。", "evidence": ["W1"]}]}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: [{"i": 1, "verdict": "不支持", "note": "证据未提电视剧"}])
    v = verifier.verify("班味是什么", "event_brief", result, pool, [], use_judge=False, meter=llm.UsageMeter())
    assert v["hard_fail"] and "FM-3.3 事实主张不被证据支持" in v["hard_fail_reasons"]
    assert v["claims"][0]["verdict"] == "不支持"
    assert any("梗百科" in i for i in v["issues"])              # 只有 D 级来源 → 交叉验证提示


def test_enrichment_refreshes_views_without_touching_sketch(monkeypatch):
    from CampusPulse import pipeline, lens
    items = _items(["考研报名开始", "王楚钦夺冠"], source="weibo")
    ts = 2_400_000_000
    storage.record_fetch(ts, items, {})
    monkeypatch.setattr(pipeline, "start_enrichment", lambda *a: None)
    pipeline.analyze_batch(ts, items, use_llm=True)
    sketch_before = storage.kv_get("burst_sketch_v1")
    assert storage.latest_batch("complete")["stats"]["enriched"] is False
    monkeypatch.setattr(pipeline.settings, "llm_api_key", "x")
    monkeypatch.setattr(lens, "annotate_topics", lambda topics, use_llm=True, **k: [
        {**t, "lens": {**lens.rule_annotate(t), "one_liner": "模型标注", "annotator": "llm"}} for t in topics])
    monkeypatch.setattr(pipeline.memes, "web_recall", lambda *a, **k: [])
    pipeline.enrich_batch(ts, items)
    assert storage.latest_batch("complete")["stats"]["enriched"] is True
    assert all(t["lens"]["annotator"] == "llm" for t in storage.latest_topics()["topics"])
    assert storage.kv_get("burst_sketch_v1") == sketch_before


def test_hotlist_outage_keeps_previous_public_topics(monkeypatch):
    from CampusPulse import pipeline
    monkeypatch.setattr(pipeline, "start_enrichment", lambda *a: None)
    ok_items = _items(["考研报名开始", "王楚钦夺冠"], source="weibo")
    storage.record_fetch(2_500_000_000, ok_items, {})
    pipeline.analyze_batch(2_500_000_000, ok_items, use_llm=False)
    only_bili = [{"source": "bilibili-popular", "rank": 1, "title": "某个视频", "extra": {}}]
    storage.record_fetch(2_500_001_800, only_bili, {"errors": {"weibo": "500"}})
    pipeline.analyze_batch(2_500_001_800, only_bili, use_llm=False)
    topics = storage.latest_topics()["topics"]
    assert {t["label"] for t in topics} >= {"考研报名开始"} and all(t.get("stale_from") == 2_500_000_000 for t in topics)
    assert storage.latest_batch("complete")["stats"]["errors"] == {"weibo": "500"}   # 抓取错误不被覆盖


def test_anonymous_poll_flow_and_calibration():
    from flask import Flask
    from CampusPulse import blueprint
    ts = 2_600_000_000
    storage.record_fetch(ts, [], {})
    storage.commit_analysis(ts, [{"label": "跺脚换装", "scope": "meme", "key": "x:跺脚换装",
                                  "lens": {"meaning": "跺一下切换穿搭"}}], {}, {})
    app = Flask(__name__)
    app.register_blueprint(blueprint.pulse_bp, url_prefix="/pulse")
    c = app.test_client()
    token = c.post("/pulse/api/polls", json={"keys": ["x:跺脚换装", "x:不存在"]}).get_json()["token"]
    assert c.get("/pulse/poll/bad!token").status_code == 404
    page = c.get(f"/pulse/poll/{token}")
    assert page.status_code == 200 and "pulse_voter" in page.headers.get("Set-Cookie", "")
    data = c.get(f"/pulse/poll/{token}/data").get_json()
    assert [i["label"] for i in data["items"]] == ["跺脚换装"] and "results" not in data   # 公开端不暴露结果
    assert c.post(f"/pulse/poll/{token}/vote", json={"answers": {"x:跺脚换装": {"seen": 2, "follow": True}}}).status_code == 200
    assert c.post(f"/pulse/poll/{token}/vote", json={"answers": {"x:跺脚换装": {"seen": 1}}}).status_code == 409  # 同一浏览器只能投一次
    # 模拟 25 位不同同学作答，校准证据等级：仅外部线索 → 学生问卷证实
    for i in range(24):
        storage.add_vote(token, f"v{i}", {"x:跺脚换装": {"seen": 1 if i % 2 else 0, "follow": False}})
    cand = {"key": "x:跺脚换装", "kind": "web", "label": "跺脚换装", "df": 0, "sources": ["web"], "score": 1}
    memes.attach_history([cand], {}, ts, {})
    assert cand["tier"] == "observed" and "问卷" in cand["tier_reason"]
    blueprint._vote_rate.clear()
    blueprint._VOTE_LIMIT_PER_HOUR = 2
    t2 = c.post("/pulse/api/polls", json={"keys": ["x:跺脚换装"]}).get_json()["token"]
    codes = []
    for i in range(3):
        c2 = app.test_client()
        c2.get(f"/pulse/poll/{t2}")
        codes.append(c2.post(f"/pulse/poll/{t2}/vote", json={"answers": {"x:跺脚换装": {"seen": 1}}}).status_code)
    assert codes == [200, 200, 429]   # 同一 IP 频率限制
