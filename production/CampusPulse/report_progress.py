"""Public progress uses event metadata only; never expose model drafts or provider errors."""
def describe(events):
    chapters={};total=0;stage='正在整理报告结构';activity=None
    for event in events:
        kind=event.get('type');p=event.get('payload') or {}
        if kind in ('chapter_status','chapter_chunk','stage','progress'):activity=event.get('timestamp')
        if kind=='stage':
            if p.get('section_count'):total=int(p['section_count'])
            if p.get('stage') in ('chapters_compiled','html_rendered','report_saved'):stage='章节已齐备，正在核验并保存报告'
        if kind=='chapter_status':
            key=p.get('chapterId');chapters[key]={**chapters.get(key,{}),**p}
        if kind=='chapter_chunk' and p.get('chapterId') not in chapters:
            chapters[p.get('chapterId')]={'status':'running','title':p.get('title')}
    done=sum(c.get('status')=='completed' for c in chapters.values())
    active=[c for c in chapters.values() if c.get('status') in ('running','retrying')]
    if active:
        c=active[-1];title=str(c.get('title') or '当前章节')[:100]
        if c.get('status')=='retrying':
            error=str(c.get('error') or '')
            reason='核对来源' if '来源' in error or 'URL' in error else '调整篇幅' if any(w in error for w in ('字','篇幅','预算')) else '修正章节格式'
            stage=title+' · '+reason+'，第'+str(int(c.get('attempt') or 1)+1)+'次尝试'
        else:stage='正在撰写：'+title
    return {'message':stage,'completed_chapters':done,'total_chapters':total or len(chapters),'last_activity_at':activity}
