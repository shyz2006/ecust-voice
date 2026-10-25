import subprocess,json
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code=r'''
import json,copy,re
from html.parser import HTMLParser
from CampusPulse import weekly,report_contract
row=weekly.get('weekly_20261023_1400_40b5838f9d');assert row['status']=='ready'
data=row['data'];weekly.validate_insights(copy.deepcopy(data['insights']),data)
report=data['report'];ids={e['id'] for e in data['evidence']}
assert len(report['chapters'])==5
for c,(title,headings) in zip(report['chapters'],report_contract.CHAPTERS):
 assert c['title']==title;report_contract.validate_chapter(c,headings,ids)
assert 8000<=report['word_count']<=12000
html=weekly.report_html(row)
class Links(HTMLParser):
 def __init__(self):super().__init__();self.ids=set();self.refs=set()
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if a.get('id'):self.ids.add(a['id'])
  if a.get('href','').startswith('#'):self.refs.add(a['href'][1:])
p=Links();p.feed(html);assert not p.refs-p.ids
cfg=weekly.config(True);weekly.delivery_ready(cfg)
result={'status':'ready','chapters':len(report['chapters']),'sections':sum(len(c['sections']) for c in report['chapters']),'word_count':report['word_count'],'html_bytes':len(html.encode()),'linked_evidence':len(p.refs),'missing_reference_targets':len(p.refs-p.ids),'delivery_config_ready':True,'automatic_sending_enabled':cfg['enabled'],'send_time':cfg['send_time'],'weekday':cfg['weekday'],'recipient_count':len(cfg['recipients']),'send_attempts':row['send_attempts'],'emails_sent_this_validation':0}
print(json.dumps(result,ensure_ascii=True))
'''
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n docker exec -i bettafish python -'],input=code.encode(),capture_output=True,timeout=80)
if r.returncode:print(r.stderr.decode(errors='replace')[-700:]);raise SystemExit(r.returncode)
data=json.loads(r.stdout);(repo/'validation/report-weekly-live-recovery-results.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(data))
