"""Teacher revision read model: one taxonomy, reproducible counts, source-linked feeds."""
import hashlib,json,logging,math,re,threading,time
from collections import Counter,defaultdict
from functools import lru_cache
from urllib.parse import urlsplit
from . import cache,campus,observatory,storage,taxonomy

DAY=86400
HOT_PLATFORMS={'douyin':'抖音','thepaper':'澎湃','bilibili-hot-search':'B站','bilibili-popular':'B站','toutiao':'头条'}
MEME_PLATFORMS={'douyin':'抖音','bilibili-hot-search':'B站','bilibili-popular':'B站','weibo':'微博','baidu':'百度'}
_cache={};_lock=threading.Lock()
_feed_cache={};_feed_locks={kind:threading.Lock() for kind in ('hot','memes')}

def _refresh_snapshot():
    try:
        snapshot(force=True)
    except Exception:
        logging.getLogger(__name__).exception('Campus trend refresh failed')
    finally:
        with _lock:
            _cache['refreshing']=False

@lru_cache(maxsize=10000)
def cached_tokens(text):return frozenset(observatory.tokens(text))

def source_link(url):
    try:
        parsed=urlsplit(url or '')
        return url if parsed.scheme in ('https','http') and parsed.hostname else None
    except ValueError:return None

def positive_practice(text):
    activity=bool(re.search(r'志愿(?:服务|者|活动)|团日|党日|社会实践|支教|义工|公益活动|献血',text or ''))
    context=bool(re.search(r'参加|开展|举办|招募|报名|完成|组织|服务|志愿|实践|支教|献血|公益',text or ''))
    excluded=bool(re.search(r'刷分|代签|水贴|灌水|出证明|卖证明|代做|收购|广告|水时长|刷时长|水学分|凑时长|凑学时|强制|被迫|形式主义|敷衍',text or ''))
    return activity and context and not excluded and taxonomy.sentiment(text)['label']!='消极'

def count_reference(points):
    """Only complete observed 24h windows enter the mean and rolling MAE."""
    valid=[p['new_posts'] for p in points if p.get('observed') and p.get('new_posts') is not None]
    errors=[]
    for i in range(3,len(points)):
        prior=[p['new_posts'] for p in points[:i] if p.get('observed') and p.get('new_posts') is not None]
        actual=points[i].get('new_posts') if points[i].get('observed') else None
        if len(prior)>=3 and actual is not None:errors.append(abs(actual-sum(prior)/len(prior)))
    last_valid=next((i for i in range(len(points)-1,-1,-1) if points[i].get('observed') and points[i].get('new_posts') is not None),None)
    lag=len(points)-1-last_valid if last_valid is not None else None
    value=int(math.floor(sum(valid)/len(valid)+0.5)) if len(valid)>=3 else None
    mae=sum(errors)/len(errors) if errors else None
    width=mae*math.sqrt(lag+1) if mae is not None and lag is not None else None
    return {'hours':24,'value':value,
            'windows':len(valid),'mae':round(sum(errors)/len(errors),1) if errors else None,
            'as_of':points[last_valid]['ts']+DAY if last_valid is not None else None,
            'lag_windows':lag,'target_end':points[-1]['ts']+2*DAY if points else None,
            'lower':max(0,math.floor(value-width)) if value is not None and width is not None else None,
            'upper':math.ceil(value+width) if value is not None and width is not None else None,
            'validation_windows':len(errors),'method':'最近十日完整24小时窗口新增帖数的算术平均，四舍五入为整数篇；历史误差使用未取整均值计算'}


def window_comparison(points):
    """Keep the latest comparable pair visible without treating collection gaps as zero."""
    for i in range(len(points)-1,0,-1):
        current,previous=points[i],points[i-1]
        if not (current.get('observed') and previous.get('observed')):continue
        if current.get('new_posts') is None or previous.get('new_posts') is None:continue
        if current['ts']-previous['ts']!=DAY:continue
        return {'value':current['new_posts']-previous['new_posts'],
                'basis':'current' if i==len(points)-1 else 'latest_complete',
                'current':current['new_posts'],'previous':previous['new_posts'],
                'start':current['ts'],'end':current['ts']+DAY,'previous_start':previous['ts']}
    return {'value':None,'basis':'unavailable'}

