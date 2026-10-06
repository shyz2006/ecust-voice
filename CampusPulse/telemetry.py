"""永久用量台账。不保存提示词、响应正文、密钥；历史缺失不估算。"""
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS pulse_ledger (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_seen_posts (key TEXT PRIMARY KEY, source TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_usage (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, success INTEGER NOT NULL,
 usage_known INTEGER NOT NULL, prompt_tokens INTEGER, completion_tokens INTEGER, seconds REAL NOT NULL,
 engine TEXT NOT NULL DEFAULT 'CampusPulse');
CREATE INDEX IF NOT EXISTS pulse_usage_ts ON pulse_usage(ts);
CREATE TABLE IF NOT EXISTS pulse_main_reports (key TEXT PRIMARY KEY,first_seen INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS pulse_auto_reports (
 id INTEGER PRIMARY KEY AUTOINCREMENT, slot TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, ts INTEGER NOT NULL,
 status TEXT NOT NULL, snapshot_ts INTEGER, payload TEXT, error TEXT, completed_ts INTEGER,
 started_ts INTEGER);
"""


def initialize(conn):
    # executescript隐式提交；此函数只由storage首次初始化调用，不能插入抓取事务中。
    conn.executescript(SCHEMA)
    usage_cols = {r[1] for r in conn.execute('PRAGMA table_info(pulse_usage)')}
    if 'engine' not in usage_cols:
        conn.execute("ALTER TABLE pulse_usage ADD COLUMN engine TEXT NOT NULL DEFAULT 'CampusPulse'")
        conn.commit()
    cols = {r[1] for r in conn.execute('PRAGMA table_info(pulse_auto_reports)')}
    if 'started_ts' not in cols:
        conn.execute('ALTER TABLE pulse_auto_reports ADD COLUMN started_ts INTEGER')
        conn.commit()
    if conn.execute("SELECT 1 FROM pulse_ledger WHERE key='initialized_at'").fetchone():
        return
    conn.execute('BEGIN IMMEDIATE')
    try:
        if conn.execute("SELECT 1 FROM pulse_ledger WHERE key='initialized_at'").fetchone():
            conn.commit()
            return
        rows = conn.execute('SELECT source,title,extra,batch_ts FROM snapshots').fetchall()
        record_rows(conn, rows)
        first = min((r['batch_ts'] for r in rows), default=int(time.time()))
        last = max((r['batch_ts'] for r in rows), default=0)
        analysis_id = conn.execute('SELECT coalesce(max(id),0) FROM analyses').fetchone()[0]
        for k, v in [('initialized_at', int(time.time())), ('observed_since', first), ('baseline_cutoff', last), ('baseline_analysis_id',analysis_id)]:
            conn.execute('INSERT INTO pulse_ledger(key,value) VALUES (?,?)', (k, v))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _add(conn, key, amount):
    conn.execute('INSERT INTO pulse_ledger(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=value+excluded.value', (key, amount))


def record_rows(conn, rows):
    for r in rows:
        src = r['source']
        ex = r['extra'] if isinstance(r['extra'], dict) else json.loads(r['extra'] or '{}')
        key = src+':'+hashlib.sha1(str(ex.get('link') or ex.get('feed_id') or ex.get('content') or r['title']).encode()).hexdigest()
        _add(conn, 'observations', 1)
        _add(conn, 'observations:'+src, 1)
        if src in ('huyou-school', 'tieba-school'):
            _add(conn, 'school_observations', 1)
        cur = conn.execute('INSERT OR IGNORE INTO pulse_seen_posts(key,source) VALUES (?,?)', (key, src))
        if cur.rowcount:
            _add(conn, 'unique_items', 1)
            _add(conn, 'unique:'+src, 1)
            if src in ('huyou-school','tieba-school'):
                _add(conn, 'unique_school_posts', 1)


def record_response(usage, seconds, success=True,engine='CampusPulse'):
    from . import storage
    prompt = getattr(usage, 'prompt_tokens', None)
    completion = getattr(usage, 'completion_tokens', None)
    known = prompt is not None and completion is not None
    with storage.connect() as conn:
        conn.execute('INSERT INTO pulse_usage(ts,success,usage_known,prompt_tokens,completion_tokens,seconds,engine) VALUES (?,?,?,?,?,?,?)',
                     (int(time.time()), int(success), int(known), prompt, completion, round(seconds,3),engine))


def sync_main_reports(conn):
    root=Path(__file__).resolve().parent.parent
    files=list((root/'final_reports').glob('final_report_*.html'))
    files+=list((root/'runtime'/'tasks').glob('*/outputs/report/final_report_*.html'))
    for path in files:
        try:
            content=path.read_bytes()
            # 不计未写完的空文件/HTML片段；同一报告复制到不同目录不重复计数。
            if b'</html>' not in content[-1024:].lower():continue
            key=hashlib.sha256(content).hexdigest()
            conn.execute('INSERT OR IGNORE INTO pulse_main_reports(key,first_seen) VALUES (?,?)',(key,int(time.time())))
        except OSError:
            continue


def dashboard():
    from . import storage
    with storage.connect() as conn:
        sync_main_reports(conn)
        ledger = dict(conn.execute('SELECT key,value FROM pulse_ledger').fetchall())
        usage = dict(conn.execute('SELECT count(*) calls,coalesce(sum(success),0) successful_calls,'
                  'coalesce(sum(CASE WHEN success=1 AND usage_known=0 THEN 1 ELSE 0 END),0) unknown_usage_calls,'
                  'coalesce(sum(prompt_tokens),0) prompt_tokens,coalesce(sum(completion_tokens),0) completion_tokens FROM pulse_usage').fetchone())
        daily = [dict(r) for r in conn.execute("SELECT date(ts,'unixepoch','+8 hours') day,count(*) calls,"
                 "coalesce(sum(prompt_tokens+completion_tokens),0) tokens,sum(CASE WHEN success=0 THEN 1 ELSE 0 END) failures "
                 "FROM pulse_usage WHERE ts>=? GROUP BY day ORDER BY day", (int(time.time())-10*86400,))]
        statuses = dict(conn.execute('SELECT status,count(*) FROM analyses GROUP BY status').fetchall())
        automatic = dict(conn.execute('SELECT status,count(*) FROM pulse_auto_reports GROUP BY status').fetchall())
        main_reports=conn.execute('SELECT count(*) FROM pulse_main_reports').fetchone()[0]
        engines=[dict(r) for r in conn.execute('SELECT engine,count(*) calls,coalesce(sum(prompt_tokens+completion_tokens),0) tokens,'
                 'sum(CASE WHEN success=1 AND usage_known=0 THEN 1 ELSE 0 END) unknown_calls FROM pulse_usage GROUP BY engine')]
        # 历史研报是任务内独立UsageMeter，批次的并发进程差值不与之相加。
        old_tokens = old_measured = 0
        historical_input = historical_output = split_tasks = missing_tasks = 0
        for row in conn.execute('SELECT payload FROM analyses WHERE id<=?', (ledger.get('baseline_analysis_id',0),)):
            v = json.loads(row[0]).get('usage') or {}
            if v.get('prompt_tokens') is not None and v.get('completion_tokens') is not None:
                historical_input += int(v['prompt_tokens'])
                historical_output += int(v['completion_tokens'])
                split_tasks += 1
            else:
                missing_tasks += 1
            if v.get('total_tokens') is not None:
                old_tokens += int(v['total_tokens'])
                old_measured += 1
        batch_count = conn.execute('SELECT count(*) FROM batches').fetchone()[0]
        b = conn.execute('SELECT batch_ts,stats FROM batches ORDER BY batch_ts DESC LIMIT 1').fetchone()
        complete = conn.execute("SELECT batch_ts FROM batches WHERE status='complete' ORDER BY batch_ts DESC LIMIT 1").fetchone()
        current_sources = dict(conn.execute('SELECT source,count(*) FROM snapshots WHERE batch_ts=? GROUP BY source', (complete['batch_ts'],)).fetchall()) if complete else {}
        legacy_batch_tokens = 0
        for r in conn.execute('SELECT stats FROM batches WHERE batch_ts<=?', (ledger['baseline_cutoff'],)):
            stats = json.loads(r[0] or '{}')
            legacy_batch_tokens += int(stats.get('enrich_llm_tokens') or 0)+int(stats.get('analyze_llm_tokens') or 0)
        from . import costs
        cost = costs.summary(conn,usage,historical_input,historical_output,split_tasks,missing_tasks)
    return {'cost':cost, 'success': True, 'generated_at': int(time.time()), 'scope': '校园观察、育人工坊与BettaFish主研报',
            'observed_since': ledger['observed_since'], 'ledger_started_at': ledger['initialized_at'],
            'school_observations': ledger.get('school_observations',0), 'unique_school_posts': ledger.get('unique_school_posts',0),
            'observations': ledger.get('observations',0), 'unique_items': ledger.get('unique_items',0),
            'sources': [{'source': k[7:], 'unique': v, 'observations':ledger.get('observations:'+k[7:],0),
                         'latest_count': current_sources.get(k[7:])} for k,v in ledger.items() if k.startswith('unique:')],
            'reports_completed': statuses.get('formal',0)+statuses.get('approved',0)+automatic.get('complete',0)+main_reports,
            'main_reports_completed':main_reports, 'campus_reports_completed':statuses.get('formal',0)+statuses.get('approved',0),
            'reports_pending_review':statuses.get('formal',0), 'report_statuses':statuses, 'automatic_statuses':automatic,
            'recorded_tokens': old_tokens+usage['prompt_tokens']+usage['completion_tokens'],
            'historical_report_tokens':old_tokens, 'historical_measured_reports':old_measured,
            'legacy_batch_summary_tokens':legacy_batch_tokens, 'usage':usage, 'usage_by_engine':engines, 'daily_usage':daily,
            'retained_batches':batch_count, 'latest_fetch':b['batch_ts'] if b else None,
            'latest_complete_fetch':complete['batch_ts'] if complete else None,
            'notes':['累计采集从尚存快照回填；此前已清理历史无法还原。以后台账不随30天快照清理而减少。',
                     '帖子数以来源+帖子链接/正文哈希去重，跨论坛分别计数；采集条次包含重复轮询。',
                     '已记录Token=启用前可核实研报UsageMeter+启用后每次模型响应usage。服务商不返回usage时记为未知。',
                     '启用后校园、查询、洞察、媒体、主研报、论坛主持等引擎的OpenAI兼容请求统一记账；旧主流程Token未记录，无法回补。',
                     '旧批次用量为并发进程差值，可能重叠，单列展示而不加入累计。主流程完整HTML按内容哈希去重，不计IR/状态文件或导出副本。',
                     '完成报告包括待人工复核的有效研报及已完成自动报告；失败、降级稿和固定方案模板不计完成。']}
