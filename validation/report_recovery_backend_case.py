"""Offline regression checks; no model/search requests, research workers or mail."""
import os,tempfile,pathlib,json,time,copy,types
from unittest import mock
os.environ['BETTAFISH_RUNTIME_DIR']=tempfile.mkdtemp()
from loguru import logger
logger.remove()
from CampusPulse.config import settings
settings.db_path=pathlib.Path(tempfile.mkdtemp())/'case.db'
from CampusPulse import storage,research_brief as brief,research
from CampusPulse.blueprint import pulse_bp
from utils import topic_guard
from utils.task_runtime import ensure_task,read_task_metadata,task_output_dir
from flask import Flask
checks=[]
rows=[{'id':'S1','title':'武汉大学学生文理学科争论观察','url':'https://example.com/a','snippet':'武汉大学部分网络讨论围绕文科与理工科争论展开，帖子的具体指控仍待核查。'}]
choice={'title':'学科身份与网络争论','query':'武汉大学文科与理工科的学科争论如何产生和传播？','reason':'把“内战”作为网络比喻，核对讨论缘由与不同观点。','anchors':['武汉大学'],'focus_terms':['文科','理工科','学科争论'],'citations':[{'id':'S1','quote':'武汉大学部分网络讨论围绕文科与理工科争论展开'}]}
value={'directions':[choice],'question':'请补充时间'}
directions,_=brief.validate(value,'武汉大学内战','',rows);assert len(directions)==1
checks.append('metaphorical phrase resolved to evidence-linked neutral research scope')
for change in [dict(citations=[{'id':'S999','quote':choice['citations'][0]['quote']}]),dict(citations=[{'id':'S1','quote':'完全虚构的一段资料引用'}]),dict(query='清华大学争论')]:
 bad=copy.deepcopy(choice);bad.update(change);assert not brief.validate({'directions':[bad]},'武汉大学内战','',rows)[0]
checks.append('fabricated quotes, unknown sources, changed subjects rejected')
clear={'title':'校园食堂事件','query':'南京大学帝王蟹事件的事实经过与学生反应是什么？','reason':'核对事件经过。','anchors':['南京大学'],'focus_terms':['帝王蟹'],'citations':[{'id':'S1','quote':'南京大学帝王蟹事件的相关报道'}]}
assert brief.validate({'directions':[clear]},'南京大学帝王蟹事件','',[{'id':'S1','title':'南京大学帝王蟹事件的相关报道','snippet':'资料示例','url':'https://example.com/b'}])[0]
fallback=copy.deepcopy(choice);fallback['focus_terms']=['抽象研究视角'];assert brief.validate({'directions':[fallback]},'武汉大学内战','',rows)[0]
checks.append('explicit event preserves subject; missing lexical tags recovered only from matching scope and quote')
with mock.patch.object(brief,'summarize',return_value={'search_query':'武汉大学 文科 理工科 争论','ambiguous':True,'question':'你指的是学科争论吗？'}):assert brief.plan_query('武汉大学内战','')['ambiguous']
with mock.patch.object(brief,'summarize',return_value={'search_query':'清华大学 文理之争'}):
 try:brief.plan_query('武汉大学内战','')
 except ValueError:pass
 else:raise AssertionError('Planner swapped school')
checks.append('pre-search intent expansion retains original school; renamed subject rejected')
nav=[{'id':'S1','title':'武汉大学','url':'https://example.com/','snippet':'党委学生工作部 图书馆 通识教育 学习资源 学生会 研究生会'}]
nav_choice=dict(choice,query='武汉大学学生组织关系与校内冲突史研究',focus_terms=['学生','社团'],citations=[{'id':'S1','quote':'党委学生工作部 图书馆 通识教育 学习资源 学生会 研究生会'}])
assert not brief.validate({'directions':[nav_choice]},'武汉大学内战','',nav,ambiguous=True)[0]
checks.append('school navigation and generic student labels cannot substantiate an ambiguous conflict')

class NoThread:
 def __init__(self,*args,**kwargs):pass
 def start(self):pass
with mock.patch.object(brief.threading,'Thread',NoThread):
 pending=brief.start('武汉大学内战','','alice')
 assert brief.start('武汉大学内战','','alice')['id']==pending['id']
 try:brief.start('另一个主题','','alice')
 except ValueError:pass
 else:raise AssertionError('Concurrent different input reused incorrectly')
