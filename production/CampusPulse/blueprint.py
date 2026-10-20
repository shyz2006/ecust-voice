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

from flask import Blueprint, jsonify, redirect, request, send_from_directory, session, Response, send_file

from . import pipeline, storage
from .agents import analysis_options, router, workflows, workers
from .agents.orchestrator import Orchestrator

pulse_bp = Blueprint("campus_pulse", __name__)
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_jobs = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 50
_MAX_CONCURRENT = 3


@pulse_bp.before_request
def retire_activity_generation():
    if request.method=='POST' and (request.path.endswith('/api/analyze') or
            ('/api/issues/' in request.path and request.path.endswith('/generate'))):
        return jsonify(success=False,message='请在育人工坊提交事件研究主题'),410


@pulse_bp.after_request
def revision_cache_policy(response):
    if '/api/revision/' in request.path:
        response.headers['Cache-Control']='no-store'
    return response


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
    resp = send_from_directory(_TEMPLATE_DIR, "pulse.html", max_age=0)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


@pulse_bp.route("/api/status")
def api_status():
    from .config import refresh_runtime
    refresh_runtime()
    return jsonify({"success": True, **pipeline.status()})


@pulse_bp.route('/api/revision/overview')
def revision_overview():
    from . import revision
    data=revision.snapshot()
    return jsonify(success=True,**{k:v for k,v in data.items() if k!='posts'})


@pulse_bp.route('/api/revision/posts')
def revision_posts():
    from . import revision,taxonomy
    data=revision.snapshot();posts=data['posts']
    theme=request.args.get('theme','');emotion=request.args.get('emotion','')
    if theme and theme not in taxonomy.THEMES:return jsonify(success=False,message='无效议题分类'),400
    if emotion and emotion not in ('积极','中性','消极'):return jsonify(success=False,message='无效情绪类别'),400
    if theme:posts=[p for p in posts if p['theme']==theme]
    if emotion:posts=[p for p in posts if p['emotion']==emotion]
    if request.args.get('red')=='1':posts=[p for p in posts if p['red']]
    source=request.args.get('source','')
    if source and source not in ('huyou-school','tieba-school'):return jsonify(success=False,message='无效来源'),400
    if source:posts=[p for p in posts if p['source']==source]
    word=request.args.get('word','').strip()[:30]
    if word:posts=[p for p in posts if word in p['content']]
    try:
        since=int(request.args.get('from',data['window_start']));until=int(request.args.get('until',data['generated_at']+1))
    except (ValueError,TypeError):return jsonify(success=False,message='无效时间窗口'),400
    if since>=until:return jsonify(success=False,message='时间窗口顺序有误'),400
    posts=[p for p in posts if since<=p['published']<until]
    posts=sorted(posts,key=lambda p:-p['published'])
    return jsonify(success=True,posts=posts,total=len(posts),generated_at=data['generated_at'])


@pulse_bp.route('/api/revision/feed/<kind>')
def revision_feed(kind):
    from . import revision
    if kind not in ('hot','memes'):return jsonify(success=False,message='无效栏目'),404
    return jsonify(success=True,**revision.network_feed(kind))


@pulse_bp.route('/api/revision/source-posts')
def revision_source_posts():
    from . import revision
    source=request.args.get('source','')
    if source not in set(revision.HOT_PLATFORMS)|set(revision.MEME_PLATFORMS):
        return jsonify(success=False,message='无效平台'),400
    rows=storage.recent_items([source],int(time.time())-7*86400);seen={}
    for r in rows:
        url=(r.get('extra') or {}).get('link') or r.get('url')
        key=url or r['title']
        seen[key]={'source':source,'content':r['title'],'link':revision.source_link(url),'published':r['batch_ts'],'time_basis':'first_observed'}
    posts=sorted(seen.values(),key=lambda p:-p['published'])
    return jsonify(success=True,posts=posts,total=len(posts))


