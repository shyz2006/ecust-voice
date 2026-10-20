"""Real model/search in the isolated copy; never invoke mail delivery."""
import pathlib,subprocess,json,sys,shlex
sys.stdout.reconfigure(encoding="utf-8")
repo=pathlib.Path(__file__).resolve().parent.parent
code=r'''
import os,pathlib,json,time
root=next(pathlib.Path('/tmp').glob('campus-v3-validation-*'))
os.environ.update(PULSE_DB_PATH=str(root/'campus.db'),BETTAFISH_RUNTIME_DIR=str(root/'runtime'),SEARCH_GATEWAY_DB=str(root/'search.sqlite3'),LLM_SLOT_DIR=str(root/'llm_slots'),LLM_STATS_FILE=str(root/'llm_stats.json'))
from loguru import logger
logger.remove()
from CampusPulse import dynamic_memes as dm
from CampusPulse import weekly
weekly.initialize()
began=time.time();dm.scan();result=dm.snapshot()
(root/'dynamic-result.json').write_text(json.dumps(result,ensure_ascii=False))
summary={'status':dm.saved().get('status'),'seconds':round(time.time()-began),'observations':len(dm.corpus()),'verified':len(result['items']),'candidates':len(result['candidates']),'terms':[x['term'] for x in result['items']],'candidate_reasons':[{'term':x['term'],'uses':x['observed_count'],'reason':x['reason']} for x in result['candidates']],'isolated_database':True,'emails_sent':0}
print(json.dumps(summary,ensure_ascii=False))
'''
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','-o','ConnectTimeout=15','ubuntu@3.17.59.150',shlex.join(['sudo','-n','docker','exec','-i','bettafish-source-links-validation-web','python','-'])],input=code.encode(),capture_output=True,timeout=650)
if r.returncode:print(r.stderr.decode(errors='replace')[-1000:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/source-links-live-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(data,ensure_ascii=False))
