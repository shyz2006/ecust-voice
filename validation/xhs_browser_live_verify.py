"""Read-only endpoint probes using a temporary scoped key, restored afterward; no note upload."""
import hashlib,json,urllib.request,urllib.error
from pathlib import Path
from CampusPulse import storage,xhs_browser_import as bridge
from utils import access

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):return None

opener=urllib.request.build_opener(NoRedirect())
def probe(url,token=None):
    request=urllib.request.Request(url,headers={'Authorization':'Bearer '+token} if token else {})
    try:
        with opener.open(request,timeout=20) as response:return response.status,response.read()
    except urllib.error.HTTPError as exc:return exc.code,b''

result={'notes_uploaded':0,'model_calls':0,'emails_sent':0}
old=storage.kv_get(bridge.PAIR_KEY)
owner=next(iter(access.admin_usernames()))
pair=bridge.rotate_pair(owner);temporary=storage.kv_get(bridge.PAIR_KEY)
try:
    code,_=probe('https://smydashuaige.2026515.xyz/pulse/api/xhs-browser/ping',pair['token'])
    result['https_nginx_scoped_ping']=code;assert code==200
    code,_=probe('https://smydashuaige.2026515.xyz/api/config',pair['token'])
    result['token_denied_config']=code in (302,401,403);assert result['token_denied_config']
    code,_=probe('http://127.0.0.1:5000/pulse/api/xhs-browser/status')
    result['anonymous_loopback_denied']=code==401;assert code==401
    code,body=probe('http://127.0.0.1:5000/static/downloads/ecust-xhs-browser-helper.zip')
    result['helper_zip_http']=code;assert code==200
    assert hashlib.sha256(body).hexdigest()==hashlib.sha256(Path('/app/static/downloads/ecust-xhs-browser-helper.zip').read_bytes()).hexdigest()
    result['helper_zip_verified']=True
    code,body=probe('http://127.0.0.1:5000/static/js/campus-xhs-sync.js?v=20261026b1')
    result['ui_module_http']=code;assert code==200 and '本机定时同步'.encode() in body
    result['real_user_capture_verified']=False
finally:
    with storage.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        current=conn.execute('SELECT value FROM kv WHERE key=?',(bridge.PAIR_KEY,)).fetchone()
        if current and current['value']==temporary:
            if old is None:conn.execute('DELETE FROM kv WHERE key=?',(bridge.PAIR_KEY,))
            else:conn.execute('UPDATE kv SET value=? WHERE key=?',(old,bridge.PAIR_KEY))
    result['temporary_pair_restored']=storage.kv_get(bridge.PAIR_KEY)==old
print(json.dumps(result,ensure_ascii=True))
