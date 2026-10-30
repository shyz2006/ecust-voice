"""Compose a weekly digest from already validated observations, without another model pass."""
VERSION='campus-weekly-v1'

def build(data):
    from .weekly import validate_insights
    value=validate_insights(data['insights'],data)
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
