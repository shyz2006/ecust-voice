"""Read-only production validation; credentials/cookies remain inside the server."""
import pathlib,subprocess,json,shlex,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=pathlib.Path(__file__).resolve().parent.parent
manifest=json.loads((repo/'validation/campus-followup-release-manifest.json').read_text(encoding='utf-8'))
expected={x['path']:x['candidate_sha256'] for x in manifest['files']}
code=r"""
import os,json,hashlib,urllib.request,urllib.error
from pathlib import Path
from flask import Flask
from flask.sessions import SecureCookieSessionInterface
expected=EXPECTED
assert all(hashlib.sha256((Path('/app')/p).read_bytes()).hexdigest()==v for p,v in expected.items())
app=Flask('readonly');app.secret_key=os.environ['WEB_SESSION_SECRET']
cookie=SecureCookieSessionInterface().get_signing_serializer(app).dumps({'authenticated':True,'username':os.environ['WEB_AUTH_USERNAME']})
base='https://smydashuaige.2026515.xyz'
from urllib.parse import urlsplit
class Redirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  assert urlsplit(newurl).hostname=='smydashuaige.2026515.xyz' and urlsplit(newurl).scheme=='https'
  return super().redirect_request(req,fp,code,msg,headers,newurl)
opener=urllib.request.build_opener(Redirect())
def fetch(path):
 req=urllib.request.Request(base+path,headers={'Cookie':'session='+cookie,'Cache-Control':'no-cache'})
 with opener.open(req,timeout=45) as r:return r.read(),r.headers
home,_=fetch('/');pulse,_=fetch('/pulse/');assert home.replace(b'\r\n',b'\n').strip()==pulse.replace(b'\r\n',b'\n').strip()
assert 'researchRefine' in home.decode() and 'researchContext' in home.decode();assert '比如：这里的' not in home.decode()
for p in ['static/js/campus-review.js','static/css/campus-play.css']:
 body,_=fetch('/'+p+'?v=20261021p3');assert hashlib.sha256(body).hexdigest()==expected[p]
checks=[]
for p in ['overview','feed/hot','feed/memes','ledger','research','weekly']:
 raw,headers=fetch('/pulse/api/revision/'+p);value=json.loads(raw);assert value['success'] and headers.get('Cache-Control')=='no-store';checks.append(p)
 if p=='overview':assert 'campus-topics-4' in value['methods']['classification']
req=urllib.request.Request(base+'/pulse/api/revision/research/brief',data=b'{}',headers={'Cookie':'session='+cookie,'Content-Type':'application/json'})
try:opener.open(req,timeout=25)
except urllib.error.HTTPError as e:assert e.code==400 and json.loads(e.read())['success'] is False
else:raise AssertionError('Empty preparation accepted')
print(json.dumps({'passed':True,'files_verified':len(expected),'root_and_pulse_match':True,'public_static_hashes':True,'authenticated_reads':checks,'invalid_preparation_rejected':True,'model_calls':0,'search_calls':0,'emails_sent':0}))
""".replace('EXPECTED',repr(expected))
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(['sudo','-n','docker','exec','-i','bettafish','python','-'])],input=code.encode(),capture_output=True,timeout=320)
if r.returncode:print(r.stderr.decode(errors='replace')[-1200:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/campus-followup-postdeploy-results.json').write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(data))
