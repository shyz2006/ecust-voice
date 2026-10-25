import json,hashlib,urllib.request
from CampusPulse import storage
from CampusPulse.sources.campus_social import search_plan
from CampusPulse.sources.xiaohongshu_hot import CACHE_SECONDS
base='http://127.0.0.1:5000'
def get(path):
 with urllib.request.urlopen(base+path,timeout=60) as r:return json.load(r)
s=get('/pulse/api/status');d=get('/pulse/api/revision/overview');f=get('/pulse/api/revision/feed/hot');l=get('/pulse/api/revision/ledger');b=storage.latest_batch()
with urllib.request.urlopen(base+'/static/js/campus-review.js?v=20261025t1',timeout=20) as r:js=r.read()
with urllib.request.urlopen(base+'/static/css/campus-play.css?v=20261025t1',timeout=20) as r:css=r.read()
result={'running':s['running'],'enriching':s.get('enriching'),'complete_windows':sum(c['ready'] for c in d['coverage']),'themes':[{k:t[k] for k in ('theme','delta','comparison','reference')} for t in d['themes']],'comparison_available':sum(t['comparison']['value'] is not None for t in d['themes']),'reference_available':sum(t['reference']['value'] is not None for t in d['themes']),'hot_xiaohongshu_candidates':f.get('candidate_counts',{}).get('小红书',0),'hot_xiaohongshu_cards':sum(x['source']=='xiaohongshu' for x in f['items']),'hot_pool_hours':f.get('xiaohongshu_pool_hours'),'hot_cache_seconds':CACHE_SECONDS,'school_queries':[{'query':q,'include':inc,'count':n} for q,inc,n in search_plan('xiaohongshu-school')],'ledger_xiaohongshu':[x for x in l['sources'] if x['source'] in ('xiaohongshu','xiaohongshu-school')],'latest_batch':{'ts':b['batch_ts'],'status':b['status'],'stats':{k:b['stats'].get(k) for k in ('items','errors','by_source','enriched')}},'served_js_sha256':hashlib.sha256(js).hexdigest(),'reference_chart_served':b'reference-projection' in js,'window_styles_served':b'.window-note' in css}
assert result['comparison_available']==12 and result['reference_available']==12
assert result['reference_chart_served'] and result['window_styles_served']
assert len(result['school_queries'])==4 and all(q['count']==50 for q in result['school_queries'])
print(json.dumps(result,ensure_ascii=True))
