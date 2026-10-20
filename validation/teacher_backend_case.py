"""Executed only in an isolated candidate container, with a temporary database/runtime."""
import os,tempfile,pathlib,json,time,base64,math
from unittest import mock
from types import SimpleNamespace
tmp=pathlib.Path(tempfile.mkdtemp(prefix='teacher-case-'))
os.environ['BETTAFISH_RUNTIME_DIR']=str(tmp/'runtime')
from loguru import logger
logger.remove()
from CampusPulse.config import settings
settings.db_path=tmp/'fixture.db'
from CampusPulse import taxonomy,revision,research,storage,campus
from flask import Flask
from CampusPulse.blueprint import pulse_bp
checks=[]
assert len(taxonomy.THEMES)==len(set(taxonomy.THEMES))==12
assert taxonomy.canonical('找搭子/兴趣活动')=='社交与同伴'
assert taxonomy.canonical('其他','报名参加志愿服务活动')=='文体与实践'
assert taxonomy.sentiment('开心快乐')['label']=='积极'
assert taxonomy.sentiment('不开心，真的失望')['label']=='消极'
assert taxonomy.sentiment('明天十点上课')['label']=='中性'
assert revision.positive_practice('报名参加志愿服务活动')
assert not revision.positive_practice('志愿活动代签刷分广告')
assert not revision.positive_practice('报名参加音乐节，太开心了')
assert not revision.positive_practice('强制参加团日，只想凑时长')
checks+=['fixed taxonomy and aliases','deterministic sentiment with negation','practice content validation']
points=[{'new_posts':n,'observed':n is not None} for n in [1,2,None,3,4]]
reference=revision.count_reference(points);assert reference['value']==2.5 and reference['windows']==4
assert reference['validation_windows']==1 and reference['mae']==2
assert revision.count_reference(points[:2])['value'] is None
checks+=['mean baseline excludes gaps','rolling MAE uses prior windows only','minimum observation gate']
now=int(time.time());rows=[];annotations=[]
for day in range(10):
 for source in ['huyou-school','tieba-school']:
  text=('图书馆开放时间的讨论，今天很开心，推荐新的阅读区。' if source=='huyou-school' else '考试考证报名时间，明天在哪里办理？')+str(day)
  annotations.append({'key':campus._hash(text),'value':json.dumps({'theme':'校园设施与管理' if source=='huyou-school' else '考试考证','is_ad':False,'crisis_level':'无','emotion':'消极'})})
  for hour in [1,5,9,13,17,21]:
   rows.append({'source':source,'batch_ts':now-(10-day)*86400+hour*3600,'rank':1,'title':text,'url':'https://example.com/'+source+'/'+str(day),'extra':{'content':text,'published':now-(10-day)*86400+100,'comments':day,'exposure':20}})
annotations[0]['value']=json.dumps({'theme':'恋爱情感','is_ad':False,'crisis_level':'无','emotion':'消极'})
with mock.patch.object(storage,'recent_items',return_value=rows),mock.patch.object(storage,'kv_prefix',return_value=annotations):
 data=revision.snapshot(True)
 assert len(data['themes'])==12 and sum(t['posts'] for t in data['themes'])==data['total']==20
 assert data['emotion'].get('消极',0)==0,'Old model labels must not override rule statistics'
 assert all(c['ready'] for c in data['coverage'])
 assert sum(t['posts_7d'] for t in data['themes'])==data['total_7d']
 assert all(p['theme'] in taxonomy.THEMES for p in data['posts'])
 assert all(p['theme']=='校园设施与管理' for p in data['posts'] if p['source']=='huyou-school')
checks+=['cross-module count conservation','7d and 10d scopes agree','model labels excluded from classification and sentiment metrics','coverage gates']
network=[]
for stamp in [now-10800,now-7200,now-3600,now]:
 network.append({'source':'douyin','batch_ts':stamp,'rank':1,'title':'常驻校园新闻','url':'https://www.douyin.com/video/123','extra':{}})
 if stamp==now:network.append({'source':'douyin','batch_ts':stamp,'rank':2,'title':'班味太重的新视频','url':'https://www.douyin.com/video/456','extra':{}})
with mock.patch.object(storage,'recent_items',return_value=network),mock.patch.object(storage,'latest_topics',return_value={'topics':[]}),mock.patch.object(storage,'kv_prefix',return_value=[{'key':'班味太重的新视频','value':json.dumps({'one_liner':'关注实习与学习中的疲惫表达'})}]):
 feed=revision.network_feed('hot');new=next(x for x in feed['items'] if '班味' in x['title'])
 assert new['baseline_samples']==3 and new['signal']>0
 assert len(feed['items'])==2
 assert new['focus']=='关注实习与学习中的疲惫表达'
 memes=revision.network_feed('memes')['items'];assert memes and all(x['links'] for x in memes)
