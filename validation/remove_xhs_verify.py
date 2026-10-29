"""Read-only checks of the deployed removal; does not collect, generate or email."""
import json,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code=r'''import json,urllib.request,urllib.error,time
from CampusPulse.source_policy import public_payload
from CampusPulse import collection_queue

def read(path):
 with urllib.request.urlopen('http://127.0.0.1:5000'+path,timeout=60) as r:return json.load(r)
checks={}
for name,path in [('overview','/pulse/api/revision/overview'),('hot','/pulse/api/revision/feed/hot'),('ledger','/pulse/api/revision/ledger'),('posts','/pulse/api/revision/posts?limit=3'),('official_news','/pulse/api/revision/official-news'),('status','/pulse/api/status')]:
 data=read(path);assert public_payload(data)==data,name
 checks[name]=True
for path,expected in [('/pulse/api/xhs-browser/status',410),('/pulse/api/xhs-browser/push',410),('/static/js/campus-xhs-sync.js',404),('/static/downloads/ecust-xhs-browser-helper.zip',404)]:
 try: status=urllib.request.urlopen('http://127.0.0.1:5000'+path,timeout=10).status
 except urllib.error.HTTPError as e:status=e.code
 assert status==expected,(path,status)
 checks[path]=status
queue=collection_queue.status();assert queue['available'] and queue['worker_alive'],queue
checks['collection_worker_alive']=True
print(json.dumps(checks))
'''
remote='import subprocess,sys\nr=subprocess.run('+repr(['sudo','-n','docker','exec','bettafish','python','-c',code])+',capture_output=True,timeout=240)\nsys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)'
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n python3 -'],input=remote.encode(),capture_output=True,timeout=260)
if r.returncode:print(r.stderr.decode(errors='replace')[-2000:]);raise SystemExit(r.returncode)
result=json.loads(r.stdout);(repo/'validation/remove-xhs-live-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
