import json,time,urllib.request
from datetime import datetime,timezone,timedelta
from collections import Counter,defaultdict
from CampusPulse import storage
from CampusPulse.post_identity import stable_value
TZ=timezone(timedelta(hours=8));now=int(time.time());start=int(datetime(2026,10,23,tzinfo=TZ).timestamp())
with urllib.request.urlopen('http://127.0.0.1:5000/pulse/api/status',timeout=20) as r:status=json.load(r)
with storage.connect() as c:
 batches=[dict(r) for r in c.execute('SELECT batch_ts,status,error FROM batches WHERE batch_ts>=? ORDER BY batch_ts',(start,))]
 rows=storage.recent_items(['huyou-school','tieba-school'],start-86400)
counts=Counter();seen=set();unknown=Counter()
for r in rows:
 ex=r['extra'];pub=ex.get('published');key=(r['source'],stable_value(r))
 if key in seen:continue
 seen.add(key)
 if not pub:unknown[r['source']]+=1;continue
 try:date=datetime.fromtimestamp(float(pub),TZ).date().isoformat()
 except (ValueError,TypeError,OverflowError):continue
 if date>='2026-10-23':counts[(date,r['source'])]+=1
bydate=defaultdict(Counter)
for b in batches:bydate[datetime.fromtimestamp(b['batch_ts'],TZ).date().isoformat()][b['status']]+=1
print(json.dumps({'status':{k:status.get(k) for k in ('running','enriching','last_error','last_complete','interval_min')},'batches_by_day':dict(bydate),'last_batches':[dict(ts=datetime.fromtimestamp(b['batch_ts'],TZ).isoformat(),status=b['status'],error=b['error']) for b in batches[-8:]],'first_gap_before_recovery':[dict(ts=datetime.fromtimestamp(b['batch_ts'],TZ).isoformat(),status=b['status'],error=b['error']) for b in batches[:8]],'published_records':[{'date':d,'source':s,'unique':n} for (d,s),n in counts.items()],'unknown_published':dict(unknown)},ensure_ascii=True))