@pulse_bp.route('/api/revision/ledger')
def revision_ledger():
    from . import telemetry,revision
    data=telemetry.dashboard()
    allowed=set(revision.HOT_PLATFORMS)|set(revision.MEME_PLATFORMS)|set(revision.observatory.SOURCES)
    sources=[s for s in data.get('sources',[]) if s['source'] in allowed]
    # Cost, vendor and legacy national-comparison values are excluded from this presentation API.
    from datetime import datetime,timedelta,timezone
    today=datetime.now(timezone(timedelta(hours=8))).date()
    days=[today-timedelta(days=n) for n in range(13,-1,-1)]
    start=int(datetime.combine(days[0],datetime.min.time(),tzinfo=timezone(timedelta(hours=8))).timestamp())
    with storage.connect() as conn:
        daily=[dict(r) for r in conn.execute("SELECT date(ts,'unixepoch','+8 hours') day, "
               "SUM(CASE WHEN usage_known=1 THEN prompt_tokens+completion_tokens END) tokens, "
               "SUM(CASE WHEN success=1 AND usage_known=0 THEN 1 ELSE 0 END) unknown_calls "
               "FROM pulse_usage WHERE ts>=? AND ts<=? GROUP BY day ORDER BY day",(start,int(time.time())))]
    by_day={r['day']:r for r in daily}
    daily=[dict(by_day.get(day.isoformat(),{'day':day.isoformat(),'tokens':None,'unknown_calls':0}),has_records=day.isoformat() in by_day) for day in days]
    return jsonify(success=True,generated_at=data['generated_at'],observed_since=data['observed_since'],
                   unique_school_posts=data['unique_school_posts'],reports_completed=data['main_reports_completed'],
                   unique_items=sum(s['unique'] for s in sources),sources=sources,
                   recorded_tokens=data['recorded_tokens'],daily_usage=daily)


@pulse_bp.route('/api/revision/research',methods=['GET','POST'])
def revision_research():
    from . import research
    if session.get('authenticated') is not True or not _username():return jsonify(success=False,message='请登录后使用报告研究'),401
    if request.method=='GET':return jsonify(success=True,items=research.history(_username()))
    body=request.get_json(silent=True)
    query=body.get('query') if isinstance(body,dict) else None
    if not isinstance(query,str) or not 1<=len(query.strip())<=500:return jsonify(success=False,message='请输入1至500字的研究主题'),400
    request_id=body.get('request_id','')
    if not isinstance(request_id,str) or len(request_id)>80:return jsonify(success=False,message='请求编号格式有误'),400
    try:return jsonify(success=True,**research.start(query.strip(),_username(),request_id))
    except ValueError as exc:return jsonify(success=False,message=str(exc)),400
    except Exception:
        return jsonify(success=False,message='研究服务启动失败，请检查模型与检索配置'),503


@pulse_bp.route('/api/revision/research/<task_id>')
def revision_research_status(task_id):
    from . import research
    try:allowed=research.authorize(task_id,_username()) if session.get('authenticated') is True else False
    except ValueError:allowed=False
    if not allowed:return jsonify(success=False,message='研究任务不存在或无权访问'),404
    return jsonify(success=True,**research.status(task_id))


@pulse_bp.route('/api/revision/research/<task_id>/report')
def revision_research_report(task_id):
    from . import research
    try:allowed=research.authorize(task_id,_username()) if session.get('authenticated') is True else False
    except ValueError:allowed=False
    if not allowed:return jsonify(success=False,message='研究任务不存在或无权访问'),404
    try:
        if request.args.get('format')=='pdf':
            response=send_file(research.pdf(task_id),mimetype='application/pdf',as_attachment=True,download_name='事件分析报告.pdf')
        else:
            response=Response(research.report_html(task_id),mimetype='text/html')
            response.headers['Content-Security-Policy']="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src 'self'"
        response.headers['Cache-Control']='no-store'
        return response
    except ValueError as exc:return jsonify(success=False,message=str(exc)),409
    except Exception:return jsonify(success=False,message='报告导出失败，请稍后重试'),503


@pulse_bp.route("/api/topics")
def api_topics():
    return jsonify({"success": True, **storage.latest_topics("public")})


@pulse_bp.route("/api/meme-trends")
def api_meme_trends():
    """梗 / 短视频玩法候选（聚合 B站、抖音、微博、百度、知乎等全网平台及校内共鸣）。"""
    from . import memes
    items = memes.network_meme_catalog()
    return jsonify({"success": True, "topics": items, "items": items})


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


