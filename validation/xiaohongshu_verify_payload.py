import json,urllib.request
from CampusPulse import storage
base='http://127.0.0.1:5000'
def get(path):
 with urllib.request.urlopen(base+path,timeout=30) as r:return json.load(r)
s=get('/pulse/api/status');b=storage.latest_batch()
ledger=get('/pulse/api/revision/ledger');feed=get('/pulse/api/revision/feed/hot');posts=get('/pulse/api/revision/source-posts?source=xiaohongshu')
source=next((r for r in ledger.get('sources',[]) if r['source']=='xiaohongshu'),{})
items=[r for r in feed.get('items',[]) if r['source']=='xiaohongshu']
with storage.connect() as c:
 rows=[dict(x) for x in c.execute("SELECT batch_ts,COUNT(*) n FROM snapshots WHERE source='xiaohongshu' GROUP BY batch_ts ORDER BY batch_ts DESC LIMIT 2")]
print(json.dumps({'running':s['running'],'enriching':s.get('enriching'),'stage':s['stage'],'error':s.get('last_error'),'xiaohongshu_batches':rows,'latest_status':b['status'],'latest_items':(b['stats'] or {}).get('items'),'source_counts':(b['stats'] or {}).get('by_source'),'errors':(b['stats'] or {}).get('errors'),'ledger_xiaohongshu':source,'hot_cards':len(items),'all_hot_cards_have_focus':all(r.get('focus') for r in items),'hot_search_links':all(r.get('link_kind')=='platform_search' and r.get('url','').startswith('https://www.xiaohongshu.com/search_result?') for r in items),'source_posts_total':posts.get('total'),'source_post_search_links':all(r.get('link_kind')=='platform_search' for r in posts.get('posts',[]))},ensure_ascii=True))
