"""Workshop adapter to the original BettaFish three-engine research/report runtime."""
import html,json,os,re,threading,time,hashlib
from pathlib import Path
from urllib.parse import urlsplit
from . import storage

TEMPLATE='社会公共热点事件分析报告模板'
_init_lock=threading.Lock()
_pdf_lock=threading.Lock()
_resume_lock=threading.Lock()
_resume_jobs={}

def start(query,username,request_id='',brief=None):
    from utils.task_runtime import ensure_task,new_task_id,register_task_account,task_metadata_path
    from utils.research_runner import start_research
    from ReportEngine import flask_interface
    with _init_lock:
        if not flask_interface.report_agent and not flask_interface.ensure_report_engine():
            raise RuntimeError('报告服务初始化失败，请在配置中检查研究模型')
    from config import settings
    missing=[label for prefix,label in [('QUERY','查询'),('MEDIA','媒体'),('INSIGHT','洞察'),('REPORT','报告')]
             if not getattr(settings,prefix+'_ENGINE_API_KEY',None)]
    if missing:raise ValueError('请先配置'+ '、'.join(missing)+'模型')
    task_id='task_'+hashlib.sha256((username+'|'+request_id).encode()).hexdigest()[:32] if request_id else new_task_id()
    from utils.task_runtime import read_task_metadata
    previous=read_task_metadata(task_id)
    if previous.get('pulse_revision')==2:
        if previous.get('query')!=query:raise ValueError('请求编号已用于其他主题，请重新提交')
        return {'task_id':task_id,'status':status(task_id)['status'],'reused':True}
    ensure_task(task_id,query=query);register_task_account(task_id,username)
    path=task_metadata_path(task_id);meta=json.loads(path.read_text())
    meta.update(report_template=TEMPLATE,report_style='public_event',pulse_revision=2,auto_report=True)
    if brief:meta['research_brief']=brief
    temp=path.with_suffix('.revision.tmp');temp.write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8');os.replace(temp,path)
    from ForumEngine.task_store import initialize_task_forum
    initialize_task_forum(task_id)
    state=start_research(task_id,query)
    return {'task_id':task_id,'engines':state,'status':'running'}

def authorize(task_id,username):
    from utils.task_runtime import validate_runtime_id,task_has_account,read_task_metadata
    validate_runtime_id(task_id)
    return bool(username and task_has_account(task_id,username) and read_task_metadata(task_id).get('pulse_revision')==2)

def status(task_id, auto=True):
    from utils.task_runtime import task_summary,task_output_dir
    from ReportEngine import flask_interface
    result=task_summary(task_id)
    reports=list(task_output_dir(task_id,'report').glob('final_report_*.html'))
    with flask_interface.task_lock:
        current=[t for t in flask_interface.tasks_registry.values() if t.research_task_id==task_id]
    current=sorted(current,key=lambda t:t.created_at if hasattr(t,'created_at') else 0)
    report=current[-1] if current else None
    if reports:
        try:
            report_document(task_id)
            result.update(status='completed',report_url=f'/pulse/api/revision/research/{task_id}/report')
        except (ValueError,OSError):
            if report and report.status in ('pending','running'):
                result.update(status='reporting',progress=getattr(report,'progress',0))
            else:
                result.update(status='failed',error='报告未通过正文与原始来源检查，研究材料已保留，可继续生成报告。',can_resume_report=True)
    elif any(v=='failed' or str(v).startswith('error') for v in result['engines'].values()):
        gaps=[task_output_dir(task_id,engine)/'research_information_gap.json' for engine in ('query','media')]
        messages=[json.loads(p.read_text(encoding='utf-8')).get('message') for p in gaps if p.exists()]
        result.update(status='failed',error=next((m for m in messages if isinstance(m,str) and m),'部分研究引擎未完成，请检查模型与检索服务后重试。'),information_gap=bool(messages))
    elif report and report.status in ('error','cancelled'):
        reason = str(getattr(report,'error_message','') or '')
        message = ('报告模板章节未通过检查，请更新服务后继续生成。' if '必须包含五章' in reason else
                   '报告正文未通过篇幅或小节检查，可继续生成最终报告。' if any(x in reason for x in ('篇幅','小节','字数','正文须')) else
                   '报告汇总未完成，研究材料已保留，可继续生成最终报告。')
        from .report_automation import _permanent
        result.update(status='failed',error=message,can_resume_report=True,automatic_retry_allowed=report.status!='cancelled' and not _permanent({'error':reason}))
    elif all(v=='completed' for v in result['engines'].values()):
        if report and report.status in ('pending','running'):
            result.update(status='reporting',progress=getattr(report,'progress',0))
        else:
            result.update(status='awaiting_report',progress=0,message='研究材料已齐备，最终报告尚未启动，可继续生成报告。',can_resume_report=True)
    else:result['status']='queued' if any(v=='queued' for v in result['engines'].values()) else 'running'
    with _resume_lock:
        recovery=dict(_resume_jobs.get(task_id) or {})
    if recovery.get('pending'):
        result.update(status='reporting',can_resume_report=False,error=None,message='正在启动报告汇总，研究材料已保留。')
    elif recovery.get('error') and result.get('status') not in ('completed','reporting'):
        result.update(status='failed',can_resume_report=True,error=recovery['error'])
    if auto and result.get('status') not in ('completed','running','queued','reporting'):
        from .report_automation import waiting_message
        message=waiting_message(task_id,result)
        if message:result.update(status='reporting',can_resume_report=False,error=None,message=message)
    return result

