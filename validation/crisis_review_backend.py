"""Candidate risk endpoint tests in a separate Flask app; read-only stored-data check."""
import pathlib,subprocess,base64,json
repo=pathlib.Path(__file__).resolve().parent.parent
script=r'''
import base64,types,json,time,unittest.mock as mock
from flask import Flask
from loguru import logger
logger.remove()
import CampusPulse
from CampusPulse import storage
candidate=types.ModuleType('CampusPulse.crisis_candidate')
exec(compile(base64.b64decode(CAMPUS),'/app/CampusPulse/campus.py','exec'),candidate.__dict__)
bp=types.ModuleType('CampusPulse.crisis_blueprint_candidate');bp.__file__='/app/CampusPulse/blueprint.py'
exec(compile(base64.b64decode(BLUEPRINT),bp.__file__,'exec'),bp.__dict__)
app=Flask('isolated-crisis-validation');app.secret_key='test-only';app.register_blueprint(bp.pulse_bp,url_prefix='/pulse')
client=app.test_client();now=int(time.time())
fixtures=[
 {'source':'huyou-school','batch_ts':now-100,'title':'高风险核查样例甲','url':'https://hy.sns.sohu.com/?feedDetail=12345','extra':{}},
 {'source':'huyou-school','batch_ts':now-50,'title':'高风险核查样例甲','url':'https://hy.sns.sohu.com/?feedDetail=12345','extra':{}},
 {'source':'tieba-school','batch_ts':now-200,'title':'关注核查样例乙','url':None,'extra':{'link':'https://tieba.baidu.com/p/54321'}},
 {'source':'huyou-school','batch_ts':now-300,'title':'普通选课样例丙','url':'https://hy.sns.sohu.com/?feedDetail=67890','extra':{}},
 {'source':'huyou-national','batch_ts':now-400,'title':'全国风险样例丁','url':None,'extra':{}},
 {'source':'huyou-school','batch_ts':now+200,'title':'快照之后样例戊','url':None,'extra':{}},
]
def annotation(content):
 return {'theme':'其他','emotion':'中性','psych_dimensions':[],'crisis_level':'关注' if '乙' in content else '高危' if any(x in content for x in ['甲','丁','戊']) else '无','is_ad':False,'content_risk':'无','gist':'','annotator':'test'}
def cache(key):
 if key=='campus_voice':return json.dumps({'generated_at':now})
 for row in fixtures:
  if key==candidate._PREFIX+candidate._hash(row['title']):return json.dumps(annotation(row['title']))
 return None
with mock.patch.object(CampusPulse,'campus',candidate),mock.patch.object(storage,'recent_items',return_value=fixtures),mock.patch.object(storage,'kv_get',side_effect=cache),mock.patch.object(candidate,'_near_dup',side_effect=lambda a,b:a==b),mock.patch.object(candidate,'_rule',side_effect=annotation),mock.patch.object(candidate,'annotate_posts',side_effect=lambda posts,_:{candidate._hash(p['content']):annotation(p['content']) for p in posts}),mock.patch.object(candidate.llm,'chat',side_effect=AssertionError('No model calls')):
 unauth=client.get('/pulse/api/campus/crisis-posts?level=高危');assert unauth.status_code==401 and 'posts' not in unauth.json
 with client.session_transaction() as sess:sess['authenticated']=True;sess['username']='validation'
 assert client.get('/pulse/api/campus/crisis-posts?level=无').status_code==400
 summary=candidate.summarize(now,False)
 for level in ['高危','关注']:
  response=client.get('/pulse/api/campus/crisis-posts',query_string={'level':level});assert response.status_code==200 and response.headers['Cache-Control']=='no-store'
  data=response.json;assert data['total']==summary['crisis'][level]==1
  assert len(data['posts'])==1 and data['posts'][0]['link']
  assert all(p['crisis_level']==level for p in data['posts'])
  assert data['posts'][0]['time_basis']=='first_observed'
 assert not candidate.theme_posts('其他',now)['posts'] or all(p['crisis_level']=='无' for p in candidate.theme_posts('其他',now)['posts'])
# Compare candidate risks with stored summary, without emitting content or addresses.
with mock.patch.object(CampusPulse,'campus',candidate):
 voice=json.loads(storage.kv_get('campus_voice') or '{}')
 live={}
 for level in ['高危','关注']:
  response=client.get('/pulse/api/campus/crisis-posts',query_string={'level':level});assert response.status_code==200
  data=response.json;assert all(p['crisis_level']==level for p in data['posts'])
  expected=voice.get('crisis',{}).get(level)
  assert expected is None or data['total']==expected,(level,data['total'],expected)
  live[level]={'posts':data['total'],'linked':sum(bool(p.get('link')) for p in data['posts']),'matches_summary':data['total']==expected}
print(json.dumps({'passed':True,'fixture_checks':['unauthenticated 401','invalid level 400','no-store','separate levels','same summary counts','duplicate polls merged','national excluded','snapshot end enforced','source URL fallback','first observed time','ordinary themes retain filtering','no model calls'],'stored_data':live,'production_writes':False},ensure_ascii=False))
'''
script=script.replace('CAMPUS',repr(base64.b64encode((repo/'production/CampusPulse/campus.py').read_bytes()).decode())).replace('BLUEPRINT',repr(base64.b64encode((repo/'production/CampusPulse/blueprint.py').read_bytes()).decode()))
key=repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'
r=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(key),'-o','BatchMode=yes','ubuntu@3.144.33.23','sudo -n docker exec -i bettafish python -'],input=script.encode(),capture_output=True,timeout=70)
if r.returncode:print(r.stderr.decode(errors='replace')[-1800:]);raise SystemExit(r.returncode)
d=json.loads(r.stdout);(repo/'validation/crisis-review-backend-results.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(d,ensure_ascii=False))
