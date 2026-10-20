"""Isolated regression: re-search the named subject, reuse saved research, regenerate report."""
import pathlib,subprocess,json,sys
repo=pathlib.Path(__file__).resolve().parents[1]
out=repo.parent/'validation-artifacts/campus-v3'
old=json.loads((out/'audit.json').read_text(encoding='utf-8'))['goose_tasks'][0]['task']
task='task_30697c6ad83d481ea2eb9067de6c6ced'
if len(sys.argv)>1 and sys.argv[1]=='poll':
 code=r'''
import json,urllib.request
data=json.load(urllib.request.urlopen('http://127.0.0.1:15003/api/report/status?task_id=TASK',timeout=30))
t=data.get('current_task') or {}
print(json.dumps({k:t.get(k) for k in ('status','progress','error_message')},ensure_ascii=False))
'''.replace('TASK',task)
else:
 code=r'''
import json,pathlib,subprocess,urllib.request
old=OLD;task=TASK
stage=pathlib.Path('/home/ubuntu/bettafish/deploy/campus-polish-20261020')
target=stage/'validation-runtime'/task
find="from utils.task_runtime import task_dir;print(str(task_dir('"+old+"').resolve()))"
source=subprocess.check_output(['sudo','-n','docker','exec','-i','bettafish','python','-'],input=find.encode()).decode().strip()
if not target.exists():
 target.mkdir(parents=True)
 for relative in ['metadata.json','outputs/query','outputs/media','outputs/insight','runs']:
  dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
  subprocess.run(['sudo','-n','docker','cp','bettafish:'+source+'/'+relative,str(dest)],check=True,capture_output=True)
else:assert (target/'metadata.json').is_file() and not (target/'outputs/report').exists(),'Do not overwrite a report run'
seed=r"""
import os,pathlib,json
task=TASK
os.environ.update(BETTAFISH_RUNTIME_DIR=os.environ['VALIDATION_RUNTIME_DIR'],BETTAFISH_TASK_ID=task,
 SEARCH_GATEWAY_DB='/tmp/campus-v3-regression-search.sqlite3',LLM_SLOT_DIR='/tmp/campus-v3-regression-slots',LLM_STATS_FILE='/tmp/campus-v3-regression-stats.json')
from CampusPulse.config import settings
settings.db_path=list(pathlib.Path('/tmp').glob('campus-v3-validation-*/campus.db'))[-1]
from utils.task_runtime import register_task_account,read_task_metadata
register_task_account(task,'isolated-validator')
from SingleEngineApp.research_worker import build_agent
from utils.topic_guard import prepare_agent
agent=build_agent('query',task)
assert prepare_agent(agent,'query','鹅腿阿姨事件',task)
assert all('鹅腿阿姨' in p.title for p in agent.state.paragraphs)
agent._initial_search_and_summary(0)
agent._save_report(agent.state.paragraphs[0].research.latest_summary)
from ReportEngine.evidence import source_evidence
records=source_evidence(task)
assert len(records)>=2 and all('鹅腿阿姨' in (x['title']+x['excerpt']) for x in records)
print(json.dumps({'fresh_search_and_first_summary':True,'grounded_outline':[p.title for p in agent.state.paragraphs],
 'relevant_sources':len(records),'source_titles':[x['title'] for x in records[:12]]},ensure_ascii=False))
""".replace('task=TASK','task='+repr(task))
r=subprocess.run(['sudo','-n','docker','exec','-i','bettafish-campus-v3-validation','python','-'],input=seed.encode(),capture_output=True,timeout=900)
if r.returncode:print(r.stderr.decode(errors='replace')[-1200:]);raise SystemExit(r.returncode)
result=json.loads(r.stdout)
req=urllib.request.Request('http://127.0.0.1:15003/api/report/generate',data=json.dumps({'research_task_id':task,'query':'鹅腿阿姨事件','regenerate':True}).encode(),headers={'Content-Type':'application/json'})
generated=json.load(urllib.request.urlopen(req,timeout=30));assert generated['success']
result.update(report_task_id=generated['task_id'],research_task_id=task,materials_reused=True)
print(json.dumps(result,ensure_ascii=False))
'''.replace('old=OLD;task=TASK','old='+repr(old)+';task='+repr(task))
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','-o','ServerAliveInterval=20','ubuntu@3.17.59.150','python3 -'],input=code.encode(),capture_output=True,timeout=960)
if r.returncode:print(r.stdout.decode(errors='replace')[-1400:]);print(r.stderr.decode(errors='replace')[-1200:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
(out/('goose-status.json' if len(sys.argv)>1 else 'goose-run.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(data,ensure_ascii=False))
