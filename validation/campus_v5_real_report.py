"""Generate one real weekly preview in an isolated database; never send mail."""
import pathlib,subprocess,json,base64,shlex
repo=pathlib.Path(__file__).resolve().parents[1]
code=r"""
import time,json,base64,os,pathlib,tempfile
databases=list(pathlib.Path('/tmp').glob('campus-v3-validation-*/campus.db'));assert len(databases)==1
tmp=pathlib.Path(tempfile.mkdtemp(prefix='weekly-model-check-'))
os.environ.update(PULSE_DB_PATH=str(databases[0]),BETTAFISH_RUNTIME_DIR=str(tmp/'runtime'),LLM_SLOT_DIR=str(tmp/'slots'),LLM_STATS_FILE=str(tmp/'stats.json'))
from loguru import logger
logger.remove()
from CampusPulse import weekly
assert not weekly.config()['enabled'] and not weekly.config()['key_configured']
report_id=weekly.start()
for _ in range(150):
 row=weekly.get(report_id)
 if row['status']!='generating':break
 time.sleep(2)
assert row['status']=='ready',row.get('error') or 'Weekly preview did not finish'
data=row['data'];document=weekly.report_html(row)
assert len(data['insights']['signals'])>=1
print(json.dumps({'passed':True,'report_id':report_id,'current_posts':data['current_total'],'previous_posts':data['previous_total'],'observed_days':data['observed_days'],'previous_observed_days':data['previous_observed_days'],'observations':len(data['insights']['signals']),'evidence_records':len(data['evidence']),'model':data['model'],'automatic_delivery_enabled':False,'emails_sent':0,'html_base64':base64.b64encode(document.encode()).decode()},ensure_ascii=False))
"""
args=['sudo','-n','docker','exec','-i','bettafish-campus-v5-validation-web','python','-']
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','-o','ServerAliveInterval=20','ubuntu@3.17.59.150',shlex.join(args)],input=code.encode(),capture_output=True,timeout=350)
if r.returncode:print(r.stderr.decode(errors='replace')[-800:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);document=base64.b64decode(data.pop('html_base64'));out=repo.parent/'validation-artifacts/campus-v5';out.mkdir(exist_ok=True);(out/'weekly-preview.html').write_bytes(document)
(repo/'validation/campus-v5-real-report-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(data,ensure_ascii=False))
