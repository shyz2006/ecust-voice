"""Real preliminary search/model in isolated DB, no research workers or email."""
import pathlib,subprocess,json,shlex,sys
sys.stdout.reconfigure(encoding='utf-8')
repo=pathlib.Path(__file__).resolve().parent.parent
code=r"""
import urllib.request,http.cookiejar,json,time
jar=http.cookiejar.CookieJar();opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar));base='http://127.0.0.1:15004'
def get(path,data=None):
 req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
 return json.load(opener.open(req,timeout=15))
get('/validation/login');results=[]
for query,context in [('武汉大学内战',''),('武汉大学内战','这里指网络上文科与理工科之间的争论，想了解其形成、传播和学科身份认同；具体指控需要核查。'),('南京大学帝王蟹事件','')]:
 began=time.time();result=get('/pulse/api/revision/research/brief',{'query':query,'context':context})
 while result['status']=='preparing' and time.time()-began<180:
  time.sleep(2);result=get('/pulse/api/revision/research/brief/'+result['id'])
 results.append({'query':query,'context':context,'seconds':round(time.time()-began),'status':result['status'],'directions':result['directions'],'sources':result['sources'],'question':result.get('question'),'message':result.get('message')})
 time.sleep(21 if time.time()-began<20 else .1)
print(json.dumps({'results':results,'isolated_database':True,'full_reports_started':0,'emails_sent':0},ensure_ascii=False))
"""
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(['sudo','-n','docker','exec','-i','bettafish-workshop-intent-validation-web','python','-'])],input=code.encode(),capture_output=True,timeout=650)
if r.returncode:print(r.stderr.decode(errors='replace')[-1500:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/workshop-intent-live-results.json').write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(data,ensure_ascii=False))
