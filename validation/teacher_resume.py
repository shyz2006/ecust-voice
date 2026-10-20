"""Preserve the completed isolated research before restarting with final report code."""
import pathlib,json,subprocess,sys
repo=pathlib.Path(__file__).resolve().parent.parent
out=repo.parent/'validation-artifacts/teacher';state=json.loads((out/'teacher-live-task.json').read_text(encoding='utf-8'));task=state['task_id']
if len(sys.argv)>1 and sys.argv[1]=='generate':
 code=r'''
import pathlib,json,urllib.request
task=TASK
root=pathlib.Path('/home/ubuntu/bettafish/deploy/teacher-feedback-20261020/validation-runtime')/task
meta=json.loads((root/'metadata.json').read_text())
request=urllib.request.Request('http://127.0.0.1:15001/api/report/generate',data=json.dumps({'research_task_id':task,'query':meta['query'],'regenerate':True}).encode(),headers={'Content-Type':'application/json'})
data=json.load(urllib.request.urlopen(request,timeout=30));assert data['success']
print(json.dumps({'report_task_id':data['task_id']}))
'''.replace('TASK',repr(task))
else:
 code=r'''
import pathlib,json,subprocess,shutil
task=TASK
find="import pathlib,json;roots=list(pathlib.Path('/tmp').glob('teacher-validation-*/runtime/TASK'));assert len(roots)==1;print(json.dumps(str(roots[0])))".replace('TASK',task)
r=subprocess.run(['sudo','-n','docker','exec','-i','bettafish-teacher-validation','python','-'],input=find.encode(),capture_output=True,check=True)
source=json.loads(r.stdout);stage=pathlib.Path('/home/ubuntu/bettafish/deploy/teacher-feedback-20261020')
saved=stage/'validation-evidence-backup'/task;assert not saved.exists();saved.parent.mkdir(parents=True,exist_ok=True)
subprocess.run(['sudo','-n','docker','cp','bettafish-teacher-validation:'+source,str(saved)],check=True,capture_output=True)
target=stage/'validation-runtime'/task
assert not target.exists();target.parent.mkdir(parents=True,exist_ok=True)
shutil.copytree(saved,target,ignore=lambda folder,names:['report'] if pathlib.Path(folder)==saved/'outputs' else [])
print(json.dumps({'evidence_preserved':True,'unverified_report_separated':True}))
'''.replace('task=TASK','task='+repr(task),1)
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','python3 -'],input=code.encode(),capture_output=True,timeout=90)
if r.returncode:print(r.stderr.decode(errors='replace')[-1800:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
if 'report_task_id'in data:state.update(data);(out/'teacher-live-task.json').write_text(json.dumps(state),encoding='utf-8')
print(json.dumps(data))
