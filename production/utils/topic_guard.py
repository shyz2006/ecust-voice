"""Keep a research task attached to the user's subject, starting before LLM planning."""
import json,re
from collections import Counter
from urllib.parse import urlsplit

STOP={'事件','研究','分析','报告','问题','影响','现象','讨论','发展','最新','动态','信息','中国','社会','如何','什么','相关','报道','记者','大学生','高校','校园'}

def subject(query):
    text=re.sub(r'^(?:请|帮我|关于|研究|分析|一下|的)+','',query.strip())
    core=re.sub(r'(?:事件|风波|争议|现象|分析|研究|报告|的影响|的发展)+$','',text).strip(' ：:，,的')
    quoted=re.findall(r'[“「"]([^”」"]{2,25})[”」"]',query)
    strict=bool(quoted or (len(core)<=16 and text!=core) or re.search(r'阿姨$|叔叔$|公司$|大学$',core))
    if quoted:core=quoted[0]
    import jieba
    terms=list(dict.fromkeys(w.lower() for w in jieba.lcut(core) if len(w.strip())>=2 and w not in STOP))
    return {'query':query,'core':core,'strict':strict,'terms':terms or [core.lower()]}

def relevant(text,topic):
    text=re.sub(r'\s+','',text or '').lower()
    if topic['strict']:return re.sub(r'\s+','',topic['core']).lower() in text
    terms=topic['terms'];matches=sum(t in text for t in terms)
    return matches>=min(2,len(terms))

def search_query(query,topic):
    core=topic['core']
    return query if core.lower() in query.lower() else core+' '+query

def _record(item):
    get=item.get if isinstance(item,dict) else lambda k,default='':getattr(item,k,default)
    return {'title':get('title') or get('name') or '', 'url':get('url') or '',
            'content':get('content') or get('snippet') or get('title_or_content') or ''}

def filter_response(response,topic):
    for attr in ('results','webpages'):
        values=getattr(response,attr,None)
        if isinstance(values,list):
            kept=[item for item in values if relevant(' '.join(_record(item).values()),topic)]
            setattr(response,attr,kept)
            if hasattr(response,'results_count'):response.results_count=len(kept)
    # Provider-generated answers may summarize material removed by the relevance gate.
    if hasattr(response,'answer'):response.answer=None
    return response

def prepare_agent(agent,engine,query,task_id):
    """New workshop only: literal subject search -> grounded outline -> original research nodes."""
    from utils.task_runtime import read_task_metadata,task_output_dir
    if read_task_metadata(task_id).get('pulse_revision')!=2:return False
    topic=subject(query);execute=agent.execute_search_tool
    def guarded(tool_name,query,**kwargs):
        anchored=search_query(str(query),topic)
        # Historical events must not be restricted to a model-invented current date.
        if engine=='query':tool_name='basic_search_news'
        elif engine=='media':tool_name='web_search_only'
        return filter_response(execute(tool_name,anchored,**kwargs),topic)
    agent.execute_search_tool=guarded
    seeds=[]
    if engine in ('query','media'):
        response=guarded('basic_search_news' if engine=='query' else 'web_search_only',topic['core'])
        seeds=[_record(item) for item in (getattr(response,'results',None) or getattr(response,'webpages',None) or [])]
        seeds=[x for x in seeds if x['url'] and x['content'] and urlsplit(x['url']).scheme in ('http','https')][:8]
        if not seeds:raise ValueError('尚未找到与“'+topic['core']+'”直接相关的原始资料，已停止生成，避免研究对象跑偏。')
        (task_output_dir(task_id,engine)/'state_topic_seed.json').write_text(json.dumps({'subject':topic,'sources':seeds},ensure_ascii=False),encoding='utf-8')
    context=json.dumps(seeds,ensure_ascii=False)
    agent.state.query=query
    agent.state.report_title=query+' · 研究资料'
    for title,goal in [('主体与事实','核对主体身份、地点、已发生事实和时间线；同名人物须区分。'),
                       ('传播与观点','核对媒体报道和公众讨论，区分直接证据、评论与未确认说法。'),
                       ('争议与后续','查找争议回应、后续进展与信息缺口；没有资料的部分如实留空。')]:
        agent.state.add_paragraph(title=topic['core']+' · '+title,content='用户原始主题：'+query+'。'+goal+
            '\n先读这些与主体直接相关的检索摘录，再规划检索词。检索时间与事件时间分开记录；始终研究用户指定的主体。\n'+context)
    return True
