"""Replay saved real service outputs through the final evidence gate; no paid calls."""
import pathlib,json,subprocess,shlex
repo=pathlib.Path(__file__).resolve().parent.parent
payload=json.loads((repo/'validation/workshop-intent-live-results.json').read_text(encoding='utf-8'))
code=r"""
import json
from loguru import logger
logger.remove()
from CampusPulse.research_brief import validate
rows=json.loads(DATA)['results'];checks=[]
for r in rows:
 directions,question=validate({'directions':r['directions'],'question':r.get('question')},r['query'],r['context'],r['sources'],ambiguous=not bool(r['context']))
 if r['query']=='武汉大学内战' and not r['context']:assert not directions
 else:assert directions
 checks.append({'query':r['query'],'supplemented':bool(r['context']),'directions':[d['title'] for d in directions],'needs_context':not bool(directions)})
print(json.dumps({'passed':True,'checks':checks,'new_model_calls':0,'new_search_calls':0,'full_reports_started':0,'emails_sent':0},ensure_ascii=False))
""".replace('DATA',repr(json.dumps(payload,ensure_ascii=False)))
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(['sudo','-n','docker','run','--rm','-i','--network','none','--entrypoint','python','bettafish:candidate-workshop-intent-20261021','-'])],input=code.encode(),capture_output=True,timeout=90)
if r.returncode:print(r.stderr.decode(errors='replace')[-1500:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/workshop-intent-live-revalidation.json').write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(data,ensure_ascii=False))
