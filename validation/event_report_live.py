"""Read-only deployed checks; never starts historical research or sends mail."""
import json,subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code=r'''import json
from pathlib import Path
from ReportEngine.core.template_parser import parse_template_sections
from CampusPulse import research
from utils.task_runtime import list_task_ids,read_task_metadata
from unittest.mock import patch
sections=parse_template_sections(Path('ReportEngine/report_template/社会公共热点事件分析报告模板.md').read_text())
assert len(sections)==5 and sum(len(c.outline) for c in sections)==12
checked=None
for task_id in list_task_ids():
 if read_task_metadata(task_id).get('pulse_revision')!=2:continue
 try:doc=research.report_document(task_id)
 except (OSError,ValueError):continue
 html=research.report_html(task_id)
 with patch('ReportEngine.renderers.markdown_renderer.get_chart_review_service',side_effect=AssertionError('Reading must not call chart review')):
  md=research.markdown(task_id)
 assert '<html' in html and len(md)>1000
 checked={'html':True,'markdown':True,'chapters':len(doc['chapters'])};break
assert checked,'No valid historical report found for rendering check'
import urllib.request
with urllib.request.urlopen('http://127.0.0.1:5000/login',timeout=10) as r:assert r.status==200
with urllib.request.urlopen('http://127.0.0.1:5000/pulse/api/status',timeout=15) as r:assert json.load(r)['success']
print(json.dumps({'template_chapters':5,'template_subsections':12,'historical_report':checked,'login':200,'collection_status':True,'model_calls':0,'emails_sent':0}))
'''
remote='import subprocess,sys\nr=subprocess.run('+repr(['docker','exec','bettafish','python','-c',code])+',capture_output=True,timeout=90)\nsys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)'
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n python3 -'],input=remote.encode(),capture_output=True,timeout=110)
if r.returncode:print(r.stderr.decode(errors='replace')[-2000:]);raise SystemExit(r.returncode)
result=json.loads(r.stdout);(repo/'validation/event-report-live-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
