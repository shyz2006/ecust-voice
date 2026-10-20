"""Disposable database; model and delivery calls are mocked. No external messages."""
import os,tempfile,pathlib,time,json,copy
from datetime import datetime,timedelta
from unittest import mock
os.environ['BETTAFISH_RUNTIME_DIR']=tempfile.mkdtemp()
from loguru import logger
logger.remove()
from CampusPulse.config import settings
settings.db_path=pathlib.Path(tempfile.mkdtemp())/'case.db'
from CampusPulse import weekly,storage,taxonomy,campus
from CampusPulse.blueprint import pulse_bp
from flask import Flask
weekly.initialize();checks=[]
assert not weekly.config()['enabled'] and not weekly.config()['key_configured']
try:weekly.save_config({'enabled':True})
except ValueError:pass
else:raise AssertionError('Incomplete automatic mail configuration accepted')
cfg={'sender':'校园周报 <weekly@example.com>','recipients':'teacher@example.com','api_key':'re_isolated_test_key','sender_verified':True,'enabled':True}
weekly.save_config(cfg);assert weekly.config()['key_configured'] and 'api_key' not in weekly.config()
weekly.save_config({'api_key':''});assert weekly.config(True)['api_key']==cfg['api_key']
try:weekly.save_config({'recipients':['invalid']})
except ValueError:pass
else:raise AssertionError('Invalid recipient accepted')
checks+=['automatic mail disabled by default; complete configuration required','API key masked and blank preserves it; email validation']
now=int(time.time());rows=[]
for day in range(14):
 for source in ('huyou-school','tieba-school'):
  text=('图书馆预约，自习很难找到座位' if source=='huyou-school' else '选课作业多，希望课程安排更清晰')+str(day)
  for hour in (1,5,9,13,17,21):
   rows.append({'source':source,'batch_ts':now-(14-day)*86400+hour*3600,'rank':1,'title':text,'url':'https://example.com/post/'+source+'/'+str(day),'extra':{'content':text,'published':now-(14-day)*86400+100,'comments':1,'exposure':10}})
with mock.patch.object(storage,'recent_items',return_value=rows),mock.patch.object(storage,'kv_prefix',return_value=[]):data=weekly.packet(now)
assert data['current_total']==data['previous_total']==14
assert sum(n[0] for n in data['categories'].values())==14 and len(data['categories'])==12
assert data['observed_days']==data['previous_observed_days']==7
assert {e['period'] for e in data['evidence']}=={'current','previous'}
checks+=['fourteen-day deduplication with matching twelve-category rules','balanced current/prior evidence and actual sampling coverage']
current=next(e['id'] for e in data['evidence'] if e['period']=='current')
previous=next(e['id'] for e in data['evidence'] if e['period']=='previous')
insights={'headline':'校园的一周：学习与生活','signals':[{'title':'自习空间的期待','observation':'讨论中可见同学对自习空间和清晰安排的期待。','comparison':'两期材料都能看到学习安排的诉求。','evidence':[current,previous]}],'follow_up':['可以了解座位供给与预约体验。']}
weekly.validate_insights(copy.deepcopy(insights),data)
bad=copy.deepcopy(insights);bad['signals'][0]['evidence']=['S999']
try:weekly.validate_insights(bad,data)
except ValueError:pass
else:raise AssertionError('Invented evidence accepted')
sparse=copy.deepcopy(data);sparse['previous_observed_days']=0
assert not weekly.validate_insights(copy.deepcopy(insights),sparse)['signals'][0]['comparison']
bad=copy.deepcopy(insights);bad['signals'][0]['observation']='有75%的学生确诊焦虑'
try:weekly.validate_insights(bad,data)
except ValueError:pass
else:raise AssertionError('Unsupported percentage accepted')
checks+=['evidence IDs checked; incomplete coverage removes comparisons','unsupported psychological diagnosis and statistical percentages rejected']
report_id='preview_case'
with storage.connect() as conn:conn.execute('INSERT INTO pulse_weekly(id,cutoff,kind,created,status) VALUES(?,?,?,?,?)',(report_id,now,'preview',now,'generating'))
with mock.patch.object(weekly,'packet',return_value=data),mock.patch.object(weekly,'summarize',return_value=(insights,'test-model')):weekly.generate(report_id)
row=weekly.get(report_id);assert row['status']=='ready' and row['generation_attempts']==1
document=weekly.report_html(row);assert '查看原帖' in document and '十二类议题' in document
malicious=copy.deepcopy(row);malicious['data']['insights']['headline']='<script>alert(1)</script>'
assert '<script>' not in weekly.report_html(malicious)
checks+=['generation persisted with model and sources; safe HTML preview']
captured=[]
def deliver(payload,key,api_key):captured.append((copy.deepcopy(payload),key));return 'isolated-email-id'
with mock.patch.object(weekly,'resend',side_effect=ValueError('test timeout')):weekly.send_report(report_id)
assert weekly.get(report_id)['send_state']=='failed'
with mock.patch.object(weekly,'resend',side_effect=deliver):weekly.send_report(report_id);weekly.send_report(report_id)
assert len(captured)==1 and weekly.get(report_id)['send_state']=='submitted'
assert captured[0][1]=='campus-weekly/'+report_id and captured[0][0]['to']==['teacher@example.com']
assert 'mail_payload' not in weekly.get(report_id)
import io
captured_requests=[]
def fake_http(request,timeout):
 captured_requests.append(request)
 return io.StringIO(json.dumps({'id':'transport-case'}))
