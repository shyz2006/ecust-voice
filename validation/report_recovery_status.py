import json,urllib.request,hashlib
from pathlib import Path
from utils.task_runtime import task_output_dir
T='task_60222aa862abab486d14708fe7679dd3'
with urllib.request.urlopen('http://127.0.0.1:5000/api/report/status?research_task_id='+T,timeout=20) as r:s=json.load(r)
t=s.get('current_task') or {}
report={k:t.get(k) for k in ('task_id','status','progress','created_at','updated_at')}
reason=str(t.get('error_message') or '')
report['error_kind']='template_chapters' if '必须包含五章' in reason else ('validation' if any(w in reason for w in ('篇幅','小节','正文','校验')) else ('report_error' if reason else None))
files=task_output_dir(T,'report')
irs=[]
for p in (files/'ir').glob('*.json'):
 d=json.loads(p.read_text(encoding='utf-8'))
 from CampusPulse.report_contract import validate_ir,CHAPTERS
 from ReportEngine.evidence import validate_sources
 count=validate_ir(d);validate_sources(d,T)
 from CampusPulse.research import report_html,_text_blocks
 html=report_html(T)
 irs.append({'html_readable':isinstance(html,str) and len(html)>1000,'subsections':sum(h in ''.join(t for _,t,_ in _text_blocks(ch.get('blocks',[]))) for ch,(_,hs) in zip(d['chapters'],CHAPTERS) for h in hs),'chapters':len(d['chapters']),'body_characters':count,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
print(json.dumps({'report':report,'validated_reports':irs},ensure_ascii=True))