def history(username):
    from utils.task_runtime import list_task_ids
    records=[]
    for task_id in list_task_ids():
        if authorize(task_id,username):records.append(status(task_id))
    return sorted(records,key=lambda x:x['created_at'],reverse=True)[:30]

def _text_blocks(block):
    if isinstance(block,list):
        return [text for child in block for text in _text_blocks(child)]
    if not isinstance(block,dict):return []
    kind=block.get('type')
    if kind=='table':
        out=[]
        for row in block.get('rows',[]):
            cells=[_text_blocks(cell) for cell in row.get('cells',[])]
            text=' ｜ '.join('；'.join(item[1] for item in cell) for cell in cells)
            out.append(('p',text,[url for cell in cells for item in cell for url in item[2]]))
        return out
    if kind=='paragraph':
        content=''.join(str(x.get('text','')) for x in block.get('inlines',[])
                        if not (str(x.get('text','')).strip() in ('来源','原文','参考','出处')
                                and any(m.get('type')=='link' for m in x.get('marks',[]))))
        links=[]
        for inline in block.get('inlines',[]):
            for mark in inline.get('marks',[]):
                url=mark.get('href') or (mark.get('value') if mark.get('type')=='link' else None)
                if isinstance(url,str) and url.startswith(('http://','https://')):links.append(url)
        return [('p',content,links)] if content or links else []
    if kind in ('markdown','text') or (kind=='code' and str(block.get('lang','')).lower() in ('md','markdown')):
        return [('p',str(block.get('content') or block.get('text') or ''),[])]
    if kind=='heading':return [('h3',str(block.get('text','')),[])]
    out=[]
    for key in ('blocks','children','items','rows','cells','content','body'):
        value=block.get(key)
        if isinstance(value,(list,dict)):out.extend(_text_blocks(value))
    if not out and isinstance(block.get('text'),str):out=[('p',block['text'],[])]
    if not out and kind=='figure':
        caption=block.get('caption') or block.get('title')
        if isinstance(caption,str):out=[('p',caption,[])]
    return out

def report_document(task_id):
    from utils.task_runtime import task_output_dir,read_task_metadata
    from ReportEngine.evidence import validate_sources
    directory=task_output_dir(task_id,'report')
    files=list((directory/'ir').glob('*.json'))
    if not files:raise ValueError('报告正文尚未就绪')
    doc=json.loads(max(files,key=lambda p:p.stat().st_mtime).read_text(encoding='utf-8'))
    chapters=doc.get('chapters') or []
    style=read_task_metadata(task_id).get('report_style')
    expected=5 if style=='public_event' else 4
    if len(chapters)!=expected:raise ValueError('报告章节数量待核查，请查看原始研究结果')
    if style=='public_event':
        from .report_contract import validate_ir
        validate_ir(doc)
    validate_sources(doc,task_id)
    return doc


def report_html(task_id):
    from utils.task_runtime import read_task_metadata
    from ReportEngine.evidence import source_evidence
    doc=report_document(task_id)
    query=str(read_task_metadata(task_id).get('query') or (doc.get('metadata') or {}).get('title') or '事件分析报告')
    catalogue={x['url']:x for x in source_evidence(task_id)}
    return render_document(doc,query,catalogue)


