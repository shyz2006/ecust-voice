"""Keep a research task attached to the user's subject, starting before LLM planning."""
import json,re
from collections import Counter
from urllib.parse import urlsplit

STOP={'事件','研究','分析','报告','问题','影响','现象','讨论','发展','最新','动态','信息','中国','社会','如何','什么','相关','报道','记者','大学生','高校','校园'}

# Unambiguous, conventional institutional aliases; no incident-specific interpretation table.
ENTITY_ALIASES={
 '清华大学':('清华',),'北京航空航天大学':('北航',),'北京理工大学':('北理工',),
 '华东理工大学':('华理',),'武汉大学':('武大',),'北京大学':('北大',),
 '中国科学技术大学':('中科大',),'上海交通大学':('上海交大','上交大'),
 '复旦大学':('复旦',),'浙江大学':('浙大',),
}

def entity_text(text):
    text=re.sub(r'\s+','',str(text or '')).lower()
    for name,aliases in ENTITY_ALIASES.items():
        text=text.replace(name,aliases[0])
        for alias in aliases[1:]:text=text.replace(alias,aliases[0])
    return text

def anchor_present(anchor,text):return entity_text(anchor) in entity_text(text)


def quote_context(query):
    """Extract explicit identity context around a quotation, without inferring an event."""
    outside=re.sub(r'[“「"]([^”」"]{2,120})[”」"]',' ',query)
    schools=list(dict.fromkeys(re.findall(r'[\u4e00-\u9fff]{2,16}大学',outside)))
    people=[]
    for school in schools:
        tail=outside.split(school,1)[1].strip()
        match=re.match(r'(?:的)?(?:(?:教授|老师)\s*)?([\u4e00-\u9fff]{2,4}?)(?=\s*(?:老师|教授|在|说|称|谈|表示|提出|[，,：:]|$))',tail)
        if match and match[1] not in ('学生','同学','老师','教授','研究生','计算机','计算机系'):
            people.append(match[1])
    return schools,people


def subject(query):
    text=re.sub(r'^(?:请|帮我|关于|研究|分析|一下|的)+','',query.strip())
    core=re.sub(r'(?:事件|风波|争议|现象|分析|研究|报告|的影响|的发展)+$','',text).strip(' ：:，,的')
    quoted=re.findall(r'[“「"]([^”」"]{2,120})[”」"]',query)
    strict=bool(quoted or (len(core)<=16 and text!=core) or re.search(r'阿姨$|叔叔$|公司$|大学$',core))
    if quoted:core=quoted[0]
    import jieba
    terms=list(dict.fromkeys(w.lower() for w in jieba.lcut(core) if len(w.strip())>=2 and w not in STOP))
    result={'query':query,'core':core,'strict':strict,'terms':terms or [core.lower()]}
    if quoted:
        schools,people=quote_context(query)
        identities=people or schools
        if identities:
            generic={'没有','应该','立刻','立即','应当','必须','可以','不能','是否','一个','这样','在课上'}
            terms=[word for word in terms if word not in generic]
            result.update(strict=False,quote_identity=identities,quote_schools=schools,terms=terms or [core.lower()])
    return result

def task_subject(task_id):
    from utils.task_runtime import read_task_metadata
    meta=read_task_metadata(task_id);topic=subject(str(meta.get('query') or ''))
    brief=meta.get('research_brief') or {}
    if brief.get('confirmed') and brief.get('exploratory'):
        topic=subject(str(brief.get('query') or meta.get('query') or ''))
    if brief.get('confirmed') and brief.get('anchors'):
        topic.update(strict=False,anchors=brief['anchors'],terms=brief.get('focus_terms') or topic['terms'])
    return topic


