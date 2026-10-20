"""Raw retrieval evidence for concise reports; generated prose is not a source catalogue."""
import json,re
from urllib.parse import urlsplit,urldefrag

def source_evidence(task_id):
    from utils.task_runtime import task_output_dir
    evidence={}
    def visit(value,engine):
        if isinstance(value,list):
            for child in value:visit(child,engine)
        elif isinstance(value,dict):
            url=value.get('url');content=value.get('content') or value.get('snippet') or ''
            if isinstance(url,str) and isinstance(content,str):
                try:valid=urlsplit(url).scheme in ('http','https') and bool(urlsplit(url).hostname)
                except ValueError:valid=False
                if valid and content.strip():
                    entry={'url':url,'title':str(value.get('title') or ''),'excerpt':content[:1800],'engine':engine}
                    if url not in evidence or len(entry['excerpt'])>len(evidence[url]['excerpt']):evidence[url]=entry
            for child in value.values():
                if isinstance(child,(dict,list)):visit(child,engine)
    for engine in ('query','media','insight'):
        for path in task_output_dir(task_id,engine).glob('state_*.json'):
            try:visit(json.loads(path.read_text(encoding='utf-8')),engine)
            except (ValueError,OSError):continue
    return list(evidence.values())

def evidence_context(task_id):
    records=source_evidence(task_id)
    if not records:raise ValueError('研究材料尚无可核对的原始来源链接')
    records.sort(key=lambda x:(not any(w in x['title'].lower() for w in ('ai','人工智能','核验','学术')),x['engine']=='insight'))
    selected=[dict(x,excerpt=x['excerpt'][:1000]) for x in records[:24]]
    return ('原始检索证据目录（URL与摘录来自检索记录，不是模型分析）：\n'+json.dumps(selected,ensure_ascii=False)+
            '\n只依据这些摘录陈述事实；没有原始摘录支持的数字、日期、学校事件不得从上游模型报告沿用。'
            '检索时间不是发表时间。每章至少一处通过inlines.marks的link/href引用目录中的原始URL，逐字复制URL。'
            '一条论坛发言只代表该帖，不能推出学生总体比例或学校普遍问题。')

def validate_sources(document,task_id):
    records={urldefrag(x['url'])[0]:x for x in source_evidence(task_id)}
    allowed=set(records)
    def links(value):
        if isinstance(value,list):
            for child in value:yield from links(child)
        elif isinstance(value,dict):
            url=value.get('href')
            if isinstance(url,str) and url.startswith(('https://','http://')):yield urldefrag(url)[0]
            for child in value.values():
                if isinstance(child,(list,dict)):yield from links(child)
    def text_content(value):
        if isinstance(value,list):return ' '.join(text_content(x) for x in value)
        if not isinstance(value,dict):return ''
        return ' '.join(v if k=='text' and isinstance(v,str) else text_content(v) for k,v in value.items())
    for chapter in document.get('chapters') or []:
        cited=set(links(chapter))
        if not cited or not cited<=allowed:raise ValueError('报告原始来源链接尚未通过核对，需要补充检索记录中的逐章引用')
        source_text=' '.join(records[url]['excerpt'] for url in cited)
        percentages=lambda text:{re.sub(r'\s','',x).replace('％','%') for x in re.findall(r'\d+(?:\.\d+)?\s*[%％]',text)}
        if not percentages(text_content(chapter))<=percentages(source_text):
            raise ValueError('报告中的百分比未在所引原始摘录中找到，需要核对统计依据')