def snapshot(force=False):
    now=int(time.time())
    with _lock:
        if not force and _cache.get('expires',0)>now:return _cache['data']
        if not force:
            cached=_cache.get('data') or cache.get_json('campuspulse:revision:v2-no-xhs')
            if isinstance(cached,dict) and cached.get('generated_at',0)+600>now:
                _cache.update(expires=cached['generated_at']+60,data=cached)
                if _cache['expires']<=now and not _cache.get('refreshing'):
                    _cache['refreshing']=True
                    threading.Thread(target=_refresh_snapshot,name='campus-trend-refresh',daemon=True).start()
                return cached
        rows=storage.recent_items(list(observatory.SOURCES),now-10*DAY)
        annotations={r['key']:json.loads(r['value']) for r in storage.kv_prefix(campus._PREFIX,limit=100000)}
        for key,raw in list(annotations.items()):
            annotations[key]=dict(raw)
        # Apply current care filtering consistently before building the visible sample.
        @lru_cache(maxsize=10000)
        def classify(text):return campus._rule(text)
        seen=set()
        for row in rows:
            text=(row.get('extra') or {}).get('content') or row.get('title') or ''
            key=campus._hash(text)
            if key in seen:continue
            seen.add(key)
            rule=classify(text);a=dict(annotations.get(key) or rule)
            a['crisis_level']=campus._filter_false_crisis(text,rule['theme'],a.get('crisis_level','无'))
            annotations[key]=a
        from .sources.huyou import mask_names,deidentify
        posts,excluded=observatory.prepare(rows,annotations,now,classify,lambda x:mask_names(deidentify(x)),tokenize=cached_tokens)
        cov=observatory.coverage(rows,now)
        start=now-10*DAY
        for p in posts:
            topic=taxonomy.classify(p['content'])
            p['theme']=topic['theme']
            p['classification']={k:v for k,v in topic.items() if k!='theme'}
            p['emotion']=taxonomy.sentiment(p['content'])['label']
            p['red']=positive_practice(p['content'])
        themes=[]
        for name,color in zip(taxonomy.THEMES,taxonomy.COLORS):
            group=[p for p in posts if p['theme']==name]
            points=[]
            for c in cov:
                members=[p for p in group if c['ts']<=p['published']<c['ts']+DAY]
                points.append({'ts':c['ts'],'posts':len(members),'observed':c['ready'],
                               'new_posts':len(members) if c['ready'] else None})
            last,prev=points[-1],points[-2]
            delta=last['new_posts']-prev['new_posts'] if last['observed'] and prev['observed'] else None
            themes.append({'theme':name,'color':color,'posts':len(group),
                'posts_7d':sum(p['published']>=now-7*DAY for p in group),'posts_24h':last['posts'],
                'delta':delta,'comparison':window_comparison(points),'timeline':points,'reference':count_reference(points),
                'emotion':dict(Counter(p['emotion'] for p in group)),
                'by_source':dict(Counter(p['source'] for p in group)),
                'examples':[{'content':p['content'],'link':p.get('link')} for p in sorted((p for p in group if p.get('link')),key=lambda x:-x['published'])[:3]]})
        words=Counter(w for p in posts for w in set(p['terms']))
        seven=[p for p in posts if p['published']>=now-7*DAY]
        public=[{k:v for k,v in p.items() if k not in ('observations','terms','raw_heat')} for p in posts]
        observed_at=max((r['batch_ts'] for r in rows),default=None)
        from .config import settings
        late_after=3*max(10,settings.collect_interval_min)*60
        data={'generated_at':now,'observed_at':observed_at,
              'collection_health':'empty' if observed_at is None else 'delayed' if now-observed_at>late_after else 'fresh',
              'window_start':start,'window_days':10,'taxonomy':list(taxonomy.THEMES),
              'themes':themes,'posts':public,'total':len(posts),'total_7d':len(seven),
              'emotion':dict(Counter(p['emotion'] for p in seven)),
              'practice_count':sum(p['red'] for p in seven),'coverage':cov,'excluded':excluded,
              'wordcloud':[{'term':w,'df':n} for w,n in words.most_common(50)],
              'methods':{'emotion':'规则词典 lexicon-1：积极词次数减消极词次数，前三字内否定词反转；按结果统计帖子比例。',
                         'classification':'校园常用词、同义简称与行为语境加权匹配十二类议题；识别课程咨询、公共空间、社群互动、消费与交易等意图，多主题取最高分。信息不足时归入其他。campus-topics-4。',
                         'heat':'同来源互动量分位数。狐友使用ln(1+曝光)+2ln(1+回复)，贴吧使用2ln(1+回复)。',
                         'increment':'相邻两个覆盖完整的24小时窗口新增帖数之差。最近日窗缺测时，展示最近一组连续完整日窗的对比及日期；近期已采集数量单独保留。'}}
        _cache.update(expires=time.time()+60,data=data)
        cache.set_json('campuspulse:revision:v2-no-xhs',data,ttl=600)
        return data

