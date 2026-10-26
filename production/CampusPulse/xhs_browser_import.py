"""Receive explicit exports of visible XHS search cards; never receive account sessions."""
import json
import math
import re
import threading
import time
import secrets
import hashlib
import hmac
from urllib.parse import urlsplit, urlunsplit, parse_qs, parse_qsl, urlencode

from . import storage
from .sources.campus_social import school_context

FORMAT = 'ecust-xhs-visible-v1'
KEY = 'xhs-browser:visible:v1'
PAIR_KEY = 'xhs-browser:pair:v1'
RETENTION = 14 * 86400
_refresh_lock = threading.Lock()
_refresh_state = {'state': 'idle'}
_state_lock = threading.Lock()


def note_url(value):
    if not isinstance(value, str) or len(value) > 4096:return ''
    try:
        u = urlsplit(value)
        if u.scheme != 'https' or u.hostname not in ('www.xiaohongshu.com', 'xiaohongshu.com') or u.username or u.password or u.port not in (None, 443):return ''
        match = re.fullmatch(r'/(?:explore|search_result|discovery/item)/([a-fA-F0-9]{24})/?', u.path)
        if not match:return ''
        params = [(k, v) for k, v in parse_qsl(u.query) if k in ('xsec_token', 'xsec_source', 'source') and len(v) <= 1024]
        return urlunsplit(('https', 'www.xiaohongshu.com', '/explore/' + match[1].lower(), urlencode(params), ''))
    except ValueError:return ''


def clean_text(value, limit):
    if not isinstance(value, str) or len(value) > limit or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', value):return ''
    return value.strip()


def validate(payload, now=None):
    now = int(time.time()) if now is None else now
    if not isinstance(payload, dict) or set(payload) - {'format', 'captured_at', 'page_url', 'items'} or payload.get('format') != FORMAT:
        raise ValueError('请选择本机采集助手导出的校园笔记文件')
    captured = payload.get('captured_at')
    if isinstance(captured, bool) or not isinstance(captured, (int, float)) or not math.isfinite(captured) or not now - 7 * 86400 <= captured <= now + 300:
        raise ValueError('文件采集时间无效或已超过七天，请重新读取搜索结果')
    try:
        if not isinstance(payload.get('page_url'),str):raise ValueError()
        u = urlsplit(payload.get('page_url') or '')
        if u.scheme != 'https' or u.hostname not in ('www.xiaohongshu.com', 'xiaohongshu.com') or u.username or u.password or u.port not in (None,443) or u.path.rstrip('/') != '/search_result':raise ValueError()
        keyword = parse_qs(u.query).get('keyword', [''])[0][:80]
        if not school_context(keyword):raise ValueError()
    except (ValueError, TypeError):raise ValueError('请在小红书搜索华理相关内容后导出文件') from None
    raw = payload.get('items')
    if not isinstance(raw, list) or not 1 <= len(raw) <= 30:raise ValueError('每次同步支持一至三十条已加载的笔记卡片')
    seen = {}; rejected = 0
    for item in raw:
        if not isinstance(item, dict) or set(item) - {'url','title','excerpt'}:
            rejected += 1;continue
        link = note_url(item.get('url'))
        title = clean_text(item.get('title'), 240)
        excerpt = clean_text(item.get('excerpt',''), 1200)
        if not link or not title or not school_context(title + ' ' + excerpt):
            rejected += 1;continue
        identity = urlsplit(link).path.rsplit('/',1)[-1]
        seen[identity] = {'id':identity, 'url':link, 'title':title, 'excerpt':excerpt, 'captured_at':int(captured)}
    if not seen:raise ValueError('文件中没有可收录的华理笔记，请确认搜索卡片已经加载')
    return list(seen.values()), rejected


def _read(blob):
    try:
        data = json.loads(blob) if blob else {}
        return data if isinstance(data,dict) and isinstance(data.get('notes',{}),dict) else {}
    except (ValueError,TypeError):return {}


