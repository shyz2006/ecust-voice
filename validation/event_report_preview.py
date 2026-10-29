"""Build an offline rendering fixture inside the candidate, without model calls."""
import subprocess
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
code=r'''from unittest.mock import patch
from CampusPulse import research
md="## 一周关注\n\n**讨论焦点**与*表达倾向*。\n\n- 课程安排\n- 校园生活\n\n| 议题 | 新增讨论 |\n| --- | --- |\n| 课程 | 12 |\n| 生活 | 8 |\n\n```mermaid\nflowchart LR\n A[收集资料] --> B[核对来源] --> C[分析讨论] --> D[形成报告]\n```"
blocks=[{'type':'paragraph','inlines':[{'text':md}]},{'type':'widget','widgetType':'chart.js/line','props':{'title':'讨论变化 · 渲染测试数据'},'data':{'labels':['周一','周二','周三','周四','周五'],'datasets':[{'label':'新增讨论','data':[12,18,0,None,16]}]}},{'type':'widget','widgetType':'chart.js/doughnut','props':{'title':'话题构成 · 渲染测试数据'},'data':{'labels':['课程','生活','实践'],'datasets':[{'label':'讨论量','data':[12,8,5]}]}},{'type':'table','caption':'来源核对表','rows':[{'cells':[{'blocks':[{'type':'paragraph','inlines':[{'text':'原始材料','marks':[{'type':'bold'}]}]}]},{'blocks':[{'type':'paragraph','inlines':[{'text':'保留链接','marks':[{'type':'link','href':'https://example.com/evidence'}]}]}]}]}]}]
doc={'chapters':[{'title':'一、讨论概览','blocks':blocks},{'title':'二、后续关注','blocks':[{'type':'paragraph','inlines':[{'text':'正文连续排版，图表保留原始数值，缺测值不会自动补成零。'}]}]}]}
with patch.object(research,'report_document',return_value=doc),patch('utils.task_runtime.read_task_metadata',return_value={'query':'事件研究 · Markdown 与图表预览'}),patch('ReportEngine.evidence.source_evidence',return_value=[]):
 print(research.report_html('task_fixture'))
'''
remote='import subprocess,sys\nr=subprocess.run('+repr(['docker','run','--rm','--network','none','--entrypoint','python','bettafish:candidate-event-report-20261030-r1','-c',code])+',capture_output=True,timeout=60)\nsys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr);sys.exit(r.returncode)'
r=subprocess.run([r'E:/git/git/Git/usr/bin/ssh.exe','-i',str(repo.parent.parent/'亚马逊云 美国/aws-us-yzjp1test.pem'),'-o','BatchMode=yes','ubuntu@3.17.59.150','sudo -n python3 -'],input=remote.encode(),capture_output=True,timeout=90)
if r.returncode:print(r.stderr.decode(errors='replace')[-2000:]);raise SystemExit(r.returncode)
dest=repo.parent.parent/'分析资料/事件报告修复_20261030';dest.mkdir(parents=True,exist_ok=True);(dest/'报告渲染预览.html').write_bytes(r.stdout);print('Rendering fixture saved')
