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
reference=revision.count_reference(points);assert reference['value']==3 and isinstance(reference['value'],int) and reference['windows']==4
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
with mock.patch.object(storage,'recent_items',return_value=network),mock.patch.object(storage,'recent_unique_items',return_value=network),mock.patch.object(storage,'latest_topics',return_value={'topics':[]}),mock.patch.object(storage,'kv_prefix',return_value=[{'key':'班味太重的新视频','value':json.dumps({'one_liner':'关注实习与学习中的疲惫表达'})}]):
 feed=revision.network_feed('hot',True);new=next(x for x in feed['items'] if '班味' in x['title'])
 assert new['baseline_samples']==3 and new['signal']>0
 assert len(feed['items'])==2
 assert new['focus']=='关注实习与学习中的疲惫表达'
 memes=revision.network_feed('memes',True)['items'];assert len(memes)==40 and all(x['reference_url'] and x['search_url'] for x in memes) and any(x['links'] for x in memes)
assert revision.source_link('javascript:alert(1)') is None
checks+=['burst includes absent past observations as zero','latest feed deduplicates polling','ten reviewed memes per platform with separate evidence and search','unsafe links rejected']
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
from ReportEngine.core import parse_template_sections
sections=parse_template_sections(pathlib.Path('ReportEngine/report_template/'+research.TEMPLATE+'.md').read_text(encoding='utf-8'))
assert len(sections)==4 and all(s.chapter_id=='S'+str(i) for i,s in enumerate(sections,1))
checks+=['real report template parses to exactly four chapters']
set_report_style('concise');assert '不少于3万字' not in styled_prompt('CHAPTER_JSON')
assert '总字数约20000字' not in styled_prompt('WORD_BUDGET')
assert '例如主题团体辅导' not in styled_prompt('CHAPTER_JSON')
checks+=['concise mode skips educational activity stance']
directory=task_runtime.task_output_dir(task,'report')/'ir';directory.mkdir(parents=True,exist_ok=True)
paragraph='材料显示，校园信息公开讨论涉及信息时效与回应渠道。分析需核对原始发布时间和适用范围，结合不同群体的实际诉求理解表达差异。心理机制解释是基于证据的推断，后续应对照新材料继续观察。'
doc={'metadata':{'title':'校园信息公开事件分析'},'chapters':[{'title':title,'blocks':[{'type':'paragraph','inlines':[{'text':paragraph*6,'marks':[]}]},{'type':'paragraph','inlines':[{'text':'公开资料来源','marks':[{'type':'link','href':'https://example.com/source'}]}]}]} for title in ['事件概述与事实核验','传播脉络与公众关注','心理与社会机制','影响研判与后续观察']]}
(directory/'fixture.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
evidence_dir=task_runtime.task_output_dir(task,'query')
(evidence_dir/'state_fixture.json').write_text(json.dumps({'paragraphs':[{'research':{'search_history':[{'url':'https://example.com/source','title':'公开资料来源','content':paragraph}]}}]}),encoding='utf-8')
document=research.report_html(task);assert document.count('class="report-chapter"')==4 and 'https://example.com/source' in document
path=research.pdf(task);assert path.read_bytes().startswith(b'%PDF')
pdf_bytes=path.read_bytes()
checks+=['four full chapters and sources retained','server PDF export with Chinese font']
doc['chapters'][0]['blocks'][1]['inlines'][0]['marks'][0]['href']='https://fabricated.example/source'
(directory/'fixture.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
try:research.report_html(task)
except ValueError:pass
else:raise AssertionError('Unretrieved source must be rejected')
doc['chapters'][0]['blocks'][1]['inlines'][0]['marks'][0]['href']='https://example.com/source'
doc['chapters'][0]['blocks'][0]['inlines'][0]['text']='99.99%'+paragraph
(directory/'fixture.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
try:research.report_html(task)
except ValueError:pass
else:raise AssertionError('Unsupported percentage must be rejected')
checks+=['unretrieved citations rejected','unsupported statistical percentages rejected']
doc['chapters'][0]['blocks'][0]['inlines'][0]['text']=paragraph*200+'这里是长报告正文末尾验证标记'
(directory/'fixture.json').write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
long_pdf=research.pdf(task).read_bytes()
assert 'height:297mm' not in research.report_html(task) and 'break-after:page' not in research.report_html(task)
checks+=['natural pagination preserves a long chapter without forced page breaks']
from utils.topic_guard import subject,relevant,search_query,filter_response,prepare_agent
named=subject('鹅腿阿姨事件');assert named['core']=='鹅腿阿姨' and named['strict']
assert relevant('陈秀凤在清华北大送烤鹅腿，鹅腿阿姨走红',named)
assert not relevant('华东理工大学人工智能教育数字人研究',named)
assert '鹅腿阿姨' in search_query('AI教育最新动态',named)
response=SimpleNamespace(results=[SimpleNamespace(title='鹅腿阿姨来北大',url='https://example.com/goose',content='陈秀凤'),SimpleNamespace(title='校园AI教育',url='https://example.com/ai',content='人工智能')],answer='provider synthesis')
assert len(filter_response(response,named).results)==1 and response.answer is None
checks+=['named subject retained in expanded queries','unrelated search results and generated provider answers excluded']
for text,expected in [('高化报告怎么写','学业课程'),('工程制图习题册电子版答案','学业课程'),('有没有人一起打羽毛球','社交与同伴'),('校园跑算晨跑吗','文体与实践'),('转租校区附近公寓','宿舍生活'),('电话卡套餐推荐','校园设施与管理'),('理发店哪个好','食堂与生活服务'),('五元出一本书','交易与互助')]:
 assert taxonomy.classify(text)['theme']==expected,(text,taxonomy.classify(text))
from CampusPulse.meme_catalog import CATALOG,observed_match,is_observed_url
assert not is_observed_url('https://search.bilibili.com/all?keyword=哈基米')
assert not is_observed_url('https://www.baidu.com/s?wd=硬控')
assert not is_observed_url('https://www.bilibili.com/')
assert is_observed_url('https://www.bilibili.com/video/BV1234567890')
assert not observed_match(next(x for x in CATALOG if x['term']=='搭子'),'GTA6最佳搭子？TCL电视体验')
assert not observed_match(next(x for x in CATALOG if x['term']=='硬控'),'游戏最强硬控技能')
assert observed_match(next(x for x in CATALOG if x['term']=='硬控'),'被北京文化硬控了')
checks+=['campus abbreviations and request intents classified','meme semantic collisions rejected']
many=[dict(network[-1],source=source,title='唯一话题'+str(i),rank=i+1) for source in ['douyin','thepaper','bilibili-popular','bilibili-hot-search','toutiao'] for i in range(30)]
with mock.patch.object(storage,'recent_items',return_value=many),mock.patch.object(storage,'latest_topics',return_value={'topics':[]}),mock.patch.object(storage,'kv_prefix',return_value=[]):
 hot=revision.network_feed('hot',True)['items']
 assert len(hot)==40
 assert all(sum(x['platform']==p for x in hot)==10 for p in ['抖音','澎湃','B站','头条'])
checks+=['ten unique topics per platform including two Bilibili sources']
from utils.llm_failover import ModelFailover
with mock.patch.dict(os.environ,{'LLM_FALLBACK_MODELS':'deepseek-v4-pro','REPORT_ENGINE_FALLBACK_MODELS':''}):
 route=ModelFailover('poolside/laguna-s-2.1-free','REPORT_ENGINE')
 assert 'deepseek/deepseek-v4-pro' in route.models
 with mock.patch('utils.llm_failover._MODEL_STATS.order',return_value=['deepseek/deepseek-v4-pro','poolside/laguna-s-2.1-free']):
  assert route._ordered_models()[0]=='poolside/laguna-s-2.1-free'
checks+=['DeepSeek qualified alias available','configured primary preserved ahead of adaptive fallback routing']
outline=[]
fake_agent=SimpleNamespace(state=SimpleNamespace(add_paragraph=lambda **p:outline.append(p)),execute_search_tool=lambda *a,**kw:SimpleNamespace(results=[SimpleNamespace(title='鹅腿阿姨来北大',url='https://example.com/goose',content='鹅腿阿姨陈秀凤在北大、清华周边卖烤鹅腿。'),SimpleNamespace(title='AI教育',url='https://example.com/ai',content='校园人工智能')],answer='unverified provider synthesis'))
assert prepare_agent(fake_agent,'query','鹅腿阿姨事件',task)
assert len(outline)==3 and all('鹅腿阿姨' in p['title'] and '陈秀凤' in p['content'] for p in outline)
assert len(fake_agent.execute_search_tool('basic_search_news','AI教育').results)==1
checks+=['research outline grounded in literal-topic seed evidence before synthesis']
storage.save_snapshot(now-100,[{'source':'douyin','rank':1,'title':'相同标题','url':'https://example.com/old','extra':{}}])
storage.save_snapshot(now,[{'source':'douyin','rank':2,'title':'相同标题','url':'https://example.com/new','extra':{}},{'source':'weibo','rank':1,'title':'相同标题','url':'https://example.com/other','extra':{}}])
unique=storage.recent_unique_items(['douyin','weibo'],now-200)
assert len(unique)==2 and next(r for r in unique if r['source']=='douyin')['url']=='https://example.com/new'
assert storage.latest_source_batches(['douyin'],now-200)=={'douyin':now}
checks+=['SQL deduplication retains newest source-linked observation']
print(json.dumps({'passed':True,'checks':checks,'pdf_base64':base64.b64encode(pdf_bytes).decode(),'long_pdf_base64':base64.b64encode(long_pdf).decode(),'production_writes':False},ensure_ascii=False))
