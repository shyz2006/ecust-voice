"""Compose a weekly digest from already validated observations, without another model pass."""
VERSION='campus-weekly-v1'

def build(data):
    from .weekly import validate_insights
    value=validate_insights(data['insights'],data)
    if value.get('schema_version')==2:
        issues=[{'title':s['title'],'content':s['observation']+('\n\n'+s['comparison'] if s.get('comparison') else ''),'evidence':list(s['evidence'])} for s in value['signals']]
        convert=lambda rows:[{'title':s['title'],'content':s['observation'],'evidence':list(s['evidence'])} for s in rows]
        outlook=convert(value['outlook'])
        outlook.append({'title':'下周工作建议','content':'\n\n'.join(str(i+1)+'. '+s for i,s in enumerate(value['follow_up'])),'evidence':[]})
        chapters=[{'title':'二、重点议题与变化','sections':issues},
                  {'title':'三、学生心理诉求与育人分析','sections':convert(value['psychology'])},
                  {'title':'四、下周趋势研判与工作建议','sections':outlook}]
        return {'version':'campus-weekly-v2','chapters':chapters,'word_count':len(value['overview']['observation'])+sum(len(s['content']) for c in chapters for s in c['sections'])}
    observations=[];changes=[]
    for signal in value['signals']:
        refs=list(signal['evidence'])
        observations.append({'title':signal['title'],'content':signal['observation'],'evidence':refs})
        if signal.get('comparison'):
            changes.append({'title':signal['title'],'content':signal['comparison'],'evidence':refs})
    chapters=[{'title':'本周同学在关注什么','sections':observations}]
    if changes:chapters.append({'title':'与上周相比，哪些诉求发生变化','sections':changes})
    # Objective opening, twelve-theme counts, follow-up and references are rendered by weekly.report_html.
    return {'version':VERSION,'chapters':chapters,'word_count':sum(len(s['content']) for c in chapters for s in c['sections'])}


def activity_profile(posts,coverage,cutoff):
    """Aligned 24-hour windows; partial collection is never a daily zero."""
    from collections import Counter
    day=86400;start=cutoff-14*day;windows=[]
    for i,item in enumerate(coverage):
        members=[p for p in posts if start+i*day<=p['published']<start+(i+1)*day]
        ready=bool(item['ready'])
        windows.append({'start':start+i*day,'end':start+(i+1)*day,'period':'previous' if i<7 else 'current',
                        'ready':ready,'count':len(members) if ready else None,'collected_count':len(members),
                        'categories':dict(Counter(p['theme'] for p in members)) if ready else None})
    return windows
