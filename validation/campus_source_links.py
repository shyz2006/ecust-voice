"""Read-only candidate link regression checks using existing stored rows."""
import pathlib,subprocess,base64,json
repo=pathlib.Path(__file__).resolve().parent.parent
source=base64.b64encode((repo/'production/CampusPulse/campus.py').read_bytes()).decode()
script=r'''
import types,base64,unittest.mock as mock,json,time,collections
from loguru import logger
logger.remove()
module=types.ModuleType('CampusPulse.candidate_campus');module.__file__='/app/CampusPulse/campus.py'
exec(compile(base64.b64decode(SOURCE),module.__file__,'exec'),module.__dict__)
annotation={'is_ad':False,'crisis_level':'无','theme':'考试考证','emotion':'中立'}
checks=[]
for src,extra,url,expected in [
 ('huyou-school',{},'https://hy.sns.sohu.com/?feedDetail=123456','https://hy.sns.sohu.com/?feedDetail=123456'),
 ('tieba-school',{'link':'https://tieba.baidu.com/p/123456'},None,'https://tieba.baidu.com/p/123456'),
 ('huyou-school',{'link':'https://hy.sns.sohu.com/?feedDetail=111111'},'https://hy.sns.sohu.com/?feedDetail=222222','https://hy.sns.sohu.com/?feedDetail=111111'),
 ('huyou-school',{},None,None)]:
 row={'source':src,'batch_ts':int(time.time()),'title':'考试报名时间安排核查','extra':extra,'url':url}
 with mock.patch.object(module.storage,'recent_items',return_value=[row]),mock.patch.object(module.storage,'kv_get',return_value=None),mock.patch.object(module,'_rule',return_value=annotation):
  got=module.theme_posts('考试考证',int(time.time()))['posts'];assert len(got)==1;assert got[0]['link']==expected
 checks.append({'source':src,'has_extra_link':bool(extra.get('link')),'has_row_url':bool(url),'passed':True})
live={}
for theme in ['考试考证','校园设施与管理']:
 posts=module.theme_posts(theme,int(time.time()))['posts']
 stats=collections.defaultdict(lambda:{'posts':0,'linked':0})
 for p in posts:stats[p['source']]['posts']+=1;stats[p['source']]['linked']+=bool(p.get('link'))
 assert posts and all(p.get('link') for p in posts), 'Expected existing addresses for displayed sample'
 live[theme]=dict(stats)
print(json.dumps({'passed':True,'fixture_checks':checks,'candidate_stored_data':live},ensure_ascii=False))
'''.replace('SOURCE',repr(source))
key=repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'
result=subprocess.run([r'E:\git\git\Git\usr\bin\ssh.exe','-i',str(key),'-o','BatchMode=yes','ubuntu@3.144.33.23','sudo -n docker exec -i bettafish python -'],input=script.encode(),capture_output=True,timeout=45)
if result.returncode:print(result.stderr.decode(errors='replace')[-1500:]);raise SystemExit(result.returncode)
data=json.loads(result.stdout);(repo.parent/'validation-artifacts/source-link-candidate-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(data,ensure_ascii=False))