checks.append('duplicate requests share job; concurrent changed query rejected')
try:brief.get(pending['id'],'bob')
except ValueError:pass
else:raise AssertionError('Cross-account access')
checks.append('brief is private to requesting account')
search_rows=[{'title':x['title'],'url':x['url'],'snippet':x['snippet']} for x in rows]
with mock.patch.object(brief,'plan_query',return_value={'search_query':'武汉大学 文科 理工科 争论','ambiguous':True,'question':'是指学科争论吗？'}),mock.patch('CampusPulse.search.web_search',return_value=search_rows) as search,mock.patch.object(brief,'summarize',return_value=value) as model:
 brief._run(pending,'alice')
 assert search.call_count==model.call_count==1 and search.call_args.kwargs['plain'] is True
ready=brief.get(pending['id'],'alice');assert ready['status']=='ready'
with mock.patch.object(brief.threading,'Thread',NoThread):assert brief.start('武汉大学内战','','alice')['id']==ready['id']
checks.append('one Web Search, one intent model and one evidence model per uncached preparation; ready result reused')
confirmed=brief.confirmed(ready['id'],0,choice['query'],'alice')
assert confirmed['confirmed'] and confirmed['original_query']=='武汉大学内战'
for index,focus in [(True,choice['query']),(20,choice['query']),(0,'南京大学食堂研究')]:
 try:brief.confirmed(ready['id'],index,focus,'alice')
 except ValueError:pass
 else:raise AssertionError('Invalid confirmation accepted')
checks.append('selection and subject checked on confirmation')
task='task_brief_case';ensure_task(task,query=choice['query'])
from utils.task_runtime import task_metadata_path
p=task_metadata_path(task);meta=read_task_metadata(task);meta.update(pulse_revision=2,research_brief=confirmed);p.write_text(json.dumps(meta,ensure_ascii=False))
topic=topic_guard.task_subject(task)
assert topic_guard.relevant('武汉大学文科与理工科争论的网络讨论',topic)
assert not topic_guard.relevant('武汉大学食堂菜单与天气',topic)
assert not topic_guard.relevant('南京大学文理争论',topic)
assert not topic_guard.relevant('武汉大学附近历史军事战争',topic)
assert '内战' not in topic_guard.search_query('学科争论 学生观点',topic)
checks.append('semantic scope accepts relevant paraphrases, rejects unrelated and different-school sources')
class State:
 def __init__(self):self.paragraphs=[]
 def add_paragraph(self,**kw):self.paragraphs.append(kw)
agent=types.SimpleNamespace(state=State(),execute_search_tool=mock.Mock(side_effect=AssertionError('Repeated seed search')))
assert topic_guard.prepare_agent(agent,'query',choice['query'],task)
assert len(agent.state.paragraphs)==3 and '用户原始表达' in agent.state.paragraphs[0]['content']
from ReportEngine.evidence import source_evidence
assert source_evidence(task)[0]['url']=='https://example.com/a'
checks.append('confirmed preliminary sources reused and accepted by final report evidence gate')
app=Flask(__name__);app.secret_key='offline';app.register_blueprint(pulse_bp,url_prefix='/pulse');client=app.test_client()
assert client.post('/pulse/api/revision/research/brief',json={'query':'test'}).status_code==401
with client.session_transaction() as sess:sess['authenticated']=True;sess['username']='alice'
assert client.get('/pulse/api/revision/research/brief/'+ready['id']).status_code==200
assert client.post('/pulse/api/revision/research/brief',json={'query':'test'},headers={'Origin':'https://other.example'}).status_code==403
assert client.post('/pulse/api/revision/research/brief',json={'query':None}).status_code==400
assert client.post('/pulse/api/revision/research',json={'query':choice['query'],'brief_id':ready['id'],'direction':True}).status_code==400
with mock.patch.object(research,'start',return_value={'task_id':'task_mock','status':'running'}) as run:
 assert client.post('/pulse/api/revision/research',json={'query':choice['query'],'brief_id':ready['id'],'direction':0,'request_id':'r1'}).status_code==200
 assert run.call_args.kwargs['brief']['original_query']=='武汉大学内战'
checks.append('authenticated preview routes, malformed input and confirmed launch contract')
# No results ask for context rather than manufacturing a direction/model call.
empty=dict(pending,id='e'*32)
with mock.patch.object(brief,'plan_query',return_value={'search_query':'武汉大学 网络争论','ambiguous':True,'question':'请补充？'}),mock.patch('CampusPulse.search.web_search',return_value=[]),mock.patch.object(brief,'summarize') as model:
 brief._run(empty,'alice');assert model.call_count==0
assert not brief.get(empty['id'],'alice')['directions']
checks.append('no evidence leads to clarification question without evidence model or research generation')