@pulse_bp.route("/api/campus/crisis-posts")
def api_campus_crisis_posts():
    if session.get("authenticated") is not True:
        response = jsonify({"success": False, "message": "请登录后查看关注帖子"})
        response.headers["Cache-Control"] = "no-store"
        return response, 401
    level = str(request.args.get("level", "")).strip()
    if level not in ("高危", "关注", "all", "ads"):
        return jsonify({"success": False, "message": "请选择有效的查看类别"}), 400
    from . import campus

    blob = storage.kv_get("campus_voice")
    voice = json.loads(blob) if blob else {}
    now = int(time.time())
    snapshot = min(int(voice.get("generated_at") or now), now)
    response = jsonify({"success": True, **campus.crisis_posts(level, snapshot)})
    response.headers["Cache-Control"] = "no-store"
    return response


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
    query = body.get("query", "")
    if not isinstance(query, str):
        return jsonify(success=False, message='问题必须是文字'), 400
    query = query.strip()
    if not query:
        return jsonify({"success": False, "message": "请输入问题"}), 400
    if len(query) > 200:
        return jsonify(success=False, message='问题最多 200 字，请缩短后再提交'), 400
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
            if job['result'].get('degraded'):
                notes = [s.get('note') for s in job['result'].get('trace',[]) if s.get('action') == '模型服务不可用，返回检索证据' and s.get('note')]
                job['error'] = '模型未生成报告，仅保存检索资料。' + (notes[-1] if notes else '请在配置中测试模型连接。')
                job['status'] = 'error'
            else:
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
    from . import weekly
    weekly.start_scheduler()
    # Earlier automatic reports use the retired taxonomy and activity-oriented
    # summary prompts. New reports are explicitly submitted to the original runner.
    def warm_revision():
        try:
            from .revision import snapshot
            snapshot()
        except Exception:
            app.logger.exception('Campus revision warm-up failed')
    threading.Thread(target=warm_revision,name='campus-revision-warmup',daemon=True).start()


@pulse_bp.route('/api/observatory')
def api_observatory():
    from . import observatory
    data = observatory.snapshot()
    from . import issues
    return jsonify({**{k:v for k,v in data.items() if k != 'posts'}, 'recommendations':issues.recommendations(data)})


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


def _issue_access(write=False):
    if not _username():
        return jsonify(success=False,message='请先登录教师账号'),401
    if write:
        from urllib.parse import urlsplit
        origin = request.headers.get('Origin')
        try:
            foreign_origin = bool(origin and urlsplit(origin).netloc != request.host)
        except ValueError:
            foreign_origin = True
        if request.headers.get('Sec-Fetch-Site') == 'cross-site' or foreign_origin:
            return jsonify(success=False,message='请从本站提交修改'),403
        if not request.is_json or not isinstance(request.get_json(silent=True),dict):
            return jsonify(success=False,message='请使用JSON对象提交'),400
    return None


@pulse_bp.route('/api/issues', methods=['GET','POST'])
def api_issues():
    denied = _issue_access(request.method == 'POST')
    if denied:
        return denied
    from . import issues, observatory
    try:
        if request.method == 'GET':
            return jsonify(success=True,items=issues.listing(request.args.get('state')))
        body = request.get_json()
        item = issues.create(body.get('title'),body.get('post_ids'),observatory.snapshot(),_username())
        return jsonify(success=True,item=item),201
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400


@pulse_bp.route('/api/issues/<issue_id>',methods=['GET','PATCH'])
def api_issue(issue_id):
    denied = _issue_access(request.method == 'PATCH')
    if denied:
        return denied
    from . import issues
    try:
        item = issues.get(issue_id) if request.method == 'GET' else issues.update(issue_id,request.get_json(),_username())
        if item:
            return jsonify(success=True,item=item)
    except issues.Conflict as exc:
        return jsonify(success=False,message=str(exc)),409
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    except KeyError:
        pass
    return jsonify(success=False,message='议题不存在'),404


@pulse_bp.route('/api/issues/<issue_id>/generate',methods=['POST'])
def api_issue_generate(issue_id):
    denied = _issue_access(True)
    if denied:
        return denied
    from . import issues
    try:
        body = request.get_json()
        options = analysis_options.normalize(body.get('analysis_options'))
        job_id = issues.start_job(issue_id,body.get('kind','brief'),options,_username())
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    except issues.Conflict as exc:
        return jsonify(success=False,message=str(exc)),409
    except KeyError:
        return jsonify(success=False,message='议题不存在'),404
    try:
        threading.Thread(target=issues.run_job,args=(job_id,),daemon=True).start()
    except RuntimeError:
        with storage.connect() as conn:
            conn.execute("UPDATE pulse_issue_jobs SET status='failed',error='任务启动失败，请重试' WHERE id=?",(job_id,))
        return jsonify(success=False,message='任务启动失败，请重试'),503
    return jsonify(success=True,job_id=job_id),202