def relevant(text,topic):
    text=re.sub(r'\s+','',text or '').lower()
    if topic.get('anchors'):
        return all(anchor_present(a,text) for a in topic['anchors']) and any(entity_text(t) in entity_text(text) for t in topic['terms'])
    if topic.get('quote_identity'):
        matches=sum(entity_text(term) in entity_text(text) for term in topic['terms'])
        return any(anchor_present(anchor,text) for anchor in topic['quote_identity']) and matches>=min(2,len(topic['terms']))
    if topic['strict']:return re.sub(r'\s+','',topic['core']).lower() in text
    terms=topic['terms'];matches=sum(t in text for t in terms)
    return matches>=min(2,len(terms))

def search_query(query,topic):
    if topic.get('anchors'):
        parts=list(topic['anchors'])
        if not any(t.lower() in query.lower() for t in topic['terms']):parts+=topic['terms'][:3]
        return ' '.join(parts+[query])
    if topic.get('quote_identity'):
        parts=list(dict.fromkeys(topic.get('quote_schools',[])+topic['quote_identity']+topic['terms']))
        if query!=topic['query']:
            parts.append(re.sub(r'[“”「」"]',' ',query))
        return ' '.join(parts)
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
    topic=task_subject(task_id);execute=agent.execute_search_tool
    def guarded(tool_name,query,**kwargs):
        anchored=search_query(str(query),topic)
        brief=read_task_metadata(task_id).get('research_brief') or {}
        if brief.get('supplement'):
            anchored+=' 用户补充：'+brief['supplement']
        # Historical events must not be restricted to a model-invented current date.
        if engine=='query':tool_name='basic_search_news'
        elif engine=='media':tool_name='web_search_only'
        return filter_response(execute(tool_name,anchored,**kwargs),topic)
    agent.execute_search_tool=guarded
    seeds=[]
    if engine in ('query','media'):
        gap_path=task_output_dir(task_id,engine)/'research_information_gap.json'
        gap_path.unlink(missing_ok=True)
        brief=read_task_metadata(task_id).get('research_brief') or {}
        seeds=[dict(x,content=x.get('snippet','')) for x in brief.get('sources',[]) if relevant(x.get('title','')+' '+x.get('snippet',''),topic)]
        if not seeds:
            response=guarded('basic_search_news' if engine=='query' else 'web_search_only',query)
            seeds=[_record(item) for item in (getattr(response,'results',None) or getattr(response,'webpages',None) or [])]
        seeds=[x for x in seeds if x['url'] and x['content'] and urlsplit(x['url']).scheme in ('http','https')][:8]
        if not seeds:
            message='本轮检索未获得可引用的相关资料，暂不能核实这句话的出处与上下文。研究问题与补充说明已保留，可补充原文链接后重试。'
            gap_path.write_text(json.dumps({'message':message},ensure_ascii=False),encoding='utf-8')
            raise ValueError(message)
        (task_output_dir(task_id,engine)/'state_topic_seed.json').write_text(json.dumps({'subject':topic,'sources':seeds},ensure_ascii=False),encoding='utf-8')
    context=json.dumps(seeds,ensure_ascii=False)
    brief=read_task_metadata(task_id).get('research_brief') or {}
    context+='\n用户原始表达：'+str(brief.get('original_query',query))+'；用户补充：'+str(brief.get('supplement',''))+'；用户确认的研究范围：'+query+'。简称、比喻与争议性措辞按研究问题理解，事件指控和群体印象须逐项核查，不作既定事实。'
    agent.state.query=query
    agent.state.report_title=query+' · 研究资料'
    for title,goal in [('主体与事实','核对主体身份、地点、已发生事实和时间线；同名人物须区分。'),
                       ('传播与观点','核对媒体报道和公众讨论，区分直接证据、评论与未确认说法。'),
                       ('争议与后续','查找争议回应、后续进展与信息缺口；没有资料的部分如实留空。')]:
        agent.state.add_paragraph(title=topic['core']+' · '+title,content='用户原始主题：'+query+'。'+goal+
            '\n先读这些与主体直接相关的检索摘录，再规划检索词。检索时间与事件时间分开记录；始终研究用户指定的主体。\n'+context)
    return True