def render_document(doc,query,catalogue):
    from .report_rendering import ReportRenderer,STYLE,esc,safe_url
    chapters=doc.get('chapters') or []
    from .report_references import References
    references=References(catalogue)
    renderer=ReportRenderer(references=references);sections=[]
    title=references.clean(query) or '事件分析报告'
    for ch in chapters:
        renderer.chapter_data=ch.get('data') or {}
        body=renderer.blocks(ch.get('blocks') or [])
        if not body and not ch.get('footnotes'):raise ValueError('报告章节正文为空，暂不能导出')
        for footnote in ch.get('footnotes') or []:
            if isinstance(footnote,dict):references.note(footnote)
        sections.append('<section class="report-chapter"><h2>'+esc(references.clean(ch.get('title','')))+'</h2><article>'+body+'</article></section>')
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+esc(title)+'</title><style>'+STYLE+'</style></head><body><main class="report"><header>校园与青年事件研究</header><h1>'+esc(title)+'</h1><div class="report-body">'+''.join(sections)+'</div>'+references.html()+'<footer>微舆三引擎研究 · 参考资料与原帖集中列于文末</footer></main>'+renderer.scripts()+'</body></html>'


def markdown(task_id):
    from utils.task_runtime import read_task_metadata
    from ReportEngine.renderers.markdown_renderer import MarkdownRenderer
    from .report_references import References
    from ReportEngine.evidence import source_evidence
    references=References({x['url']:x for x in source_evidence(task_id)})
    doc=references.document(report_document(task_id))
    title=references.clean(read_task_metadata(task_id).get('query') or '事件分析报告')
    doc['metadata']=dict(doc.get('metadata') or {},title=title)
    return MarkdownRenderer().render(doc,review_charts=False)+references.markdown()


def pdf(task_id):
    from playwright.sync_api import sync_playwright
    from utils.task_runtime import task_output_dir
    path=task_output_dir(task_id,'report')/'research-report.pdf'
    with _pdf_lock:
        content=report_html(task_id)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                page=browser.new_page();page.set_content(content,wait_until='load')
                page.evaluate('window.reportReady || document.fonts.ready')
                page.wait_for_function('window.reportRenderComplete === true',timeout=30000)
                page.pdf(path=str(path),format='A4',print_background=True,prefer_css_page_size=True,
                         display_header_footer=True,header_template='<span></span>',
                         footer_template='<div style="width:100%;text-align:center;font-size:9px;color:#777"><span class="pageNumber"></span> / <span class="totalPages"></span></div>')
            finally:browser.close()
    return path


def _submit_report(task_id):
    """Retry only final synthesis; preserve all three completed research outputs."""
    from utils.task_runtime import read_task_metadata
    from utils.research_runner import all_engines_completed,_config_port
    import requests
    if not all_engines_completed(task_id):raise ValueError('请等待三个研究引擎完成')
    response=requests.post('http://127.0.0.1:'+str(_config_port())+'/api/report/generate',
                           json={'research_task_id':task_id,'query':read_task_metadata(task_id).get('query',''),'regenerate':True},timeout=120)
    value=response.json()
    if response.status_code==409 and value.get('current_task',{}).get('status') in ('pending','running'):
        return {'task_id':task_id,'status':'reporting','reused':True}
    if response.status_code!=200 or not value.get('success'):raise ValueError('最终报告未能启动，请检查报告模型配置后重试')
    return {'task_id':task_id,'status':'completed' if value.get('existing') else 'reporting'}


def resume_report(task_id, automatic=False):
    """Accept recovery promptly; polling follows the background submission and generation."""
    from utils.research_runner import all_engines_completed
    if not all_engines_completed(task_id):
        raise ValueError('请等待三个研究引擎完成')
    if not automatic:
        from .report_automation import enable
        enable(task_id)
    with _resume_lock:
        if (_resume_jobs.get(task_id) or {}).get('pending'):
            return {'task_id':task_id,'status':'reporting','reused':True}
        _resume_jobs[task_id]={'pending':True}
    def submit():
        try:
            _submit_report(task_id)
        except Exception:
            with _resume_lock:
                _resume_jobs[task_id]={'pending':False,'error':'报告启动暂未确认，请稍后重试；研究材料已保留。'}
        else:
            with _resume_lock:
                _resume_jobs.pop(task_id,None)
    try:
        threading.Thread(target=submit,daemon=True,name='report-resume-'+task_id).start()
    except Exception:
        with _resume_lock:_resume_jobs.pop(task_id,None)
        raise
    return {'task_id':task_id,'status':'reporting'}