with mock.patch.object(weekly,'urlopen',side_effect=fake_http):
 assert weekly.resend({'from':'weekly@example.com','to':['teacher@example.com'],'subject':'test','html':'<p>test</p>'},'stable-key','re_test_key')=='transport-case'
assert captured_requests[0].full_url=='https://api.resend.com/emails'
assert captured_requests[0].get_header('Idempotency-key')=='stable-key'
checks+=['delivery retries preserve payload/idempotency; submitted mail never resent']
retry_id='weekly_20261023'
with storage.connect() as conn:conn.execute('INSERT INTO pulse_weekly(id,cutoff,kind,created,status,generation_attempts) VALUES(?,?,?,?,?,?)',(retry_id,now,'scheduled',now,'failed',1))
with mock.patch.object(weekly.threading,'Thread') as thread:
 weekly.tick(datetime(2026,10,23,13,40,tzinfo=weekly.TZ));assert thread.call_count==1
with storage.connect() as conn:conn.execute("UPDATE pulse_weekly SET status='failed',generation_attempts=3 WHERE id=?",(retry_id,))
with mock.patch.object(weekly.threading,'Thread') as thread:
 weekly.tick(datetime(2026,10,23,13,45,tzinfo=weekly.TZ));assert not thread.called
checks+=['failed generation retries before delivery, capped at three attempts']
friday=datetime(2026,10,23,13,30,tzinfo=weekly.TZ)
with mock.patch.object(weekly,'get',side_effect=ValueError('missing')),mock.patch.object(weekly,'start') as start:
 weekly.tick(friday-timedelta(seconds=1));assert not start.called
 weekly.tick(friday);assert start.call_args.args[0]==int(friday.timestamp())
 start.reset_mock();weekly.tick(friday.replace(hour=14));assert not start.called
assert weekly.next_friday(friday).hour==14
assert weekly.next_friday(friday.replace(hour=15)).day==30
checks+=['Friday 13:30 generation, 14:00 delivery window and no stale catch-up']
app=Flask('case');app.secret_key='test';app.register_blueprint(pulse_bp,url_prefix='/pulse');client=app.test_client()
assert client.get('/pulse/api/revision/weekly').status_code==401
with client.session_transaction() as session:session.update(authenticated=True,username='case')
assert client.get('/pulse/api/revision/weekly').json['items']
assert 'api_key' not in client.get('/pulse/api/revision/weekly/config').json['config']
assert client.post('/pulse/api/revision/weekly',json={},headers={'Origin':'https://foreign.example'}).status_code==403
assert client.get('/pulse/api/revision/weekly/'+report_id+'/report').status_code==200
checks+=['weekly APIs authenticated; secrets omitted; cross-origin mutations rejected']

