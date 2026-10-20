"""Read-only production checks; signing credentials and cookies stay inside the container."""
import pathlib,subprocess,json,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=pathlib.Path(__file__).resolve().parent.parent
manifest=json.loads((repo/'validation/campus-v3-release-manifest.json').read_text(encoding='utf-8'))
expected={x['path']:x['candidate_sha256'] for x in manifest['files']}
code=r'''
import os,json,hashlib,time,urllib.request,urllib.error
from pathlib import Path
from flask import Flask
from flask.sessions import SecureCookieSessionInterface
expected=EXPECTED
assert all(hashlib.sha256((Path('/app')/path).read_bytes()).hexdigest()==digest for path,digest in expected.items())
app=Flask('readonly-release-check');app.secret_key=os.environ['WEB_SESSION_SECRET']
cookie=SecureCookieSessionInterface().get_signing_serializer(app).dumps({'authenticated':True,'username':os.environ['WEB_AUTH_USERNAME']})
base='https://smydashuaige.2026515.xyz';timings={}
from urllib.parse import urlsplit
class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  if urlsplit(newurl).hostname!='smydashuaige.2026515.xyz' or urlsplit(newurl).scheme!='https':raise RuntimeError('Unexpected redirect origin')
  return super().redirect_request(req,fp,code,msg,headers,newurl)
opener=urllib.request.build_opener(SameOriginRedirect())
def fetch(path):
 started=time.monotonic();request=urllib.request.Request(base+path,headers={'Cookie':'session='+cookie,'Cache-Control':'no-cache'})
 with opener.open(request,timeout=60) as response:
  content=response.read();headers=dict(response.headers)
 timings[path.split('?')[0]]=round(time.monotonic()-started,3)
 return content,headers
def api(path):
 raw,headers=fetch('/pulse/api/revision/'+path)
 assert headers.get('Cache-Control')=='no-store'
 value=json.loads(raw);assert value.get('success') is True
 return value
home,_=fetch('/');pulse,_=fetch('/pulse/');assert home.strip()==pulse.strip()
assert 'campus-review.js'.encode() in home and b'pulse-theme-script' not in home
for path in ['static/css/campus-play.css','static/js/campus-review.js','static/js/campus-play.js']:
 content,_=fetch('/'+path+'?v=20261020p2');assert hashlib.sha256(content).hexdigest()==expected[path]
data=api('overview');assert len(data['taxonomy'])==len(data['themes'])==12
assert sum(t['posts'] for t in data['themes'])==data['total']
assert sum(t['posts_7d'] for t in data['themes'])==data['total_7d']
assert all(t['reference']['value'] is None or type(t['reference']['value']) is int for t in data['themes'])
from urllib.parse import urlencode
first=data['themes'][0];posts=api('posts?'+urlencode({'theme':first['theme']}));assert posts['total']==first['posts']
ledger=api('ledger');assert not {'cost','pricing','national'}&set(ledger)
assert all(x['source']!='huyou-national' for x in ledger['sources'])
hot=api('feed/hot');memes=api('feed/memes');assert hot['platforms']==['抖音','澎湃','B站','头条'] and memes['platforms']==['B站','抖音','微博','百度']
from collections import Counter
assert Counter(x['platform'] for x in hot['items'])==Counter({p:10 for p in hot['platforms']})
assert Counter(x['platform'] for x in memes['items'])==Counter({p:10 for p in memes['platforms']})
assert all(x.get('reference_url') and x.get('search_url') for x in memes['items'])
from ReportEngine.utils.config import Settings
report_model=Settings().REPORT_ENGINE_MODEL_NAME
assert report_model=='minimax/minimax-m3.1-flash:free'
assert '/static/js/campus-play.js'.encode() in home
assert fetch('/static/img/pulse-dachshund.webp')[0][:4]==b'RIFF'
history=api('research');assert 'items' in history
try:fetch('/validation/login')
except urllib.error.HTTPError as exc:assert exc.code==404
else:raise AssertionError('Validation login must not be deployed')
print(json.dumps({'passed':True,'public_https':True,'source_hashes_verified':True,'twelve_categories':True,'count_conservation':True,
 'real_post_links':sum(bool(p.get('link')) for p in posts['posts']),'hot_records':len(hot['items']),'meme_records':len(memes['items']),
 'integer_post_reference':True,'ten_per_platform':True,'meme_reference_search_distinguished':True,'original_dachshund_present':True,'report_model':report_model,'own_research_history':True,'validation_login_absent':True,'requests':'GET only','timings_seconds':timings},ensure_ascii=False))
'''.replace('EXPECTED',repr(expected))
import shlex
args=['sudo','-n','docker','exec','-i','bettafish','python','-']
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(args)],input=code.encode(),capture_output=True,timeout=180)
if r.returncode:print(r.stderr.decode(errors='replace')[-1600:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/campus-v3-postdeploy-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(data,ensure_ascii=False))
