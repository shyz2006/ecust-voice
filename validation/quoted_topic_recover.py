"""Recover only a specified failed task using previously fetched, rechecked sources."""
import json,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
task_id=sys.argv[1]
code=r'''import hashlib,json,os
from pathlib import Path
from utils.task_runtime import validate_runtime_id,read_task_metadata,task_metadata_path,task_output_dir,engine_run_status
from utils.topic_guard import subject,relevant
from utils import research_runner,search_gateway
from CampusPulse import storage
from CampusPulse.source_policy import retired_url
TASK=validate_runtime_id(TARGET)
meta=read_task_metadata(TASK);assert meta.get('pulse_revision')==2
assert all(engine_run_status(TASK,engine)!='running' for engine in ('query','media','insight')),'Task already running'
assert engine_run_status(TASK,'insight')=='completed','Preserve only a completed insight run'
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in task_output_dir(TASK,'insight').rglob('*') if p.is_file()}
brief=meta.get('research_brief') or {};topic=subject(str(meta.get('query') or ''));sources=[]
brief_id=brief.get('brief_id')
for record in storage.kv_prefix('research-brief:v1:',limit=10000):
 if not brief_id or not record['key'].endswith(':'+brief_id):continue
 try:raw=json.loads(record['value'])
 except (TypeError,ValueError):continue
 sources.extend(raw.get('sources') or [])
if not sources:
 connection=search_gateway._connect()
 try:records=connection.execute('SELECT payload FROM cache WHERE query LIKE ? ORDER BY created DESC LIMIT 12',('%'+(topic.get('quote_identity') or [meta['query']])[0]+'%',)).fetchall()
 finally:connection.close()
 for row in records:
  raw=json.loads(row[0]);root=raw.get('data') or raw
  if not isinstance(root,dict):continue
  for page in (root.get('webPages') or {}).get('value',[]):
   sources.append({'title':page.get('name') or page.get('title') or '', 'snippet':page.get('summary') or page.get('snippet') or '', 'url':page.get('url') or ''})
kept=[];seen=set()
for source in sources:
 url=source.get('url') or ''
 if url in seen or not url.startswith(('https://','http://')) or retired_url(url):continue
 if not relevant(str(source.get('title') or '')+' '+str(source.get('snippet') or ''),topic):continue
 seen.add(url);kept.append(source)
assert kept,'No cached relevant sources; do not restart an empty search'
path=task_metadata_path(TASK);backup=path.with_name('metadata.before-quoted-topic-recovery.json')
if not backup.exists():backup.write_bytes(path.read_bytes())
cap=search_gateway._cap(TASK)
meta['research_brief']=dict(brief,sources=kept)
temp=path.with_suffix('.quoted-recovery.tmp');temp.write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)
result=research_runner.rerun(TASK)
assert 'insight' not in result['engines']
assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in task_output_dir(TASK,'insight').rglob('*') if p.is_file()}
assert search_gateway._cap(TASK)==cap
print(json.dumps({'task_id':TASK,'reused_sources':len(kept),'restarted_engines':result['engines'],'insight_unchanged':True,'bocha_cap':cap,'claim_verification':'pending'}))
'''.replace('TARGET',repr(task_id))
remote='import subprocess,sys\nr=subprocess.run('+repr(['docker','exec','bettafish','python','-c',code])+',capture_output=True,timeout=50)\nsys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)'
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n python3 -'],input=remote.encode(),capture_output=True,timeout=70)
if r.returncode:print(r.stderr.decode(errors='replace')[-1800:]);raise SystemExit(r.returncode)
result=json.loads(r.stdout);(repo/'validation/quoted-topic-recovery-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
