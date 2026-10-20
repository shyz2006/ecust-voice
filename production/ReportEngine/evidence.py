"""Raw retrieval evidence for concise reports; generated prose is not a source catalogue."""
import json,re
from urllib.parse import urlsplit,urldefrag

def source_evidence(task_id):
    from utils.task_runtime import task_output_dir,read_task_metadata
    from utils.topic_guard import subject,relevant
    topic=subject(str(read_task_metadata(task_id).get('query') or ''))
    evidence={}
    def visit(value,engine):
        if isinstance(value,list):
            for child in value:visit(child,engine)
        elif isinstance(value,dict):
            url=value.get('url');content=value.get('content') or value.get('snippet') or ''
            if isinstance(url,str) and isinstance(content,str):
                try:valid=urlsplit(url).scheme in ('http','https') and bool(urlsplit(url).hostname)
                except ValueError:valid=False
                if valid and content.strip() and relevant(str(value.get('title') or '')+' '+content,topic):
                    host=urlsplit(url).hostname or ''
                    official=host.endswith(('.gov.cn','.edu.cn'))
                    news=any(host==d or host.endswith('.'+d) for d in ('people.com.cn','news.cn','xinhuanet.com','cctv.com','cctv.cn','thepaper.cn','cnr.cn','gmw.cn','news.qq.com','chinanews.com.cn'))
                    community=any(host==d or host.endswith('.'+d) for d in ('weibo.com','weibo.cn','tieba.baidu.com','douyin.com','bilibili.com','163.com','zhihu.com'))
                    kind='官方发布' if official else '媒体报道或转载' if news else '社区发言或评论' if community else '其他网页'
                    entry={'url':url,'title':str(value.get('title') or '')[:160],'excerpt':content[:1800],'engine':engine,
                           'source_type':kind,'published_at':str(value.get('published_date') or value.get('published') or '')}
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
    from utils.task_runtime import read_task_metadata
    from utils.topic_guard import subject
    topic=subject(str(read_task_metadata(task_id).get('query') or ''))
    order={'官方发布':0,'媒体报道或转载':1,'其他网页':2,'社区发言或评论':3}
    records.sort(key=lambda x:(order[x['source_type']],topic['core'] not in x['title'],-sum(t in x['title'].lower() for t in topic['terms'])))
    selected=[dict(x,excerpt=x['excerpt'][:1000]) for x in records[:24]]
    return ('原始检索证据目录（URL与摘录来自检索记录，不是模型分析）：\n'+json.dumps(selected,ensure_ascii=False)+
            '\n只依据这些摘录陈述事实；没有原始摘录支持的数字、日期、学校事件不得从上游模型报告沿用。'
            '检索时间不是发表时间。每章至少一处通过inlines.marks的link/href引用目录中的原始URL，逐字复制URL。'
            '不同年份报道按阶段区分，发布时间缺失时不要推算日期。社区发言和评论仅作为观点，不作为官方事实；其他网页仅作线索。'
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
