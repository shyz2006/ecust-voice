"""Validate candidate API in a fresh container process, without production writes."""
import base64, pathlib, subprocess, json
repo=pathlib.Path(__file__).resolve().parent.parent
source=base64.b64encode((repo/'production/CampusPulse/blueprint.py').read_bytes()).decode()
script='''
import base64,types,json,tempfile,pathlib,unittest.mock as mock
from flask import Flask
from loguru import logger
logger.remove()
from CampusPulse.config import settings
settings.db_path=pathlib.Path(tempfile.mkdtemp(prefix='workshop-validation-'))/'isolated.db'
module=types.ModuleType('CampusPulse.candidate');module.__file__='/app/CampusPulse/blueprint.py'
exec(compile(base64.b64decode(SOURCE),module.__file__,'exec'),module.__dict__)
app=Flask('candidate');app.secret_key='isolated-test-only';app.register_blueprint(module.pulse_bp,url_prefix='/pulse')
client=app.test_client();checks=[]
for payload in ({'query':''},{'query':'问'*201},{'query':['问']},['invalid'],{'query':'问','analysis_options':{'thinking_effort':'invalid'}}):
 response=client.post('/pulse/api/analyze',json=payload);assert response.status_code==400;checks.append('invalid input rejected')
class ImmediateThread:
 def __init__(self,target,**kw): self.target=target
 def start(self): self.target()
for effort,workflow in [('quick','lean'),('standard','lean_verified'),('deep','central_verified')]:
 module._jobs.clear()
 with mock.patch.object(module,'Orchestrator') as orch, mock.patch.object(module.threading,'Thread',ImmediateThread):
  orch.return_value.run.return_value={'id':77,'summary':'mock result','degraded':False}
  payload={'query':'问'*200,'intent':'activity_design','workflow':workflow,'analysis_options':{'thinking_effort':effort,'psych_lens':'needs','ideology':'actions'}}
  response=client.post('/pulse/api/analyze',json=payload);assert response.status_code==200
  orch.return_value.run.assert_called_once_with(payload['query'],'activity_design',workflow,analysis_options=payload['analysis_options'])
  job=client.get('/pulse/api/job/'+response.json['job_id']).json;assert job['status']=='done' and job['result']['id']==77
  checks.append('workflow and options: '+effort)
module._jobs.clear()
with mock.patch.object(module,'Orchestrator') as orch,mock.patch.object(module.threading,'Thread',ImmediateThread):
 orch.return_value.run.return_value={'degraded':True,'trace':[]}
 response=client.post('/pulse/api/analyze',json={'query':'验证问题'});job=client.get('/pulse/api/job/'+response.json['job_id']).json;assert job['status']=='error';checks.append('degraded model remains failure')
module._jobs={str(i):{'id':str(i),'status':'running'} for i in range(module._MAX_CONCURRENT)}
assert client.post('/pulse/api/analyze',json={'query':'验证问题'}).status_code==429;checks.append('capacity rejected with 429')
assert client.get('/pulse/api/job/missing').status_code==404;checks.append('expired job 404')
print(json.dumps({'passed':True,'checks':checks,'database':'isolated','model':'mock'},ensure_ascii=False))
'''.replace('SOURCE',repr(source))
workspace=repo.parent.parent
key=workspace/'亚马逊云 美国/aws-us-yzjp1test.pem'
command=[r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(key),'-o','BatchMode=yes','ubuntu@3.144.33.23','sudo -n docker exec -i bettafish python -']
result=subprocess.run(command,input=script.encode(),capture_output=True,timeout=90)
if result.returncode:
    print(result.stderr.decode(errors='replace')[-2000:]);raise SystemExit(result.returncode)
data=json.loads(result.stdout)
out=repo.parent/'validation-artifacts';out.mkdir(exist_ok=True)
(out/'backend-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False))
