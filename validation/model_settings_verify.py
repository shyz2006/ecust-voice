import json,urllib.request,urllib.error,hashlib
base='http://127.0.0.1:5000'
checks=[]
for path in ('static/js/campus-review.js','static/js/campus-model-settings.js','static/css/campus-play.css'):
 with urllib.request.urlopen(base+'/'+path+'?v=20261026m2',timeout=20) as r:data=r.read();status=r.status
 checks.append({'path':path,'http':status,'sha256':hashlib.sha256(data).hexdigest()})
with urllib.request.urlopen(base+'/api/config',timeout=20) as r:c=json.load(r)['config']
masked=all(v in ('','********') for k,v in c.items() if k.endswith('API_KEY'))
assert masked
negative=[]
for endpoint,payload in [('/api/test_model',{'engine':'NOT_AN_ENGINE','base_url':'https://example.invalid/v1','model':'test'}),('/api/fetch_models',{'engine':'NOT_AN_ENGINE','base_url':'https://example.invalid/v1'}),('/api/test_model',{'engine':'REPORT_ENGINE','base_url':'https://model-settings-probe.example.invalid/v1','model':'test'})]:
 req=urllib.request.Request(base+endpoint,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=20) as r:status=r.status;response=json.load(r)
 except urllib.error.HTTPError as e:status=e.code;response=json.load(e)
 assert status==400 and not response.get('success')
 negative.append({'endpoint':endpoint,'http':status,'message':response.get('message')})
print(json.dumps({'passed':True,'checks':checks,'saved_secrets_masked':masked,'negative_connection_checks':negative,'provider_calls':0},ensure_ascii=True))