# Custom schedules and cross-midnight cutoffs use the same durable slot identifier.
old_secret=weekly.config(True)['api_key']
changed=weekly.save_config({'weekday':0,'send_time':'00:15','lead_minutes':60})
assert weekly.config(True)['api_key']==old_secret and changed['schedule_revision']
assert weekly.get(retry_id)['send_state']=='cancelled'
monday=datetime(2026,10,26,0,15,tzinfo=weekly.TZ)
assert weekly.next_dispatch(weekly.config(True),monday-timedelta(minutes=2))==monday
assert weekly.next_dispatch(weekly.config(True),monday)==monday+timedelta(days=7)
with mock.patch.object(weekly,'get',side_effect=ValueError('missing')),mock.patch.object(weekly,'start') as start:
 weekly.tick(monday-timedelta(minutes=61));assert not start.called
 weekly.tick(monday-timedelta(minutes=60));assert start.call_args.kwargs['send_at']==monday
 assert start.call_args.args[0]==int((monday-timedelta(minutes=60)).timestamp())
with mock.patch.object(weekly,'resend') as send:
 weekly.send_report(retry_id);assert not send.called
for field,value in [('weekday',True),('weekday',7),('lead_minutes',4),('lead_minutes',181),('send_time','24:00'),('send_time','9:30')]:
 try:weekly.save_config({field:value})
 except ValueError:pass
 else:raise AssertionError('Invalid schedule accepted: '+field)
checks+=['custom weekday/time, prior-day generation, next-week rollover, old-slot cancellation and validation']
from CampusPulse import dynamic_memes as dm
term='云朵蹦迪'  # Arbitrary expression absent from every seed dictionary.
rows=[{'title':term+'这个用法又被二创了'+str(i),'url':'https://video.example.com/video/'+str(i),'platform':'B站','source':'bilibili-popular','ts':now} for i in range(4)]
rows+=[dict(rows[0]),{**rows[0],'url':'https://video.example.com/video/0?share=other'},
       {**rows[1],'url':'https://search.bilibili.com/all?keyword=test','title':term+'搜索结果'}]
docs={'D1':rows[0]}
proposal={'candidates':[{'term':term,'aliases':[],'evidence_ids':['D1'],'form':'比喻表达'},
 {'term':'凭空编造','evidence_ids':['D999']}]}
c=dm.candidates(proposal,docs,rows)[0]
assert c['term']==term and c['observed_count']==4 and len(dm.candidates(proposal,docs,rows))==1
ref={'title':term+'是什么梗','url':'https://language.example.com/explain/1','snippet':term+'是形容心情轻快、忍不住雀跃的调侃表达，常见于评论和二创。'}
refs=dm.references(term,[],[ref,{**ref,'url':'https://www.baidu.com/s?wd=test'},{**ref,'title':'同名活动','snippet':'这里是普通新闻报道'}])
assert len(refs)==1
answer={'term':term,'is_meme':True,'meaning':'形容心情轻快、忍不住雀跃的调侃表达。','usage':'评论区分享开心时刻。','reference_id':'R1','quote':ref['snippet']}
assert dm.verified(c,answer,refs,now)
for patch in [{'quote':'这句话不在检索资料中出现'}, {'reference_id':'R999'}, {'is_meme':False}]:
 assert dm.verified(c,{**answer,**patch},refs,now) is None
assert dm.verified({**c,'observed_count':2},answer,refs,now) is None
# End-to-end discovery retains the new term, without any fallback/padding.
from CampusPulse import search
screen_answer={'accepted':[{'term':term,'observation':'在这些视频标题中，该表达被用于夸张地描述雀跃和开心的反应，形成可以跟着模仿的调侃说法。','example_quote':rows[0]['title']}]}
with mock.patch.object(dm,'corpus',return_value=rows),mock.patch.object(dm,'model',side_effect=[proposal,screen_answer,{'results':[answer]}]),mock.patch.object(search,'web_search',return_value=[ref]):dm.scan()
result=dm.snapshot();assert len(result['items'])==1 and result['items'][0]['term']==term and not result['candidates']
# Weak evidence stays a candidate and never receives a fabricated definition.
weak=rows[:2]
with mock.patch.object(dm,'corpus',return_value=weak),mock.patch.object(dm,'model',side_effect=[proposal,screen_answer]),mock.patch.object(search,'web_search') as search_call:dm.scan();assert not search_call.called
result=dm.snapshot();assert not result['items'] and result['candidates'][0]['observed_count']==2
with mock.patch.object(dm,'corpus',return_value=weak),mock.patch.object(dm,'model',side_effect=RuntimeError('secret provider detail')):dm.scan()
assert 'secret' not in json.dumps(dm.snapshot()) and dm.saved()['status']=='failed'
assert client.post('/pulse/api/revision/memes/refresh',json={},headers={'Origin':'https://foreign.example'}).status_code==403
checks+=['new expression discovered end to end with mocked model/search, no fixed vocabulary or card padding',
 'duplicate URL/title and search pages excluded from independent uses',
 'invented evidence IDs/quotes and weak evidence cannot promote; candidates remain visible',
 'provider failure produces safe diagnostic and preserves prior results']