def save(payload, username):
    now = int(time.time()); notes, rejected = validate(payload, now)
    with storage.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT value FROM kv WHERE key=?',(KEY,)).fetchone()
        data = _read(row['value'] if row else None)
        existing = {k:v for k,v in data.get('notes',{}).items() if isinstance(v,dict) and v.get('last_imported_at',0) >= now-RETENTION}
        added = 0
        for note in notes:
            old = existing.get(note['id'], {})
            added += not bool(old)
            existing[note['id']] = dict(note, first_imported_at=old.get('first_imported_at',now), last_imported_at=now, imported_by=username)
        existing = dict(sorted(existing.items(),key=lambda x:x[1]['last_imported_at'],reverse=True)[:500])
        value = {'notes':existing,'last_imported_at':now,'last_import_count':len(notes),'last_auto_push_at':data.get('last_auto_push_at',0)}
        conn.execute('INSERT INTO kv(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(KEY,json.dumps(value,ensure_ascii=False).encode()))
    return {'received':len(notes),'added':added,'updated':len(notes)-added,'rejected':rejected,'stored':len(existing)}


def items():
    now = int(time.time()); data = _read(storage.kv_get(KEY)); results = []
    for value in sorted((n for n in data.get('notes',{}).values() if isinstance(n,dict)),key=lambda n:n.get('last_imported_at',0),reverse=True):
        if not isinstance(value,dict) or value.get('last_imported_at',0) < now-7*86400:continue
        link = note_url(value.get('url'))
        text = str(value.get('title','')) + ('\n'+value['excerpt'] if value.get('excerpt') else '')
        if not link or not school_context(text):continue
        results.append({'source':'xiaohongshu-school','rank':len(results)+1,'title':value['title'],'url':link,
            'extra':{'link':link,'content':text,'content_kind':'browser_card','collection_method':'user_browser_export',
                     'browser_captured_at':value['captured_at'],'browser_imported_at':value['first_imported_at'],
                     'published':None,'comments':None,'likes':None,'exposure':None,'circle':'华理公开笔记 · 本机登录同步'}})
        if len(results)>=200:break
    return results


def status():
    data = _read(storage.kv_get(KEY))
    with _state_lock:refresh = dict(_refresh_state)
    pair = pair_config()
    return {'mode':'local_browser_sync','paired':bool(pair.get('digest')),'pair_expires_at':pair.get('expires_at'),
            'last_auto_push_at':data.get('last_auto_push_at'),'stored':len(items()),'last_imported_at':data.get('last_imported_at'),
            'last_import_count':data.get('last_import_count',0),'refresh':refresh}


def pair_config():
    try:
        value=json.loads(storage.kv_get(PAIR_KEY) or '{}')
        return value if isinstance(value,dict) else {}
    except (ValueError,TypeError):return {}


def rotate_pair(username):
    token='ecust_xhs_'+secrets.token_urlsafe(32)
    expires=int(time.time())+90*86400
    storage.kv_set(PAIR_KEY,json.dumps({'digest':hashlib.sha256(token.encode()).hexdigest(),
                                      'owner':username,'expires_at':expires}).encode())
    return {'token':token,'expires_at':expires}


def revoke_pair():
    storage.kv_set(PAIR_KEY,b'{}')


def token_owner(authorization):
    """Single-purpose upload credential; never an administrator login session."""
    if not isinstance(authorization,str) or not authorization.startswith('Bearer ecust_xhs_') or len(authorization)>200:return ''
    pair=pair_config()
    if not pair.get('digest') or pair.get('expires_at',0)<=time.time():return ''
    digest=hashlib.sha256(authorization[7:].encode()).hexdigest()
    if not hmac.compare_digest(digest,pair['digest']):return ''
    from utils import access
    owner=pair.get('owner','')
    if owner in access.admin_usernames() and owner in access.server_accounts():return owner
    from . import accounts
    account=accounts.get(owner)
    return owner if account and not account['disabled'] and account['role']=='admin' else ''


def auto_push(payload,owner):
    # Browser alarm defaults to six hours; this bound also prevents accidental retry storms.
    now=int(time.time())
    with _auto_push_lock:
        data=_read(storage.kv_get(KEY))
        if now-data.get('last_auto_push_at',0)<300:raise RuntimeError('刚刚已完成同步，请五分钟后再试')
        result=save(payload,owner)
        with storage.connect() as conn:
            row=conn.execute('SELECT value FROM kv WHERE key=?',(KEY,)).fetchone()
            value=_read(row['value'] if row else None);value['last_auto_push_at']=now
            conn.execute('UPDATE kv SET value=? WHERE key=?',(json.dumps(value,ensure_ascii=False).encode(),KEY))
        return result


_auto_push_lock=threading.Lock()


def request_refresh():
    if not _refresh_lock.acquire(blocking=False):return
    with _state_lock:_refresh_state.update(state='waiting',message='文件已接收，等待当前采集结束')
    def work():
        from . import pipeline
        try:
            for _ in range(46):
                if not pipeline.status().get('running'):break
                time.sleep(2)
            if pipeline.status().get('running'):
                with _state_lock:_refresh_state.update(state='pending',message='文件已保存，将随下一轮采集纳入统计')
                return
            with _state_lock:_refresh_state.update(state='running',message='正在更新校园统计')
            result = pipeline.run_once(use_llm=False)
            with _state_lock:
                _refresh_state.update(state='complete' if not (result.get('error') or result.get('skipped')) else 'pending',
                    message='采集完成，可刷新数据账本查看' if not (result.get('error') or result.get('skipped')) else '文件已保存，等待下一轮采集')
        except Exception:
            with _state_lock:_refresh_state.update(state='pending',message='文件已保存，等待下一轮采集')
        finally:_refresh_lock.release()
    try:threading.Thread(target=work,daemon=True,name='xhs-browser-refresh').start()
    except Exception:_refresh_lock.release();raise