assert revision.source_link('javascript:alert(1)') is None
checks+=['burst includes absent past observations as zero','latest feed deduplicates polling','memes require matched source','unsafe links rejected']
app=Flask('isolated-teacher-case');app.secret_key='test-only';app.register_blueprint(pulse_bp,url_prefix='/pulse');client=app.test_client()
assert client.post('/pulse/api/analyze',json={'query':'旧活动入口'}).status_code==410
assert client.post('/pulse/api/issues/fixture/generate',json={'kind':'full'}).status_code==410
checks+=['retired activity generation routes']
assert client.post('/pulse/api/revision/research',json={'query':'研究'}).status_code==401
with client.session_transaction() as session:session['authenticated']=True
assert client.post('/pulse/api/revision/research',json={'query':'研究'}).status_code==401
with client.session_transaction() as session:session['authenticated']=True;session['username']='fixture-account'
assert client.post('/pulse/api/revision/research',json={'query':' '}).status_code==400
assert client.post('/pulse/api/revision/research',json={'query':'问'*501}).status_code==400
assert client.get('/pulse/api/revision/posts?theme=unknown').status_code==400
assert client.get('/pulse/api/revision/posts?from=bad').status_code==400
assert client.get('/pulse/api/revision/research/unknown').status_code==404
assert client.get('/pulse/api/revision/posts?theme=unknown').headers['Cache-Control']=='no-store'
from utils import research_runner,task_runtime
from ReportEngine import flask_interface
import config
fake=SimpleNamespace(**{k+'_ENGINE_API_KEY':'test-placeholder' for k in ['QUERY','MEDIA','INSIGHT','REPORT']})
with mock.patch.object(config,'settings',fake),mock.patch.object(flask_interface,'report_agent',True),mock.patch.object(research_runner,'start_research',return_value={'query':'started','media':'started','insight':'started'}) as runner:
 first=client.post('/pulse/api/revision/research',json={'query':'校园信息公开的事件研究','request_id':'same-request'})
 assert first.status_code==200,first.json
 task=first.json['task_id'];meta=task_runtime.read_task_metadata(task)
 assert meta['report_style']=='concise' and meta['report_template']==research.TEMPLATE
 second=client.post('/pulse/api/revision/research',json={'query':'校园信息公开的事件研究','request_id':'same-request'})
 assert second.json['task_id']==task and runner.call_count==1
 assert runner.call_args.args[1]=='校园信息公开的事件研究'
 assert client.get('/pulse/api/revision/research/'+task).status_code==200
 with client.session_transaction() as session:session['username']='another-account'
 assert client.get('/pulse/api/revision/research/'+task).status_code==404
checks+=['research authentication and ownership','invalid input and date filters','original three-engine runner called','concise template metadata','idempotent retries']
from ReportEngine.prompts.prompts import set_report_style,styled_prompt
set_report_style('concise');assert '不少于3万字' not in styled_prompt('CHAPTER_JSON')
assert '总字数约20000字' not in styled_prompt('WORD_BUDGET')
assert '例如主题团体辅导' not in styled_prompt('CHAPTER_JSON')
checks+=['concise mode skips educational activity stance']
directory=task_runtime.task_output_dir(task,'report')/'ir';directory.mkdir(parents=True,exist_ok=True)
paragraph='材料显示，校园信息公开讨论涉及信息时效与回应渠道。分析需核对原始发布时间和适用范围，结合不同群体的实际诉求理解表达差异。心理机制解释是基于证据的推断，后续应对照新材料继续观察。'
doc={'metadata':{'title':'校园信息公开事件分析'},'chapters':[{'title':title,'blocks':[{'type':'paragraph','inlines':[{'text':paragraph*6,'marks':[]}]},{'type':'paragraph','inlines':[{'text':'公开资料来源','marks':[{'type':'link','href':'https://example.com/source'}]}]}]} for title in ['事件概述与事实核验','传播脉络与公众关注','心理与社会机制','影响研判与后续观察']]}
(directory/'fixture.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
document=research.report_html(task);assert document.count('class="paper"')==4 and 'https://example.com/source' in document
path=research.pdf(task);assert path.read_bytes().startswith(b'%PDF')
pdf_bytes=path.read_bytes()
checks+=['four full chapters and sources retained','server PDF export with Chinese font']
doc['chapters'][0]['blocks'][0]['inlines'][0]['text']=paragraph*200
(directory/'fixture.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
try:research.pdf(task)
except ValueError as exc:assert '超出四页' in str(exc)
else:raise AssertionError('Overflow must be rejected rather than clipping text')
checks+=['report overflow rejected without clipping']
print(json.dumps({'passed':True,'checks':checks,'pdf_base64':base64.b64encode(pdf_bytes).decode(),'production_writes':False},ensure_ascii=False))