# Completed initial screening permits immediate context refinement; new topics stay throttled.
with mock.patch.object(brief.threading,'Thread',NoThread):
 for owner in ('rate-refine','rate-new-topic'):
  first=brief.start('测试话题','',owner);first['status']='ready';storage.kv_set(brief._key(owner)+first['id'],json.dumps(first).encode())
 refined=brief.start('测试话题','补充研究范围','rate-refine');assert refined['context']=='补充研究范围'
 assert brief.start('测试话题','补充研究范围','rate-refine')['id']==refined['id']
 try:brief.start('另一个话题','','rate-new-topic')
 except ValueError:pass
 else:raise AssertionError('New-topic throttle removed')
checks.append('completed topic can be refined immediately; duplicate inflight joins, new-topic throttle retained')
alias_source=[{'id':'S1','title':'校园网络称谓讨论','url':'https://example.com/nickname','snippet':'有网友将北航称为清华健身房，该网络称谓的含义与传播语境需要核查。'}]
alias_choice={'title':'校园网络称谓的含义','query':'北京航空航天大学与清华大学相关的“清华健身房”网络称谓，其含义与传播语境是什么？','reason':'以网友表达为研究材料，具体说法需要核查。','anchors':['北京航空航天大学','清华大学'],'focus_terms':['清华健身房','传播语境'],'citations':[{'id':'S1','quote':'有网友将北航称为清华健身房，该网络称谓的含义与传播语境需要核查。'}]}
assert brief.validate({'directions':[alias_choice]},'清华健身房','北航是清华健身房',alias_source)[0]
assert topic_guard.relevant(alias_source[0]['snippet'],{'anchors':['北京航空航天大学','清华大学'],'terms':['清华健身房']})
wrong=copy.deepcopy(alias_choice);wrong['anchors']=['武汉大学'];assert not brief.validate({'directions':[wrong]},'清华健身房','北航是清华健身房',alias_source)[0]
checks.append('canonical university names match unambiguous user aliases and raw citations; unrelated school rejected')
with mock.patch.object(brief.threading,'Thread',NoThread):
 old=brief.start('缓存主题','','legacy-cache');old.update(status='ready',version=1);storage.kv_set(brief._key('legacy-cache')+old['id'],json.dumps(old).encode())
 fresh=brief.start('缓存主题','','legacy-cache');assert fresh['id']!=old['id'] and fresh['version']==brief.VERSION
checks.append('legacy empty-direction cache invalidated by preparation version after upgrade')

# Explicit user scope is accepted after zero-result preparation; references stay guarded.
with mock.patch.object(research,'start',return_value={'task_id':'task_manual','status':'running'}) as run:
 for background in ('补充第一轮','补充第一轮，第二轮，第三轮'):
  response=client.post('/pulse/api/revision/research',json={'query':'复旦王妃','brief_id':empty['id'],'context':background,'exploratory':True,'request_id':'manual-'+background})
  assert response.status_code==200,response.json
  scope=run.call_args.kwargs['brief'];assert scope['supplement']==background and scope['sources']==[] and scope['exploratory']
 assert client.post('/pulse/api/revision/research',json={'query':'自主研究问题','context':'补充','exploratory':True}).status_code==200
 assert client.post('/pulse/api/revision/research',json={'query':'自主研究问题','context':None,'exploratory':True}).status_code==400
 assert client.post('/pulse/api/revision/research',json={'query':'自主研究问题','context':'a'*501,'exploratory':True}).status_code==400
checks.append('zero directions and multiple supplements permit authenticated exploratory launch with current scope')
with client.session_transaction() as sess:sess['username']='mallory'
with mock.patch.object(research,'start') as run:
 assert client.post('/pulse/api/revision/research',json={'query':'复旦王妃','brief_id':empty['id'],'context':'补充','exploratory':True}).status_code==400
 assert not run.called
with client.session_transaction() as sess:sess['username']='alice'
assert brief.exploratory(ready['id'],choice['query'],'','alice',0)['anchors']==['武汉大学']
new_context=brief.exploratory(ready['id'],choice['query'],'新补充','alice',0)
assert new_context['anchors']==['武汉大学'] and new_context['supplement']=='新补充' and not new_context['sources']
checks.append('owner isolation retained and unchanged evidence-backed direction retains semantic anchors')
from utils.task_runtime import task_metadata_path
manual='task_manual_gap';ensure_task(manual,query='复旦王妃')
path=task_metadata_path(manual);metadata=json.loads(path.read_text());metadata.update(pulse_revision=2,research_brief=brief.exploratory(empty['id'],'复旦王妃','用户的最新补充','alice'));path.write_text(json.dumps(metadata))
search=mock.Mock(return_value=types.SimpleNamespace(results=[],answer='unverified answer'))
agent=types.SimpleNamespace(state=State(),execute_search_tool=search)
try:topic_guard.prepare_agent(agent,'query','复旦王妃',manual)
except ValueError as exc:assert '原始资料' in str(exc)
else:raise AssertionError('Empty evidence bypassed')
assert '用户的最新补充' in search.call_args.args[1]
assert (task_output_dir(manual,'query')/'research_information_gap.json').exists()
with mock.patch('utils.task_runtime.task_summary',return_value={'engines':{'query':'failed','media':'running','insight':'running'}}):
 result=research.status(manual);assert result['information_gap'] and '原始资料' in result['error']
