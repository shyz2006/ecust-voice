"""Focused checks for the follow-up, in a disposable container without network."""
import os,tempfile,pathlib,json,time
from unittest import mock
from datetime import datetime,timedelta,timezone
os.environ['BETTAFISH_RUNTIME_DIR']=tempfile.mkdtemp()
from loguru import logger
logger.remove()
from CampusPulse.config import settings
settings.db_path=pathlib.Path(tempfile.mkdtemp())/'case.db'
from CampusPulse import taxonomy,revision,storage,telemetry,campus
from CampusPulse.hot_focus import brief
from CampusPulse.meme_catalog import build
from CampusPulse.blueprint import pulse_bp
from flask import Flask
checks=[]
for text,theme in [('申飞上车点在哪','校园设施与管理'),('学习通工训课怎么签到','学业课程'),('求奉贤附近裁缝店','食堂与生活服务'),('出一张梦境车票','交易与互助'),('有没有青协的群求拉','社交与同伴'),('周末去欢乐谷','文体与实践')]:
 assert taxonomy.classify(text)['theme']==theme,(text,taxonomy.classify(text))
assert taxonomy.classify('今天拿到一张mint卡')['theme']=='其他校园讨论'
assert taxonomy.classify('明天下午！')['theme']=='其他校园讨论'
checks+=['campus-specific vocabulary and intent','English word boundaries and unsupported text remain unassigned']
assert brief('英雄联盟瑞士轮赛程')[1]=='title_rule'
assert brief('新话题XYZ')[0].startswith('话题要点')
assert brief('标题','已有摘要')==('已有摘要','cached_annotation')
now=int(time.time());network=[]
for source in revision.HOT_PLATFORMS:
 for rank in range(1,16):network.append({'source':source,'batch_ts':now,'rank':rank,'title':source+'话题'+str(rank),'url':'https://example.com/'+source+'/'+str(rank),'extra':{}})
network[0]['title']='标题缓存校验'
with mock.patch.object(storage,'recent_items',return_value=network),mock.patch.object(storage,'latest_source_batches',return_value={}),mock.patch.object(storage,'latest_topics',return_value={'topics':[]}),mock.patch.object(storage,'kv_prefix',return_value=[{'key':'annot2:标题缓存校验','value':json.dumps({'one_liner':'摘要正确命中'})}]):
 hot=revision.network_feed('hot',True)
 assert len(hot['items'])==40 and all(x['focus'] and x['focus_method'] for x in hot['items'])
 assert next(x for x in hot['items'] if x['title']=='标题缓存校验')['focus']=='摘要正确命中'
checks+=['all forty hot cards have focus','annotation cache prefix recovered; no LLM requests']
items=[{'platform':p,'title':'今天班味好重','ts':now,'url':url} for p,url in [('B站','https://www.bilibili.com/video/BV1'),('抖音','https://www.douyin.com/video/123'),('微博','https://s.weibo.com/weibo?q=班味')]]
memes=build(items);assert len(memes)==len({x['term'] for x in memes})==10
banwei=next(x for x in memes if x['term']=='班味');assert len(banwei['links'])==2
assert {x['platform'] for x in banwei['links']}=={'B站','抖音'}
assert all(len(x['search_links'])==4 for x in memes)
checks+=['ten unique aggregated memes','cross-platform examples merged; search pages excluded']
rows=[]
for i in range(5):rows.append({'source':'huyou-school','batch_ts':now,'rank':i+1,'title':'图书馆第'+str(i)+'条讨论','url':'https://example.com/post/'+str(i),'extra':{'content':'图书馆第'+str(i)+'条讨论','published':now-i*100,'comments':1,'exposure':10}})
with mock.patch.object(storage,'recent_items',return_value=rows),mock.patch.object(storage,'kv_prefix',return_value=[]):
 data=revision.snapshot(True);examples=next(t['examples'] for t in data['themes'] if t['theme']=='校园设施与管理')
 assert len(examples)==3 and [x['link'].split('/')[-1] for x in examples]==['0','1','2']
checks+=['three newest linked posts per topic']
with storage.connect() as conn:
 stamp=datetime.now(timezone(timedelta(hours=8))).replace(hour=0,minute=0,second=1,microsecond=0).timestamp()
 conn.execute('INSERT INTO pulse_usage(ts,engine,seconds,prompt_tokens,completion_tokens,success,usage_known) VALUES(?,?,?,?,?,?,?)',(stamp,'query',0,100,50,1,1))
 conn.execute('INSERT INTO pulse_usage(ts,engine,seconds,prompt_tokens,completion_tokens,success,usage_known) VALUES(?,?,?,?,?,?,?)',(stamp-14*86400,'query',0,999,999,1,1))
app=Flask('case');app.secret_key='test';app.register_blueprint(pulse_bp,url_prefix='/pulse');client=app.test_client()
with client.session_transaction() as session:session.update(authenticated=True,username='case')
dashboard={'sources':[],'generated_at':now,'observed_since':now,'unique_school_posts':0,'main_reports_completed':0,'recorded_tokens':0}
with mock.patch.object(telemetry,'dashboard',return_value=dashboard):
 daily=client.get('/pulse/api/revision/ledger').json['daily_usage']
 assert len(daily)==14 and len({x['day'] for x in daily})==14
 assert daily[-1]['tokens']==150 and daily[-1]['has_records']
 assert all(not x['has_records'] and x['tokens'] is None for x in daily[:-1])
 assert daily[0]['day']==(datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=13)).isoformat()
checks+=['fourteen Beijing calendar dates including today','missing dates distinct from zero and old usage excluded']
print(json.dumps({'passed':True,'checks':checks,'production_writes':False}))
