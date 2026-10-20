"""Workshop adapter to the original BettaFish three-engine research/report runtime."""
import html,json,os,re,threading,time,hashlib
from pathlib import Path
from urllib.parse import urlsplit
from . import storage

TEMPLATE='校园与青年事件分析报告模板'
_init_lock=threading.Lock()
_pdf_lock=threading.Lock()

def start(query,username,request_id=''):
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
            result.update(status='failed',error='报告正文未通过四章完整性检查，研究材料已保留。')
    elif any(v=='failed' or str(v).startswith('error') for v in result['engines'].values()):
        result.update(status='failed',error='部分研究引擎未完成，请检查模型与检索服务后重试。')
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
    if kind=='paragraph':
        content=''.join(str(x.get('text','')) for x in block.get('inlines',[]))
        links=[]
        for inline in block.get('inlines',[]):
            for mark in inline.get('marks',[]):
                url=mark.get('href') or (mark.get('value') if mark.get('type')=='link' else None)
                if isinstance(url,str) and url.startswith(('http://','https://')):links.append(url)
        return [('p',content,links)] if content else []
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
    directory=task_output_dir(task_id,'report')
    files=list((directory/'ir').glob('*.json'))
    if not files:raise ValueError('报告正文尚未就绪')
    doc=json.loads(max(files,key=lambda p:p.stat().st_mtime).read_text(encoding='utf-8'))
    chapters=doc.get('chapters') or []
    if len(chapters)!=4:raise ValueError('报告章节数量待核查，请查看原始研究结果')
    title=html.escape(str((doc.get('metadata') or {}).get('title') or read_task_metadata(task_id).get('query') or '事件分析报告'))
    sections=[]
    for i,ch in enumerate(chapters,1):
        blocks=_text_blocks(ch.get('blocks',[]));sources=[];body=[]
        for tag,text,links in blocks:
            body.append(f'<{tag}>{html.escape(text)}</{tag}>');sources.extend(links)
        # Chapter footnotes remain attached to their source chapter.
        for footnote in ch.get('footnotes',[]):
            if isinstance(footnote,dict):
                text=footnote.get('text') or footnote.get('content')
                if isinstance(text,str):body.append('<p class="source">'+html.escape(text)+'</p>')
        if not body:raise ValueError('报告章节正文为空，暂不能导出')
        for number,url in enumerate(dict.fromkeys(sources),1):
            label=urlsplit(url).hostname or '原始资料'
            body.append('<p class="source"><a href="'+html.escape(url,quote=True)+'">来源 '+str(number)+'：'+html.escape(label)+'</a></p>')
        sections.append(f'<section class="paper"><header>校园与青年事件研究 · {i}/4</header><h1>{title}</h1><h2>{html.escape(ch.get("title", ""))}</h2><article>'+''.join(body)+'</article><footer>微舆三引擎研究 · 事实与分析请结合文中来源阅读</footer></section>')
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>事件分析报告</title><style>
    *{box-sizing:border-box}body{margin:0;color:#24322e;background:#ebece7;font-family:"Noto Sans CJK SC","Noto Sans SC",sans-serif}.paper{width:210mm;height:297mm;padding:17mm 19mm 18mm;margin:8mm auto;background:white;position:relative;break-after:page;overflow:visible}header{font-size:10px;color:#68766f;border-bottom:1px solid #bdcbc0;padding-bottom:8px}h1{font-size:19px;line-height:1.5;margin:18px 0 12px}h2{font-size:18px;color:#285344;margin:14px 0}h3{font-size:1.07em;margin:12px 0 6px}article{font-size:13px;line-height:1.85;overflow-wrap:anywhere}p{margin:0 0 10px;white-space:pre-wrap}.source{font-size:.8em;color:#566b61}a{color:inherit}footer{position:absolute;bottom:11mm;font-size:9px;color:#68766f}.paper:last-child{break-after:auto}@page{size:A4;margin:0}@media print{body{background:white}.paper{margin:0}}
    </style><body>'''+''.join(sections)+'''<script>window.fitReport=function(){let ok=true;for(const p of document.querySelectorAll('.paper')){const a=p.querySelector('article'),foot=p.querySelector('footer');for(let font=13;font>=9.5;font-=.25){a.style.fontSize=font+'px';if(a.getBoundingClientRect().bottom<foot.getBoundingClientRect().top-12)break;}if(a.getBoundingClientRect().bottom>=foot.getBoundingClientRect().top-8)ok=false;}return ok;};document.fonts.ready.then(()=>window.fitReport());</script></body></html>'''

def pdf(task_id):
    from playwright.sync_api import sync_playwright
    from utils.task_runtime import task_output_dir
    path=task_output_dir(task_id,'report')/'concise-four-pages.pdf'
    with _pdf_lock:
        content=report_html(task_id)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
            try:
                page=browser.new_page();page.set_content(content,wait_until='load')
                page.evaluate('document.fonts.ready')
                if not page.evaluate('window.fitReport()'):raise ValueError('报告篇幅超出四页排版，需要压缩正文后导出')
                page.pdf(path=str(path),format='A4',print_background=True,prefer_css_page_size=True)
            finally:browser.close()
    return path
