"""Read-only check of the existing backend report task; no session credentials needed."""
import pathlib,subprocess,shlex,json,sys
repo=pathlib.Path(__file__).resolve().parents[1];job=sys.argv[1]
code=r"""
import json,urllib.request
from utils.task_runtime import task_summary,task_output_dir
job=JOB
with urllib.request.urlopen('http://127.0.0.1:5000/api/report/status?research_task_id='+job,timeout=25) as response:state=json.load(response)
report=state.get('current_task') or {}
result={'engines':task_summary(job)['engines'],'report_status':report.get('status','not_started'),'report_progress':report.get('progress',0),'report_initialized':state.get('initialized'),
 'final_html_present':bool(list(task_output_dir(job,'report').glob('final_report_*.html'))),'restarted_research_engines':0,'emails_sent':0}
if result['final_html_present']:
 from CampusPulse.research import report_html
 try:body=report_html(job);result.update(validated_report=True,report_bytes=len(body.encode()))
 except ValueError as exc:result.update(validated_report=False,validation_message=str(exc))
if report.get('error_message'):result['report_error']=report['error_message'][:350]
print(json.dumps(result))
""".replace('JOB',repr(job))
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150',shlex.join(['sudo','-n','docker','exec','-i','bettafish','python','-'])],input=code.encode(),capture_output=True,timeout=65)
if r.returncode:print(r.stderr.decode(errors='replace')[-500:]);raise SystemExit(r.returncode)
value=json.loads(r.stdout);(repo/'validation/report-recovery-task-results.json').write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(value))
