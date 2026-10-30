"""Read existing reports to verify the deployed layout, without model/email calls."""
import json,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code=r'''import json,re
from bs4 import BeautifulSoup
from CampusPulse import research,weekly
from utils.task_runtime import list_task_ids,read_task_metadata
checks=[]
tasks=sorted([(t,read_task_metadata(t)) for t in list_task_ids()],key=lambda item:float(item[1].get('created_at') or 0),reverse=True)
for task_id,meta in tasks:
 if meta.get('pulse_revision')!=2:continue
 try:html=research.report_html(task_id)
 except (OSError,ValueError):continue
 soup=BeautifulSoup(html,'html.parser');body=soup.select_one('.report-body');refs=soup.select_one('.report-references')
 assert body is not None and refs is not None
 assert not body.select('a[href]')
 assert not re.search(r'https?://|\[[A-Z]\d+\]',body.get_text())
 md=research.markdown(task_id);assert '## 参考资料与原帖' in md
 assert not re.search(r'https?://',md.split('## 参考资料与原帖',1)[0])
 checks.append({'kind':'event','body_links':0,'appendix_links':len(refs.select('a[href]')),'markdown':True})
 if len(checks)>=2:break
for record in weekly.recent():
 if record['status']!='ready':continue
 row=weekly.get(record['id']);html=weekly.report_html(row);soup=BeautifulSoup(html,'html.parser')
 body=soup.select_one('.report-body');refs=soup.select_one('.report-references');summary=soup.select_one('.scope')
 assert body is not None and refs is not None and summary is not None
 assert not body.select('a[href]') and not re.search(r'https?://|\[[A-Z]\d+\]',body.get_text())
 assert str(row['data']['current_total'])+' 篇' in summary.get_text()
 checks.append({'kind':'weekly','body_links':0,'appendix_links':len(refs.select('a[href]')),'objective_summary':True});break
assert any(c['kind']=='event' for c in checks) and any(c['kind']=='weekly' for c in checks)
print(json.dumps({'passed':True,'checks':checks,'model_calls':0,'emails_sent':0}))
'''
remote='import subprocess,sys\nr=subprocess.run('+repr(['docker','exec','bettafish','python','-c',code])+',capture_output=True,timeout=100)\nsys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)'
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n python3 -'],input=remote.encode(),capture_output=True,timeout=120)
if r.returncode:print(r.stderr.decode(errors='replace')[-1800:]);raise SystemExit(r.returncode)
result=json.loads(r.stdout);(repo/'validation/references-live-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
