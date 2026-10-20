"""Compare a correctly named, already configured fallback model in isolation only."""
import pathlib,subprocess,json,sys
repo=pathlib.Path(__file__).resolve().parents[1]
remote=r'''
import pathlib,subprocess,json
stage=pathlib.Path('/home/ubuntu/bettafish/deploy/campus-polish-20261020')
for p in ['ReportEngine/evidence.py','ReportEngine/prompts/prompts.py','CampusPulse/research.py','utils/llm_failover.py']:
 subprocess.run(['sudo','-n','docker','cp',str(stage/'files'/p),'bettafish-campus-v3-validation:/app/'+p],check=True,capture_output=True)
code=r"""
import os,pathlib,json,shutil,time
os.environ.update(BETTAFISH_RUNTIME_DIR=os.environ['VALIDATION_RUNTIME_DIR'],BETTAFISH_TASK_ID='task_7076385147e441a28f99f3835b173086',
 LLM_SLOT_DIR='/tmp/campus-v3-quality-slots',LLM_STATS_FILE='/tmp/campus-v3-quality-stats.json',LLM_ADAPTIVE_ROUTING='0',
 REPORT_CHAPTER_CONCURRENCY='1',LLM_REQUEST_TIMEOUT='120',LLM_OUTAGE_MAX_WAIT='0')
from loguru import logger
logger.remove();logger.add('/tmp/campus-v3-quality.log')
root=pathlib.Path(os.environ['VALIDATION_RUNTIME_DIR']);old=root/'task_30697c6ad83d481ea2eb9067de6c6ced';task='task_7076385147e441a28f99f3835b173086';target=root/task
assert not target.exists(),'Do not overwrite a comparison run'
shutil.copytree(old,target,ignore=lambda folder,names:['report'] if pathlib.Path(folder)==old/'outputs' else [])
progress=target/'quality-progress.json';progress.write_text(json.dumps({'status':'running','progress':0}))
from ReportEngine.flask_interface import _build_task_report_config
from ReportEngine.agent import create_agent
from utils.task_runtime import task_output_dir,register_task_account
register_task_account(task,'isolated-validator')
cfg=_build_task_report_config(task);cfg.REPORT_ENGINE_MODEL_NAME='deepseek/deepseek-v4-pro'
agent=create_agent(config=cfg,task_id=task);agent.llm_client.failover.models=['deepseek/deepseek-v4-pro']
reports=[max(task_output_dir(task,e).glob('*.md'),key=lambda p:p.stat().st_mtime).read_text(encoding='utf-8') for e in ('query','media','insight')]
def event(kind,data):
 if kind=='progress':progress.write_text(json.dumps({'status':'running','progress':data.get('progress',0)}))
try:
 agent.generate_report('鹅腿阿姨事件',reports,custom_template=pathlib.Path('ReportEngine/report_template/校园与青年事件分析报告模板.md').read_text(encoding='utf-8'),research_task_id=task,stream_handler=event)
 assert agent.llm_client.failover.active_model=='deepseek/deepseek-v4-pro'
 result={'status':'completed','progress':100,'task_id':task,'model':agent.llm_client.failover.active_model,'production_configuration_changed':False}
except Exception as exc:
 result={'status':'failed','error_type':type(exc).__name__,'http_status':getattr(exc,'status_code',None)}
progress.write_text(json.dumps(result));print(json.dumps(result))
"""
r=subprocess.run(['sudo','-n','docker','exec','-i','bettafish-campus-v3-validation','python','-'],input=code.encode(),capture_output=True,timeout=900)
if r.returncode:print(json.dumps({'process_failed':True,'exit_code':r.returncode}));raise SystemExit(1)
print(r.stdout.decode())
'''
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','-o','ServerAliveInterval=20','ubuntu@3.17.59.150','python3 -'],input=remote.encode(),capture_output=True,timeout=960)
if r.returncode:print(r.stdout.decode(errors='replace')[-800:]);print(r.stderr.decode(errors='replace')[-800:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
(repo.parent/'validation-artifacts/campus-v3/quality-run.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps(data))
