import json,urllib.request,hashlib
from CampusPulse import storage
base='http://127.0.0.1:5000'
def get(path):
 with urllib.request.urlopen(base+path,timeout=30) as r:return json.load(r)
s=get('/pulse/api/status');overview=get('/pulse/api/revision/overview')
with urllib.request.urlopen(base+'/static/js/campus-review.js?v=20261025t3',timeout=20) as r:js=r.read()
a=s.get('last_attempt') or {}
result={'running':s['running'],'enriching':s.get('enriching'),'last_attempt':a,'scheduler_alive':s.get('scheduler_alive'),'last_complete':s['last_complete'],'observed_at':overview.get('observed_at'),'generated_at':overview['generated_at'],'collection_health':overview.get('collection_health'),'audit_history_rows':len(storage.kv_prefix('collection:attempt:',limit=1500)),'served_js_sha256':hashlib.sha256(js).hexdigest()}
if a.get('status')=='complete':
 assert a['batch_ts']==s['last_complete'] and a.get('items',0)>0
 assert s.get('scheduler_alive') and overview.get('observed_at')
print(json.dumps(result,ensure_ascii=True))