assert not topic_guard.relevant('无关明星新闻',topic_guard.task_subject(manual))
checks.append('supplement reaches retrieval; empty evidence produces explicit information gap and unrelated evidence stays rejected')

# Test-only snippets: entity relationships are candidate clues, never established facts.
assert brief.validate({'directions':[alias_choice]},'清华健身房','',alias_source)[0]
checks.append('related entity allowed without user pre-typing it when same raw quote connects both subjects')
separate=[{'id':'S1','title':'清华健身房网络称谓讨论','url':'https://example.com/root','snippet':'清华健身房这一说法的具体指代与传播语境有待核实。'}, {'id':'S2','title':'北航运动讨论','url':'https://example.com/unrelated','snippet':'北航学生在讨论健身房锻炼与日常运动安排。'}]
spliced=dict(alias_choice,citations=[{'id':'S1','quote':separate[0]['snippet']},{'id':'S2','quote':separate[1]['snippet']}])
assert not brief.validate({'directions':[spliced]},'清华健身房','',separate)[0]
checks.append('separate unrelated search results cannot manufacture an entity relationship')
with mock.patch.object(brief.threading,'Thread',NoThread):
 legacy=brief.start('旧歧义方向','','v2-cache');legacy.update(status='ready',version=2);storage.kv_set(brief._key('v2-cache')+legacy['id'],json.dumps(legacy).encode())
 assert brief.start('旧歧义方向','','v2-cache')['id']!=legacy['id']
checks.append('v2 screening cache refreshed for new query planning and entity validation rules')

from ReportEngine import flask_interface as report_api
# Background generation after a cold process initializes once, without needing a new research.
with mock.patch.object(report_api,'report_agent',None),mock.patch.object(report_api,'initialize_report_engine',side_effect=lambda:setattr(report_api,'report_agent',True) or True) as init:
 assert report_api.ensure_report_engine() and report_api.ensure_report_engine();assert init.call_count==1
checks.append('cold report service initializes once without a new research task')
report_app=Flask('report-test');report_app.register_blueprint(report_api.report_bp,url_prefix='/api/report')
with mock.patch.object(report_api,'report_agent',None),mock.patch.object(report_api,'initialize_report_engine',side_effect=lambda:setattr(report_api,'report_agent',True) or True) as init,mock.patch.object(report_api,'check_engines_ready',return_value={'ready':False,'missing_files':['fixture']}):
 response=report_app.test_client().post('/api/report/generate',json={'research_task_id':task,'query':choice['query']});assert response.status_code==400 and init.call_count==1
checks.append('actual generate endpoint initializes before checking material readiness')
with mock.patch('utils.task_runtime.task_summary',return_value={'engines':{'query':'completed','media':'completed','insight':'completed'}}),mock.patch.object(report_api,'tasks_registry',{}):
 state=research.status(manual);assert state['status']=='awaiting_report' and state['can_resume_report']
checks.append('completed engines without a live report are actionable pending state rather than reporting forever')
with mock.patch('utils.research_runner.all_engines_completed',return_value=True),mock.patch('requests.post',return_value=types.SimpleNamespace(status_code=200,json=lambda:{'success':True})) as request:
 assert research.resume_report(task)['status']=='reporting';assert request.call_args.kwargs['json']['research_task_id']==task
with mock.patch('utils.research_runner.all_engines_completed',return_value=True),mock.patch('requests.post',return_value=types.SimpleNamespace(status_code=409,json=lambda:{'current_task':{'status':'running'}})):
 assert research.resume_report(task)['reused']
with mock.patch.object(research,'authorize',return_value=False),mock.patch.object(research,'resume_report') as resume:
 assert client.post('/pulse/api/revision/research/'+task+'/resume-report',json={}).status_code==404;assert not resume.called
with mock.patch.object(research,'authorize',return_value=True),mock.patch.object(research,'resume_report',return_value={'task_id':task,'status':'reporting'}) as resume:
 assert client.post('/pulse/api/revision/research/'+task+'/resume-report',json={}).status_code==200;assert resume.call_count==1
 assert client.post('/pulse/api/revision/research/'+task+'/resume-report',json={},headers={'Origin':'https://other.example'}).status_code==403
checks.append('final-only retry reuses running reports, preserves task scope, and enforces owner and origin checks')
print(json.dumps({'passed':True,'checks':checks,'groups':len(checks),'external_requests':0,'emails_sent':0},ensure_ascii=False))
