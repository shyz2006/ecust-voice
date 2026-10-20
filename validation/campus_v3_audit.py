"""Read-only audit of deployed classifications, feeds and the user's research evidence."""
import pathlib,subprocess,json,shlex
repo=pathlib.Path(__file__).resolve().parents[1]
out=repo.parent/'validation-artifacts/campus-v3';out.mkdir(parents=True,exist_ok=True)
code=r'''
import json,pathlib
from CampusPulse import revision,storage
from utils.task_runtime import list_task_ids,read_task_metadata,task_output_dir
data=revision.snapshot()
tasks=[]
def records(value):
 if isinstance(value,list):
  for child in value:yield from records(child)
 elif isinstance(value,dict):
  selected={k:value[k] for k in ('url','title','content','snippet','query','search_query') if isinstance(value.get(k),str)}
  if selected:yield selected
  for child in value.values():
   if isinstance(child,(list,dict)):yield from records(child)
for task in list_task_ids():
 meta=read_task_metadata(task)
 if '鹅腿' not in str(meta.get('query','')):continue
 engines={}
 for engine in ('query','media','insight'):
  engines[engine]=[]
  for path in task_output_dir(task,engine).glob('state_*.json'):
   engines[engine]+=list(records(json.loads(path.read_text(encoding='utf-8'))))
 tasks.append({'task':task,'query':meta.get('query'),'engines':engines})
feeds=storage.recent_items(list(revision.MEME_PLATFORMS),int(__import__('time').time())-7*86400)
print(json.dumps({'posts':data['posts'],'counts':{t['theme']:t['posts'] for t in data['themes']},'goose_tasks':tasks,'feed_rows':feeds},ensure_ascii=False))
'''
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(['sudo','-n','docker','exec','-i','bettafish','python','-'])],input=code.encode(),capture_output=True,timeout=180)
if r.returncode:print(r.stderr.decode(errors='replace')[-1000:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(out/'audit.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
print(json.dumps({'counts':data['counts'],'goose_tasks':[{'task':x['task'],'query':x['query'],'records':{k:len(v) for k,v in x['engines'].items()}} for x in data['goose_tasks']],'feed_rows':len(data['feed_rows'])},ensure_ascii=False))
