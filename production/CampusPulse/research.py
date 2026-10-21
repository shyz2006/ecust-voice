"""Workshop adapter to the original BettaFish three-engine research/report runtime."""
import html,json,os,re,threading,time,hashlib
from pathlib import Path
from urllib.parse import urlsplit
from . import storage

TEMPLATE='校园与青年事件分析报告模板'
_init_lock=threading.Lock()
_pdf_lock=threading.Lock()

def start(query,username,request_id='',brief=None):
    from utils.task_runtime import ensure_task,new_task_id,register_task_account,task_metadata_path
    from utils.research_runner import start_research
    from ReportEngine import flask_interface
    with _init_lock:
        if not flask_interface.report_agent and not flask_interface.initialize_report_engine():
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
    meta.update(report_template=TEMPLATE,report_style='concise',pulse_revision=2)
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

def status(task_id):
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
            report_html(task_id)
            result.update(status='completed',report_url=f'/pulse/api/revision/research/{task_id}/report')
        except (ValueError,OSError):
            result.update(status='failed',error='报告未通过正文与原始来源检查，研究材料已保留。')
    elif any(v=='failed' or str(v).startswith('error') for v in result['engines'].values()):
        gaps=[task_output_dir(task_id,engine)/'research_information_gap.json' for engine in ('query','media')]
        messages=[json.loads(p.read_text(encoding='utf-8')).get('message') for p in gaps if p.exists()]
        result.update(status='failed',error=next((m for m in messages if isinstance(m,str) and m),'部分研究引擎未完成，请检查模型与检索服务后重试。'),information_gap=bool(messages))
    elif report and report.status in ('error','cancelled'):
        result.update(status='failed',error='报告汇总未完成，原始研究材料已保留。请检查报告模型后重试。')
    elif all(v=='completed' for v in result['engines'].values()):
        result.update(status='reporting',progress=getattr(report,'progress',0))
    else:result['status']='queued' if any(v=='queued' for v in result['engines'].values()) else 'running'
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

def report_html(task_id):
    from utils.task_runtime import task_output_dir,read_task_metadata
    from ReportEngine.evidence import validate_sources,source_evidence
    directory=task_output_dir(task_id,'report')
    files=list((directory/'ir').glob('*.json'))
    if not files:raise ValueError('报告正文尚未就绪')
    doc=json.loads(max(files,key=lambda p:p.stat().st_mtime).read_text(encoding='utf-8'))
    chapters=doc.get('chapters') or []
    if len(chapters)!=4:raise ValueError('报告章节数量待核查，请查看原始研究结果')
    validate_sources(doc,task_id)
    query=str(read_task_metadata(task_id).get('query') or (doc.get('metadata') or {}).get('title') or '事件分析报告')
    title=html.escape(query)
    catalogue={x['url']:x for x in source_evidence(task_id)}
    sections=[]
    for ch in chapters:
        blocks=_text_blocks(ch.get('blocks',[]));sources=[];body=[]
        for tag,text,links in blocks:
            refs=[]
            for url in dict.fromkeys(links):
                if url not in sources:sources.append(url)
                refs.append('<a href="'+html.escape(url,quote=True)+'" target="_blank" rel="noopener">['+str(sources.index(url)+1)+']</a>')
            body.append(f'<{tag}>'+html.escape(text)+(('<sup>'+''.join(refs)+'</sup>') if refs else '')+f'</{tag}>')
        for footnote in ch.get('footnotes',[]):
            if not isinstance(footnote,dict):continue
            text=footnote.get('text') or footnote.get('content')
            if isinstance(text,str):body.append('<p class="source">'+html.escape(text)+'</p>')
            url=footnote.get('href')
            if url in catalogue and url not in sources:sources.append(url)
        if not body:raise ValueError('报告章节正文为空，暂不能导出')
        for number,url in enumerate(sources,1):
            label=catalogue.get(url,{}).get('title') or urlsplit(url).hostname or '原始资料'
            display=label if len(label)<=100 else label[:100]+'…'
            body.append('<p class="source"><a href="'+html.escape(url,quote=True)+'" title="'+html.escape(label,quote=True)+'" target="_blank" rel="noopener">['+str(number)+'] '+html.escape(display)+'</a></p>')
        sections.append('<section class="report-chapter"><h2>'+html.escape(ch.get('title',''))+'</h2><article>'+''.join(body)+'</article></section>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>事件分析报告</title><style>
    *{box-sizing:border-box}body{margin:0;color:#24322e;background:#ebece7;font-family:"Noto Sans CJK SC","Noto Sans SC",sans-serif}.report{max-width:900px;padding:40px 48px;margin:24px auto;background:white}header{font-size:11px;color:#68766f;border-bottom:1px solid #bdcbc0;padding-bottom:12px}h1{font-size:26px;line-height:1.5;margin:22px 0 28px;overflow-wrap:anywhere}h2{font-size:20px;color:#285344;margin:28px 0 15px;break-after:avoid}h3{font-size:16px;break-after:avoid}article{font-size:15px;line-height:1.95;overflow-wrap:anywhere}p{margin:0 0 14px;white-space:pre-wrap;orphans:3;widows:3}.source{font-size:11px;color:#566b61;margin:7px 0;break-inside:avoid}a{color:inherit;text-underline-offset:3px}sup{margin-left:4px;font-size:10px}footer{margin-top:28px;padding-top:12px;border-top:1px solid #bdcbc0;font-size:10px;color:#68766f}@page{size:A4;margin:18mm 16mm 20mm}@media(max-width:640px){.report{margin:0;padding:24px 20px}h1{font-size:23px}}@media print{body{background:white}.report{max-width:none;padding:0;margin:0}article{font-size:11pt;line-height:1.8}h1{font-size:21pt}h2{font-size:15pt}p{break-inside:avoid}.source{font-size:8pt}}
    </style><body><main class="report"><header>校园与青年事件研究</header><h1>'''+title+'''</h1>'''+''.join(sections)+'''<footer>微舆三引擎研究 · 文中编号链接对应本章来源</footer></main></body></html>'''


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
                page.evaluate('document.fonts.ready')
                page.pdf(path=str(path),format='A4',print_background=True,prefer_css_page_size=True,
                         display_header_footer=True,header_template='<span></span>',
                         footer_template='<div style="width:100%;text-align:center;font-size:9px;color:#777"><span class="pageNumber"></span> / <span class="totalPages"></span></div>')
            finally:browser.close()
    return path
