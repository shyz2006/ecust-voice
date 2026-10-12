"""北京时间每周一08:00宏观报告；启用后每三天08:00统计简析。

SQLite唯一slot防多线程/多进程重复扣费；重启不自动重试未知完成状态的模型任务。
"""
import json
import os
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import storage

TZ = ZoneInfo('Asia/Shanghai')
_thread = None
_guard = threading.Lock()


def enabled():
    return os.getenv('PULSE_AUTO_REPORTS', '1') == '1'


def schedule_times(now, initialized):
    dt = datetime.fromtimestamp(now, TZ)
    monday = (dt-timedelta(days=dt.weekday())).replace(hour=8,minute=0,second=0,microsecond=0)
    # 启用后的第3日首次简析。日期锚定防止重启后周期漂移。
    anchor = datetime.fromtimestamp(initialized, TZ).replace(hour=8,minute=0,second=0,microsecond=0)+timedelta(days=3)
    k = max(0, (dt.date()-anchor.date()).days//3)
    brief = anchor+timedelta(days=3*k)
    return {'macro': int(monday.timestamp()), 'brief':int(brief.timestamp())}


def scheduler_status():
    now = int(time.time())
    with storage.connect() as conn:
        initialized = conn.execute("SELECT value FROM pulse_ledger WHERE key='initialized_at'").fetchone()[0]
        recent = [dict(r) for r in conn.execute('SELECT id,kind,ts,status,completed_ts,error FROM pulse_auto_reports ORDER BY id DESC LIMIT 20')]
    due = schedule_times(now,initialized)
    next_macro = due['macro']+7*86400 if due['macro'] <= now else due['macro']
    next_brief = due['brief']+3*86400 if due['brief'] <= now else due['brief']
    return {'enabled':enabled(), 'timezone':'Asia/Shanghai', 'macro':'每周一 08:00',
            'brief':'每三天 08:00（自启用日期锚定）', 'next_macro':next_macro,
            'next_brief':next_brief, 'recent':recent, 'thread_alive':bool(_thread and _thread.is_alive())}


def _claim(kind, ts):
    if kind not in ('macro','brief'):
        raise ValueError('无效报告类型')
    slot = kind+':'+str(ts)
    with storage.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        cur = conn.execute('INSERT OR IGNORE INTO pulse_auto_reports(slot,kind,ts,status,started_ts) VALUES (?,?,?,?,?)',
                            (slot,kind,ts,'running',int(time.time())))
        return cur.lastrowid if cur.rowcount else None


def _finish(report_id, status, payload=None, snapshot_ts=None, error=None):
    with storage.connect() as conn:
        conn.execute('UPDATE pulse_auto_reports SET status=?,payload=?,snapshot_ts=?,error=?,completed_ts=? WHERE id=?',
                     (status,json.dumps(payload,ensure_ascii=False) if payload else None,snapshot_ts,error,int(time.time()),report_id))


def compose(data, kind):
    """无原帖/用户标识进入报告提示词；事实表与数据范围始终由程序填充。"""
    facts = [{k:t[k] for k in ('theme','posts','by_source','keywords','phase','velocity','acceleration','forecast_24h','confidence')}
             for t in data['themes']]
    for fact,theme in zip(facts,data['themes']):
        prediction=theme.get('forecast') or {}
        if prediction:
            fact['forecast_model']=prediction.get('label')
            fact['forecast_note']=prediction.get('reason')
    total = data['total']
    leading = sorted(facts,key=lambda t:-t['posts'])[:5]
    names = '、'.join(t['theme'] for t in leading) or '暂无议题'
    summary = f"近10天窗口实际采集可展示独立帖{total}条。讨论量靠前的主题为{names}；这是公开论坛样本中的关注结构，不代表全校学生意见。"
    interpretation = []
    usage = None
    if kind == 'macro':
        from . import llm
        meter = llm.UsageMeter()
        result = llm.chat_json(
            '你是高校校园观察报告编辑。只依据给定统计事实写宏观观察，不补造新闻、数量、采访或民意结论。'
            '关注学生近期兴趣、诉求与可响应的育人契机。趋势不足则明确资料不足。'
            '所有interpretation关联现有theme；不得推断个体心理诊断。输出JSON：'
            '{"observations":[{"theme":"统计表中的主题原名","interpretation":"80字内解释","actions":["一条可行建议"]}]}，最多5条。',
            json.dumps({'sample_scope':'狐友华理圈与本校贴吧公开列表，近10天窗口，非随机抽样',
                        'generated_at':data['generated_at'],'total':total,'facts':facts,
                        'limits':data['method']['limits']},ensure_ascii=False), meter=meter,max_tokens=2400)
        valid = {t['theme'] for t in facts}
        if not isinstance(result,dict) or not isinstance(result.get('observations'),list):
            raise ValueError('模型未按报告结构返回')
        for item in result['observations'][:5]:
            if not isinstance(item,dict) or item.get('theme') not in valid or not isinstance(item.get('interpretation'),str):
                raise ValueError('模型引用了统计表外主题')
            if not isinstance(item.get('actions',[]),list):
                raise ValueError('模型建议字段格式不正确')
            interpretation.append({'theme':item['theme'],'interpretation':item['interpretation'][:500],
                                   'actions':[a[:300] for a in (item.get('actions') or [])[:3] if isinstance(a,str)]})
        if not interpretation:
            raise ValueError('模型没有生成观察内容')
        usage = meter.as_dict()
    else:
        for t in facts:
            interpretation.append({'theme':t['theme'], 'interpretation':
                f"本窗口{t['posts']}条，占样本{t['posts']/max(total,1):.1%}。状态：{t['phase']}。"
                +(f"速度{t['velocity']:+.3f}、加速度{t['acceleration']:+.3f}。" if t['velocity'] is not None else '连续窗口覆盖不足，不给出升温结论。'),
                'actions':[]})
    return {'title':'校园宏观观察周报' if kind == 'macro' else '校园分主题三日简析',
            'summary':summary,'generated_at':data['generated_at'],'kind':kind, 'facts':facts,
            'observations':interpretation,'usage':usage,'snapshot':{'total':total,'by_source':data['by_source'],
                'window_start':data['window_start'],'coverage':data['coverage'],'method':data['method']},
            'notice':'统计事实由程序计算；宏观解释由模型辅助生成，需教师复核。简析为规则统计，不调用模型。'}


def run_slot(kind, ts):
    from . import observatory
    report_id = _claim(kind,ts)
    if report_id is None:
        return None
    try:
        data = observatory.snapshot(force=True)
        newest = max((p['last_observed'] for p in data['posts']),default=0)
        if not data['total'] or time.time()-newest > 86400:
            _finish(report_id,'skipped',error='暂无24小时内更新的可展示论坛样本')
            return report_id
        payload = compose(data,kind)
        _finish(report_id,'complete',payload,data['generated_at'])
    except Exception as exc:
        # 只保存错误类型，不持久化可能带服务商参数的异常全文。
        _finish(report_id,'failed',error='生成失败（'+type(exc).__name__+'），可检查模型或采集状态')
    return report_id


def tick(now=None):
    if not enabled() or not _guard.acquire(blocking=False):
        return
    try:
        now = int(now or time.time())
        with storage.connect() as conn:
            initialized = conn.execute("SELECT value FROM pulse_ledger WHERE key='initialized_at'").fetchone()[0]
            # 运行超过6小时的未知状态只标记中断，不自动重发模型请求。
            conn.execute("UPDATE pulse_auto_reports SET status='interrupted',error='任务中断，未自动重试以避免重复模型费用' WHERE status='running' AND coalesce(started_ts,ts)<?", (now-6*3600,))
        for kind,ts in schedule_times(now,initialized).items():
            # 允许重启后24h内补一次，其他错过的周期不集中补跑。
            if initialized <= ts <= now and now-ts < 86400:
                run_slot(kind,ts)
    finally:
        _guard.release()


def start_scheduler():
    global _thread
    if not enabled() or (_thread and _thread.is_alive()):
        return
    def loop():
        time.sleep(25)
        while True:
            try:
                tick()
            except Exception:
                from loguru import logger
                logger.warning('[CampusPulse] 自动报告调度失败，将在下一轮检查')
            time.sleep(60)
    _thread = threading.Thread(target=loop,name='campus-auto-reports',daemon=True)
    _thread.start()


def recent():
    with storage.connect() as conn:
        return [dict(r) for r in conn.execute('SELECT id,kind,ts,status,snapshot_ts,error,completed_ts FROM pulse_auto_reports ORDER BY id DESC LIMIT 50')]


def get(report_id):
    with storage.connect() as conn:
        row = conn.execute('SELECT * FROM pulse_auto_reports WHERE id=?',(report_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    result['payload'] = json.loads(result['payload']) if result['payload'] else None
    return result


def markdown(row):
    p = row['payload']
    text = f"# {p['title']}\n\n{p['summary']}\n\n{p['notice']}\n\n"
    for o in p['observations']:
        text += f"## {o['theme']}\n\n{o['interpretation']}\n\n"
        text += ''.join('- '+a+'\n' for a in o['actions'])+'\n'
    text += '## 可核查统计事实\n\n|主题|帖子数|速度|加速度|状态|\n|---|---:|---:|---:|---|\n'
    for t in p['facts']:
        text += f"|{t['theme']}|{t['posts']}|{t['velocity'] if t['velocity'] is not None else '缺测'}|{t['acceleration'] if t['acceleration'] is not None else '缺测'}|{t['phase']}|\n"
    text += '\n## 数据范围与方法\n\n'+json.dumps(p['snapshot'],ensure_ascii=False,indent=2)+'\n'
    return text
