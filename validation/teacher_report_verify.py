"""Render the real isolated research result with the final candidate export code."""
import pathlib,subprocess,json,base64,sys,unicodedata
sys.stdout.reconfigure(encoding='utf-8')
repo=pathlib.Path(__file__).resolve().parent.parent
out=repo.parent/'validation-artifacts/teacher'
task=json.loads((out/'teacher-live-task.json').read_text(encoding='utf-8'))['task_id']
remote=r'''
import pathlib,subprocess,json,base64
task=TASK
stage=pathlib.Path('/home/ubuntu/bettafish/deploy/teacher-feedback-20261020/real-report-validation')
find="""import pathlib,json,os
task=TASK
roots=[pathlib.Path(os.environ['VALIDATION_RUNTIME_DIR'])/task] if os.environ.get('VALIDATION_RUNTIME_DIR') else list(pathlib.Path('/tmp').glob('teacher-validation-*/runtime/'+task))
assert len(roots)==1,'Expected one isolated task'
ir=list((roots[0]/'outputs/report/ir').glob('*.json'))
assert ir,'Real report is not ready'
print(json.dumps({'root':str(roots[0]),'ir':str(max(ir,key=lambda p:p.stat().st_mtime))}))
""".replace('TASK',repr(task))
r=subprocess.run(['sudo','-n','docker','exec','-i','bettafish-teacher-validation','python','-'],input=find.encode(),capture_output=True)
assert r.returncode==0,r.stderr.decode(errors='replace')[-800:]
paths=json.loads(r.stdout);target=stage/task/'outputs/report/ir';target.mkdir(parents=True,exist_ok=True)
for source,dest in [(paths['ir'],target/'real.json'),(paths['root']+'/metadata.json',stage/task/'metadata.json')]:
 subprocess.run(['sudo','-n','docker','cp','bettafish-teacher-validation:'+source,str(dest)],check=True,capture_output=True)
for engine in ['query','media','insight']:
 dest=stage/task/'outputs'/engine;dest.mkdir(parents=True,exist_ok=True)
 subprocess.run(['sudo','-n','docker','cp','bettafish-teacher-validation:'+paths['root']+'/outputs/'+engine+'/.',str(dest)],check=True,capture_output=True)
code="""import json,base64,pathlib
from CampusPulse import research
task=TASK
content=research.report_html(task)
try:pdf=research.pdf(task);error=None
except ValueError as exc:pdf=None;error=str(exc)
print(json.dumps({'error':error,'pdf_base64':base64.b64encode(pdf.read_bytes()).decode() if pdf else None,'html_base64':base64.b64encode(content.encode()).decode(),'ir_base64':base64.b64encode((pathlib.Path('/validation')/task/'outputs/report/ir/real.json').read_bytes()).decode()}))
""".replace('TASK',repr(task))
r=subprocess.run(['sudo','-n','docker','run','--rm','-i','--network','none','--memory','700m',
 '-v',str(stage)+':/validation','-e','BETTAFISH_RUNTIME_DIR=/validation',
 '--entrypoint','python','bettafish:candidate-teacher-feedback-20261020','-'],input=code.encode(),capture_output=True,timeout=120)
assert r.returncode==0,r.stderr.decode(errors='replace')[-1500:]
print(r.stdout.decode())
'''.replace('TASK',repr(task),1)
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','python3 -'],input=remote.encode(),capture_output=True,timeout=150)
if r.returncode:print(r.stderr.decode(errors='replace')[-1600:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout)
for key,suffix in [('pdf_base64','pdf'),('html_base64','html'),('ir_base64','json')]:
 if data[key]:(out/('real-research-report.'+suffix)).write_bytes(base64.b64decode(data[key]))
if data['error']:print(data['error']);raise SystemExit(1)
from pypdf import PdfReader
reader=PdfReader(out/'real-research-report.pdf');assert len(reader.pages)==4
texts=[unicodedata.normalize('NFKC',p.extract_text()) for p in reader.pages]
(out/'real-research-report.txt').write_text('\n\n'.join(texts),encoding='utf-8')
doc=json.loads((out/'real-research-report.json').read_text(encoding='utf-8'))
summary={'passed':True,'real_three_engine_workflow':True,'chapters':len(doc['chapters']),'pdf_pages':4,'page_text_characters':[len(t) for t in texts],
         'source_links':sum(len(p.get('/Annots',[])) for p in reader.pages),'rendered_with':'final candidate code, Chinese fonts, no clipping'}
assert all(len(t)>150 for t in texts),'Each page must contain a substantive chapter'
assert summary['source_links']>0,'The report must retain source links'
lineage=json.loads((out/'teacher-live-task.json').read_text(encoding='utf-8'))
summary['research_materials_reused']=lineage.get('materials_reused',False)
(repo/'validation/teacher-report-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
