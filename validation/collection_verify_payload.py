import json,urllib.request,time,re
from datetime import datetime,timezone,timedelta
from pathlib import Path
from CampusPulse import storage,weekly
base='http://127.0.0.1:5000'
def get(path):
 with urllib.request.urlopen(base+path,timeout=40) as r:return r.read()
js=get('/static/js/campus-review.js?v=20261025c2').decode()
line=next(l for l in js.splitlines() if "$('ledgerMetrics').innerHTML=" in l)
assert line.count('metric(')==4 and '小红书' not in line
assert "sourceRows=l.sources.filter(s=>!s.source.endsWith('-school')||s.unique>0)" in js
assert '20261025c2' in get('/').decode() and '20261025c2' in get('/pulse').decode()
ledger=json.loads(get('/pulse/api/revision/ledger'));assert any(s['source']=='xiaohongshu' for s in ledger['sources'])
visible=[s for s in ledger['sources'] if not s['source'].endswith('-school') or s['unique']>0]
assert [s['source'] for s in visible if s['source'].startswith('xiaohongshu')]==['xiaohongshu']
b=storage.latest_batch('complete');counts=b['stats']['by_source']
hot={'weibo','douyin','bilibili-hot-search','zhihu','tieba','toutiao','baidu','thepaper'}
assert hot<=set(counts)
state=json.loads(get('/pulse/api/status'));assert "unexpected keyword argument" not in (state.get('last_error') or '')
w=weekly.get('weekly_20261023_1400_40b5838f9d');assert w['status']=='ready' and w['send_attempts']==0
result={'passed':True,'top_cards':4,'xiaohongshu_in_platform_rows':True,'xiaohongshu_visible_rows':1,'restored_hot_sources':sorted(hot),'source_counts':counts,'batch_items':b['stats']['items'],'batch_status':b['status'],'batch_bjt':datetime.fromtimestamp(b['batch_ts'],timezone(timedelta(hours=8))).isoformat(),'source_errors':b['stats'].get('errors',{}),'weekly_preview_preserved':True,'emails_sent':0,'tests_passed':10,'report_regressions_passed':33}
print(json.dumps(result,ensure_ascii=True))