def network_feed(kind,force=False):
    if kind=='memes':return _network_feed(kind)
    with _feed_locks[kind]:
        cached=_feed_cache.get(kind)
        if not force and cached and cached['expires']>time.time():return cached['data']
        if not force:
            data=cache.get_json('campuspulse:feed:'+kind+':v2-no-xhs')
            expires=data.get('generated_at',0)+60 if isinstance(data,dict) else 0
            if expires>time.time():
                _feed_cache[kind]={'expires':expires,'data':data}
                return data
        data=_network_feed(kind)
        _feed_cache[kind]={'expires':time.time()+60,'data':data}
        cache.set_json('campuspulse:feed:'+kind+':v2-no-xhs',data)
        return data


def _network_feed(kind):
    now=int(time.time());platforms=HOT_PLATFORMS if kind=='hot' else MEME_PLATFORMS
    if kind=='memes':
        from .dynamic_memes import snapshot
        return snapshot()
    stamps=storage.latest_source_batches(list(platforms),now-7*DAY)
    since=max(now-7*DAY,min(stamps.values())-DAY) if stamps else now-7*DAY
    rows=storage.recent_items(list(platforms),since)
    latest={}
    rows=[row for row in rows if row['source'] in platforms]
    for row in rows:latest[row['source']]=max(latest.get(row['source'],0),row['batch_ts'])
    grouped={};history=defaultdict(dict);source_stamps=defaultdict(set)
    for row in rows:
        key=(row['source'],row['title'].strip())
        weight=1/math.log2(max(1,int(observatory.numeric(row.get('rank')) or 1))+1)
        source_stamps[row['source']].add(row['batch_ts'])
        history[key][row['batch_ts']]=weight
        keep=row['batch_ts']==latest[row['source']]
        if keep and (key not in grouped or row['batch_ts']>=grouped[key]['batch_ts']):grouped[key]=row
    focus={}
    # Existing annotations call the short public-interest explanation one_liner.
    # It is descriptive only and never enters the numerical ranking.
    for cached in storage.kv_prefix('annot2:',limit=100000):
        try:
            annotation=json.loads(cached['value'])
            if annotation.get('one_liner'):focus[cached['key'].removeprefix('annot2:')]=annotation['one_liner']
        except (ValueError,TypeError):continue
    for topic in storage.latest_topics('public').get('topics',[]):
        explanation=topic.get('summary') or (topic.get('lens') or {}).get('focus') or (topic.get('lens') or {}).get('one_liner') or ''
        for entry in topic.get('entries') or []:
            if isinstance(entry,dict) and explanation:focus[entry.get('title')]=explanation
    items=[]
    for key,row in grouped.items():
        h=history[key];stamp=row['batch_ts'];past=[h.get(ts,0) for ts in sorted(source_stamps[row['source']]) if stamp-DAY<=ts<stamp]
        baseline=sum(past)/len(past) if past else 0
        variance=sum((v-baseline)**2 for v in past)/len(past) if past else 0
        recent_topic=False
        score=(h[stamp]-baseline)/math.sqrt(variance+0.05) if len(past)>=3 and not recent_topic else None
        items.append({'id':hashlib.sha1(('|'.join(key)).encode()).hexdigest()[:16],
                      'title':row['title'],'source':row['source'],'platform':platforms[row['source']],
                      'rank':row['rank'],'url':source_link((row.get('extra') or {}).get('link') or row.get('url')),
                      'ts':stamp,'signal':round(score,3) if score is not None else None,
                      'baseline_samples':len(past),'focus':focus.get(row['title'],''),'link_kind':(row.get('extra') or {}).get('link_kind'),
                      'recent_topic':recent_topic})
    if kind=='hot':
        candidate_counts=dict(Counter(item['platform'] for item in items))
        items.sort(key=lambda x:(x['recent_topic'],x['signal'] is None,-(x['signal'] or 0),x['rank']))
        kept=[];seen_titles=defaultdict(set)
        for item in items:
            platform=item['platform'];title=re.sub(r'\s+','',item['title'])
            if title in seen_titles[platform] or len(seen_titles[platform])>=10:continue
            seen_titles[platform].add(title);kept.append(item)
        items=kept
        from .hot_focus import brief
        for item in items:
            item['focus'],item['focus_method']=brief(item['title'],item['focus'])
        return {'items':items,'platforms':list(dict.fromkeys(HOT_PLATFORMS.values())),'generated_at':now,
                'candidate_counts':candidate_counts,
                'method':'S=(当前排名权重−此前24小时排名权重均值)/√(历史方差+0.05)，权重=1/log₂(排名+1)；至少3次历史观测。'}