@pulse_bp.route('/api/issue-jobs/<job_id>')
def api_issue_job(job_id):
    denied = _issue_access()
    if denied:
        return denied
    from . import issues
    job = issues.job_get(job_id)
    return (jsonify(success=True,job=job) if job else (jsonify(success=False,message='任务不存在'),404))


@pulse_bp.route('/api/issues/<issue_id>/export')
def api_issue_export(issue_id):
    denied = _issue_access()
    if denied:
        return denied
    from . import issues
    from flask import Response
    item = issues.get(issue_id)
    if not item:
        return jsonify(success=False,message='议题不存在'),404
    response = Response(issues.markdown(item),mimetype='text/markdown')
    response.headers['Content-Disposition'] = 'attachment; filename="campus-issue-'+issue_id+'.md"'
    return response


@pulse_bp.route('/api/revision/weekly',methods=['GET','POST'])
@pulse_bp.route('/api/revision/weekly/config',methods=['GET','POST'])
@pulse_bp.route('/api/revision/weekly/test-email',methods=['POST'])
@pulse_bp.route('/api/revision/weekly/<report_id>',methods=['GET'])
@pulse_bp.route('/api/revision/weekly/<report_id>/report',methods=['GET'])
@pulse_bp.route('/api/revision/weekly/<report_id>/send',methods=['POST'])
@pulse_bp.route('/api/revision/weekly/<report_id>/retry',methods=['POST'])
def revision_weekly(report_id=None):
    from . import weekly
    from urllib.parse import urlsplit
    if session.get('authenticated') is not True or not _username():return jsonify(success=False,message='请登录后查看校园周报'),401
    if request.method=='POST':
        origin=request.headers.get('Origin')
        if origin and urlsplit(origin).netloc!=request.host:return jsonify(success=False,message='请求来源有误'),403
        if not request.is_json:return jsonify(success=False,message='请使用JSON提交'),400
    try:
        body=request.get_json(silent=True) or {}
        if request.path.endswith('/config'):
            return jsonify(success=True,config=weekly.save_config(body) if request.method=='POST' else weekly.config())
        if request.path.endswith('/test-email'):
            address=str(body.get('recipient') or '').strip()
            if not weekly.email_address(address):raise ValueError('请填写测试收件邮箱')
            value=weekly.config(True)
            if not value['api_key'] or not value['sender'] or not value['sender_verified']:raise ValueError('请先保存密钥和已验证的发件邮箱')
            if not weekly.lease('test-email',60):raise ValueError('测试邮件已提交，请稍后再试')
            email_id=weekly.resend({'from':value['sender'],'to':[address],'subject':'华理校园周报 · 邮箱测试','html':'<p>校园周报邮件配置测试成功。</p>'},'campus-weekly/test/'+uuid.uuid4().hex,value['api_key'])
            return jsonify(success=True,email_id=email_id,message='已提交测试邮件，请查收')
        if report_id:
            row=weekly.get(report_id)
            if request.path.endswith('/report'):return Response(weekly.report_html(row),mimetype='text/html')
            if request.path.endswith('/send'):
                if row['status']!='ready':raise ValueError('请等周报正文生成完成')
                weekly.delivery_ready(weekly.config(True))
                threading.Thread(target=weekly.send_report,args=(report_id,True),daemon=True).start()
                return jsonify(success=True,message='邮件已进入发送队列')
            if request.path.endswith('/retry'):
                if row['status'] not in ('failed','generating'):raise ValueError('本期周报已完成')
                with storage.connect() as conn:conn.execute("UPDATE pulse_weekly SET status='generating',error=NULL WHERE id=?",(report_id,))
                threading.Thread(target=weekly.generate,args=(report_id,),daemon=True).start()
                return jsonify(success=True,id=report_id)
            return jsonify(success=True,item=row)
        if request.method=='POST':return jsonify(success=True,id=weekly.start())
        return jsonify(success=True,items=weekly.recent(),config=weekly.config())
    except ValueError as exc:return jsonify(success=False,message=str(exc)),400
    except Exception:return jsonify(success=False,message='周报服务暂未完成，请稍后重试'),503
