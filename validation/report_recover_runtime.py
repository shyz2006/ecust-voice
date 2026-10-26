import json,urllib.request,time,hashlib
from utils.task_runtime import read_task_metadata,task_output_dir
T='task_60222aa862abab486d14708fe7679dd3'
def inputs_digest():
 return {engine:{str(p.relative_to(task_output_dir(T,engine))):hashlib.sha256(p.read_bytes()).hexdigest() for p in task_output_dir(T,engine).rglob('*') if p.is_file()} for engine in ('query','media','insight')}
before=inputs_digest()
with urllib.request.urlopen('http://127.0.0.1:5000/api/report/status?research_task_id='+T,timeout=20) as r:current=json.load(r).get('current_task') or {}
start=time.monotonic()
if current.get('status') in ('pending','running','completed'):
 result={'reused':True,'status':current.get('status'),'report_task_id':current.get('task_id')}
else:
 payload={'research_task_id':T,'query':read_task_metadata(T).get('query',''),'regenerate':True}
 request=urllib.request.Request('http://127.0.0.1:5000/api/report/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(request,timeout=120) as r:response=json.load(r)
 result={k:response.get(k) for k in ('success','task_id','status','existing')}
print(json.dumps({'research_task_id':T,'submission_seconds':round(time.monotonic()-start,3),'result':result,'engine_outputs_unchanged':before==inputs_digest(),'input_files':{k:len(v) for k,v in before.items()}},ensure_ascii=True))
