"""Reuse completed isolated engine evidence after correcting the report template."""
import pathlib,json,base64,subprocess,sys
repo=pathlib.Path(__file__).resolve().parent.parent
out=repo.parent/'validation-artifacts/teacher';state=json.loads((out/'teacher-live-task.json').read_text(encoding='utf-8'))
old=state.get('original_task_id') or state['task_id']
template=base64.b64encode((repo/'production/ReportEngine/report_template/校园与青年事件分析报告模板.md').read_bytes()).decode()
remote=r'''
import subprocess,json
code=r"""import pathlib,json,shutil,hashlib,time,base64,urllib.request
old=OLD
roots=list(pathlib.Path('/tmp').glob('teacher-validation-*/runtime/'+old));assert len(roots)==1
source=roots[0];task='task_'+hashlib.sha256((old+'corrected-four-chapters').encode()).hexdigest()[:32]
target=source.parent/task
if not target.exists():
 shutil.copytree(source,target,ignore=lambda folder,names: ['report'] if pathlib.Path(folder)==source/'outputs' else [])
 p=target/'metadata.json';meta=json.loads(p.read_text());meta.update(task_id=task,created_at=time.time(),updated_at=time.time());p.write_text(json.dumps(meta,ensure_ascii=False))
meta=json.loads((target/'metadata.json').read_text())
pathlib.Path('/app/ReportEngine/report_template/校园与青年事件分析报告模板.md').write_bytes(base64.b64decode(TEMPLATE))
from ReportEngine.core import parse_template_sections
assert len(parse_template_sections(pathlib.Path('/app/ReportEngine/report_template/校园与青年事件分析报告模板.md').read_text()))==4
request=urllib.request.Request('http://127.0.0.1:15001/api/report/generate',data=json.dumps({'research_task_id':task,'query':meta['query']}).encode(),headers={'Content-Type':'application/json'})
result=json.load(urllib.request.urlopen(request,timeout=30))
assert result['success']
print(json.dumps({'task_id':task,'report_task_id':result['task_id'],'original_task_id':old,'materials_reused':True}))
""".replace('OLD',repr(OLD)).replace('TEMPLATE',repr(TEMPLATE))
r=subprocess.run(['sudo','-n','docker','exec','-i','bettafish-teacher-validation','python','-'],input=code.encode(),capture_output=True)
assert r.returncode==0,r.stderr.decode(errors='replace')[-1000:]
print(r.stdout.decode())
'''.replace('OLD',repr(old),1).replace('TEMPLATE',repr(template),1)
# Bind constants outside the nested source string, preserving its replacement code.
remote='OLD='+repr(old)+'\nTEMPLATE='+repr(template)+'\n'+remote
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','python3 -'],input=remote.encode(),capture_output=True,timeout=60)
if r.returncode:print(r.stderr.decode(errors='replace')[-1500:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(out/'teacher-live-task.json').write_text(json.dumps(data),encoding='utf-8');print(json.dumps(data))
