"""Real candidate API acceptance in a temporary DB; only existing free model."""
import base64,pathlib,subprocess,json
repo=pathlib.Path(__file__).resolve().parent.parent
source=base64.b64encode((repo/'production/CampusPulse/blueprint.py').read_bytes()).decode()
script='''
import base64,types,json,tempfile,pathlib,time,os
from flask import Flask
from loguru import logger
logger.remove()
from CampusPulse.config import settings,refresh_runtime
from CampusPulse import llm,storage
refresh_runtime()
assert 'free' in (settings.llm_model or '').lower(), 'Free model required'
model=settings.llm_model
# Disable cross-model failover for this isolated acceptance process.
llm.ModelFailover=None;llm._failover=None;settings.llm_timeout=60
with tempfile.TemporaryDirectory(prefix='workshop-model-acceptance-') as sandbox:
 settings.db_path=pathlib.Path(sandbox)/'acceptance.db'
 module=types.ModuleType('CampusPulse.candidate');module.__file__='/app/CampusPulse/blueprint.py'
 exec(compile(base64.b64decode(SOURCE),module.__file__,'exec'),module.__dict__)
 app=Flask('model_acceptance');app.secret_key='isolated-test-only';app.register_blueprint(module.pulse_bp,url_prefix='/pulse')
 client=app.test_client()
 query='在尚无学校真实数据的情况下，如何核实校园食堂晚间服务需求？请提供核查步骤，将未知事实标为待核实，不虚构学校情况。'
 response=client.post('/pulse/api/analyze',json={'query':query,'intent':'event_brief','workflow':'lean','analysis_options':{'thinking_effort':'quick','psych_lens':'needs','ideology':'evidence'}})
 assert response.status_code==200
 job_id=response.json['job_id'];deadline=time.monotonic()+180
 while time.monotonic()<deadline:
  job=client.get('/pulse/api/job/'+job_id).json
  if job['status']!='running': break
  time.sleep(2)
 result=job.get('result') or {}
 readable=False;report=None
 if result.get('id'):
  saved=client.get('/pulse/api/analysis/'+str(result['id']))
  readable=saved.status_code==200 and saved.json.get('success') and bool(saved.json.get('result'))
  report=saved.json if readable else None
 data={'passed':job['status']=='done' and readable and not result.get('degraded'),'status':job['status'],'model':model,'database':'temporary; no production writes','readable':bool(readable),'result_status':result.get('status'),'usage':result.get('usage'),'report':report,'error_present':bool(job.get('error'))}
 print(json.dumps(data,ensure_ascii=False))
'''.replace('SOURCE',repr(source))
key=repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'
command=[r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(key),'-o','BatchMode=yes','ubuntu@3.144.33.23','sudo -n docker exec -i bettafish python -']
result=subprocess.run(command,input=script.encode(),capture_output=True,timeout=220)
if result.returncode:
    print(json.dumps({'passed':False,'reason':'isolated execution failed','exit_code':result.returncode}));raise SystemExit(1)
data=json.loads(result.stdout)
out=repo.parent/'validation-artifacts';out.mkdir(exist_ok=True)
(out/'real-model-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in data.items() if k!='report'},ensure_ascii=False))
