"""Exercise the isolated candidate with a copy of real data and one original research task."""
import json,time,pathlib,urllib.request,http.cookiejar,sys
root=pathlib.Path(__file__).resolve().parents[2]/'validation-artifacts/teacher'
root.mkdir(parents=True,exist_ok=True)
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
base='http://127.0.0.1:15001'
def get(path,body=None):
    data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None
    request=urllib.request.Request(base+path,data=data,headers={'Content-Type':'application/json'})
    return json.load(client.open(request,timeout=90))
get('/validation/login')
if len(sys.argv)>1 and sys.argv[1]=='poll':
    task=json.loads((root/'teacher-live-task.json').read_text())['task_id']
    result=get('/pulse/api/revision/research/'+task)
    (root/'teacher-live-status.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));raise SystemExit()
results={}
for name,path in [('overview','overview'),('ledger','ledger'),('hot','feed/hot'),('memes','feed/memes')]:
    started=time.time();value=get('/pulse/api/revision/'+path)
    results[name]={'seconds':round(time.time()-started,2),'data':value}
    print(name,round(time.time()-started,2),'seconds', 'keys:',list(value))
(root/'teacher-live-data.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
task=get('/pulse/api/revision/research',{'query':'高校学生使用生成式人工智能的学习方式与信息核验问题','request_id':'teacher-isolated-real-20261020'})
(root/'teacher-live-task.json').write_text(json.dumps(task,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(task,ensure_ascii=False))