from utils import search_gateway as gateway
response=mock.Mock();response.status_code=200;response.json.return_value={'code':200,'data':{'webPages':{'value':[{'name':'测试资料','url':'https://example.com/ref/1','summary':'摘要'}]}}}
with mock.patch.multiple(search.settings,bocha_api_key='isolated',bocha_base_url='https://api.bocha.cn/v1/ai-search'),mock.patch.object(gateway,'cache_get',return_value=None),mock.patch.object(gateway,'try_consume',return_value=True),mock.patch.object(gateway,'cache_put'),mock.patch.object(search.requests,'post',return_value=response) as post:
 pages=search.web_search('test',count=2,freshness='noLimit',plain=True)
 assert post.call_args.args[0]=='https://api.bocha.cn/v1/web-search' and len(pages)==1
 assert post.call_args.kwargs['json']['summary'] is True and post.call_args.kwargs['headers']['User-Agent']=='ECUST-CampusPulse/1.0'
quota_response=mock.Mock();quota_response.status_code=403;quota_response.json.return_value={'error':'quota exhausted'}
with mock.patch.multiple(search.settings,bocha_api_key='isolated',bocha_base_url='https://api.bocha.cn/v1/ai-search'),mock.patch.object(gateway,'cache_get',return_value=None),mock.patch.object(gateway,'try_consume',return_value=True),mock.patch.object(gateway,'refund'),mock.patch.object(search.requests,'post',return_value=quota_response):
 try:search.web_search('test',plain=True)
 except search.SearchUnavailable as exc:assert '博查额度不足' in str(exc)
 else:raise AssertionError('Quota failure should stop verification')
checks+=['meme verification selects Bocha web-search with summaries and explicit application client header']
with mock.patch.object(dm,'model',return_value={'accepted':[{'term':term,'observation':'这里是一段有长度的简介，但其引用并不来自真实材料。','example_quote':term+'凭空编造的引用'}]}):assert not dm.screen([c])
assert dm.candidates({'candidates':[{'term':term,'evidence_ids':['D1']}]},docs,[{**rows[0],'url':'https://search.bilibili.com/all?keyword=example'}])==[]
checks+=['candidate screening requires a grounded introduction and real use; invented intro quotes rejected']
assert not dm.is_observed_url('https://www.douyin.com/hot/2700388')
assert not dm.is_observed_url('https://www.douyin.com/search/example')
assert dm.is_observed_url('https://www.douyin.com/video/7123456789012345678')
assert dm.is_observed_url('https://www.bilibili.com/video/BV122nu6sEKG/')
assert not dm.is_observed_url('https://www.bilibili.com/video/not-a-bvid')
assert dm.content_url('http://m.bilibili.com/video/BV122nu6sEKG?share_source=test')=='https://www.bilibili.com/video/BV122nu6sEKG/'
assert dm.content_url('https://www.douyin.com/video/7123456789012345678?modal_id=old')=='https://www.douyin.com/video/7123456789012345678'
old_data={'candidates':[{'term':'旧话题','observation':'旧版曾显示的话题，实际上没有独立内容链接。','links':[{'url':'https://www.douyin.com/hot/2700388'}]}]}
with mock.patch.object(dm,'saved',return_value=old_data):assert not dm.snapshot()['candidates']
checks+=['expired Douyin hot topics are not content examples; concrete video URLs canonicalized; legacy topic cards excluded']
print(json.dumps({'passed':True,'checks':checks,'model_calls':'mocked','emails_sent':0,'production_writes':False}))
