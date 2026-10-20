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
print(json.dumps({'passed':True,'checks':checks,'model_calls':'mocked','emails_sent':0,'production_writes':False}))
