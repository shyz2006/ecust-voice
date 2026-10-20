"""Check production health and work in progress before the app-only release."""
import json,pathlib,subprocess,shlex
repo=pathlib.Path(__file__).resolve().parents[1]
code=r'''
import os,json,urllib.request
from flask import Flask
from flask.sessions import SecureCookieSessionInterface
from utils.research_runner import active_research_tasks,queued_tasks
from utils.task_runtime import list_task_ids
active=active_research_tasks();queued=queued_tasks()
app=Flask('release-preflight');app.secret_key=os.environ['WEB_SESSION_SECRET']
cookie=SecureCookieSessionInterface().get_signing_serializer(app).dumps({'authenticated':True,'username':os.environ['WEB_AUTH_USERNAME']})
reporting=[]
for task in list_task_ids():
 req=urllib.request.Request('http://127.0.0.1:5000/api/report/status?task_id='+task,headers={'Cookie':'session='+cookie})
 with urllib.request.urlopen(req,timeout=15) as response:data=json.load(response)
 current=data.get('current_task') or {}
 if current.get('status') in ('running','pending'):reporting.append(task)
with urllib.request.urlopen('https://smydashuaige.2026515.xyz/login',timeout=30) as response:healthy=response.status==200
assert healthy and not active and not queued and not reporting,'Production work is active; defer recreation'
print(json.dumps({'passed':True,'https_login':healthy,'active_research':len(active),'queued_research':len(queued),'active_reports':len(reporting)}))
'''
args=['sudo','-n','docker','exec','-i','bettafish','python','-']
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(args)],input=code.encode(),capture_output=True,timeout=180)
if r.returncode:print(r.stderr.decode(errors='replace')[-1200:]);raise SystemExit(r.returncode)
result=json.loads(r.stdout)
(repo/'validation/teacher-preflight-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result))
