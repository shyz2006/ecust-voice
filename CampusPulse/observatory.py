"""校园观察：只在真实双论坛快照上计算；排序/预测/词云/梗榜均不调用模型。

每日窗口按请求时刻回溯24h，缺测窗口为None。预测为未校准的启发式外推。
"""
import bisect
import hashlib
import json
import math
import re
import threading
import time
from collections import Counter, defaultdict

SOURCES = ('huyou-school', 'tieba-school')
NAMES = {'huyou-school': '狐友华理圈', 'tieba-school': '华理贴吧'}
DAY = 86400
RED_TERMS = ('党建', '党支部', '入党', '党员', '党史', '团支部', '团课', '团员', '理论学习', '思政',
             '爱国', '国庆', '报国', '家国', '红色', '志愿服务', '志愿者', '乡村振兴', '社会实践', '校史', '青年使命')
# 种子词只供字符串匹配：没有至少3条真实独立帖子命中，就不会进入梗榜。
MEME_TERMS = ('搭子', '班味', '发疯文学', '显眼包', '电子榨菜', '抽象', '松弛感', '情绪价值',
              '破防', '内卷', '躺平', '摆烂', '上头', '下头', '红温', '牛马', '社恐', '社牛',
              '已读乱回', '硬控', 'citywalk', '尊嘟假嘟', '绝绝子', '包的', '偷感', '淡人', '浓人')
STOP = set('同学 学校 华理 华东 理工 大学 大家 一个 这个 那个 什么 怎么 可以 还有 没有 不是 知道 感觉 真的 '
           '一下 现在 今天 昨天 时候 这样 就是 但是 所以 可能 还是 自己 我们 你们 他们 有没有 为什么 '
           '已隐藏 姓名 同学 数字 手机号 邮箱 图片 视频 链接 网页 吧主 分享 来自 需要 觉得 '
           '请问 问问 有无 有点 不能 看到 是不是 的话 怎么办 明天 下午 晚上 早上 时候 时间 直接 不会 东西 之后 帮忙 平时'.split())
_cache_lock = threading.Lock()
_cache = {}


def numeric(value):
    try:
        n = float(value or 0)
        return max(0, n) if math.isfinite(n) else 0
    except (ValueError, TypeError):
        return 0


def raw_heat(source, exposure, comments):
    return (math.log1p(numeric(exposure)) if source == 'huyou-school' else 0) + 2 * math.log1p(numeric(comments))


def tokens(text):
    # jieba词性过滤人名和代词；统计之前正文还会经过现有脱敏函数。
    import jieba.posseg as pseg
    clean = re.sub(r'\[[^\]]*\]|https?://\S+', ' ', text.lower())
    return {w for w, flag in pseg.cut(clean) if 2 <= len(w) <= 12 and w not in STOP
            and flag not in ('nr', 'nrfg', 'nrt', 'r', 'm', 'x', 'uj', 'ul', 'c', 'p', 'd')
            and re.fullmatch(r'[\u4e00-\u9fffA-Za-z]+', w)}


def _key(row):
    ex = row.get('extra') or {}
    stable = ex.get('link') or ex.get('feed_id') or ex.get('content') or row.get('title') or ''
    return row['source'] + ':' + hashlib.sha1(str(stable).encode()).hexdigest()[:20]


def coverage(rows, now, days=10):
    """≥18小时观测跨度且最长间断≤6小时，才把一个24h窗视为可比较。"""
    bins = [{s: set() for s in SOURCES} for _ in range(days)]
    start = now - days * DAY
    for row in rows:
        i = int((row['batch_ts'] - start) // DAY)
        if row['source'] in SOURCES and 0 <= i < days:
            bins[i][row['source']].add(row['batch_ts'])
    out = []
    for i, by in enumerate(bins):
        sources = {}
        for s, stamps in by.items():
            ts = sorted(stamps)
            gaps = [b-a for a, b in zip(ts, ts[1:])]
            span = ts[-1] - ts[0] if ts else 0
            edges = [ts[0]-(start+i*DAY), start+(i+1)*DAY-ts[-1]] if ts else [DAY]
            sources[s] = {'samples': len(ts), 'span_hours': round(span/3600, 1),
                          'ready': span >= 18*3600 and max(gaps + edges) <= 6*3600}
        out.append({'ts': start+i*DAY, 'sources': sources, 'ready': all(s['ready'] for s in sources.values())})
    return out


def prepare(rows, annotations, now, classify, sanitize, days=10):
    grouped = defaultdict(list)
    for row in rows:
        if row['source'] in SOURCES and now-days*DAY <= row['batch_ts'] <= now:
            grouped[_key(row)].append(row)
    posts, excluded = [], Counter()
    for key, observations in grouped.items():
        observations.sort(key=lambda r: r['batch_ts'])
        row, first = observations[-1], observations[0]
        ex = row.get('extra') or {}
        text = ex.get('content') or row.get('title') or ''
        ann_key = hashlib.sha1(text.encode()).hexdigest()[:16]
        a = annotations.get(ann_key) or classify(text)
        rule = classify(text)
        if a.get('is_ad') or rule.get('is_ad'):
            excluded['ads'] += 1
            continue
        if a.get('crisis_level', '无') != '无' or rule.get('crisis_level', '无') != '无':
            excluded['crisis'] += 1
            continue
        published = int(numeric(ex.get('published')))
        # 无合法发帖时间时，按首次采集时间归窗，并保留明确标记。
        known = 946684800 <= published <= now+300
        event_ts = published if known else first['batch_ts']
        if event_ts < now-days*DAY:
            excluded['older_posts'] += 1
            continue
        text = sanitize(text)
        posts.append({'id': key, 'source': row['source'], 'content': text, 'link': ex.get('link') or row.get('url'), 'gist': sanitize(a.get('gist') or ''),
                      'theme': a.get('theme') or rule.get('theme') or '其他', 'emotion': a.get('emotion') or '中性',
                      'psych_dimensions': a.get('psych_dimensions') or [], 'published': event_ts,
                      'time_basis': 'published' if known else 'first_observed', 'first_observed': first['batch_ts'],
                      'last_observed': row['batch_ts'], 'comments': int(numeric(ex.get('comments'))),
                      'exposure': int(numeric(ex.get('exposure'))), 'observations': observations,
                      'raw_heat': raw_heat(row['source'], ex.get('exposure'), ex.get('comments')),
                      'terms': tokens(text), 'red_terms': [w for w in RED_TERMS if w in text]})
    for s in SOURCES:
        group = [p for p in posts if p['source'] == s]
        ranks = sorted(p['raw_heat'] for p in group)
        for p in group:
            # 同互动量同分，零互动为0；分位数只能在本来源内解释。
            p['heat'] = round(100*bisect.bisect_right(ranks, p['raw_heat'])/len(ranks), 1) if p['raw_heat'] else 0
    posts.sort(key=lambda p: (-p['heat'], -p['raw_heat'], -p['published']))
    return posts, dict(excluded)


def series(posts, cov, now, days=10):
    """每窗真实新增帖子+存量帖子曝光/回复的对数增量，按论坛采集独立帖量归一化。"""
    start = now-days*DAY
    counts = [{s: 0 for s in SOURCES} for _ in range(days)]
    strength = [{s: 0.0 for s in SOURCES} for _ in range(days)]
    for p in posts:
        i = int((p['published']-start)//DAY)
        if 0 <= i < days:
            counts[i][p['source']] += 1
            strength[i][p['source']] += 1
        previous = None
        for r in p['observations']:
            ex = r.get('extra') or {}
            current = raw_heat(p['source'], ex.get('exposure'), ex.get('comments'))
            i = int((r['batch_ts']-start)//DAY)
            if previous is not None and 0 <= i < days:
                strength[i][p['source']] += max(0, current-previous)
            previous = current
    return counts, strength


def trend(group, denominator, cov, now, days=10):
    from . import forecasting
    counts, strength = series(group, cov, now, days)
    points = []
    for i, c in enumerate(cov):
        val = sum(50*strength[i][s]/max(denominator[i][s], 1) for s in SOURCES) if c['ready'] else None
        source_heat = {s:round(100*strength[i][s]/max(denominator[i][s],1),3)
                       if c.get('sources',{}).get(s,{'ready':c['ready']})['ready'] else None for s in SOURCES}
        points.append({'ts': c['ts'], 'posts': sum(counts[i].values()),
                       'heat': round(val, 3) if val is not None else None, 'by_source': counts[i],
                       'source_heat':source_heat, 'observed': c['ready']})
    ready = all(p['heat'] is not None for p in points[-3:])
    v = a = predicted = None
    score = 0
    backtest=[]
    for i in range(3,len(points)):
        window=points[i-3:i+1]
        if any(p['heat'] is None for p in window):continue
        x0,x1,x2,actual=[p['heat'] for p in window]
        estimate=max(0,min(2*x2+1,x2+0.5*(x2-x1)+0.25*(x2-2*x1+x0)))
        backtest.append({'predicted':estimate,'actual':actual,'baseline':x2})
    if ready:
        x0, x1, x2 = [p['heat'] for p in points[-3:]]
        v, a = x2-x1, x2-2*x1+x0
        predicted = max(0, min(2*x2+1, x2+0.5*v+0.25*a))
        support = sum(p['posts'] for p in points[-3:])
        score = 100*(0.4*max(0,v)/(1+abs(v)) + 0.6*max(0,a)/(1+abs(a)))*support/(support+8)
    projection=forecasting.forecast(points,sum(p['posts'] for p in points[-3:]))
    source_forecasts={s:forecasting.forecast([{'ts':p['ts'],'heat':p['source_heat'][s]} for p in points],
                                           sum(p['by_source'][s] for p in points[-3:])) for s in SOURCES}
    return {'timeline': points, 'velocity': round(v, 3) if v is not None else None,
            'acceleration': round(a, 3) if a is not None else None,
            'forecast_24h':projection['path'][0]['value'] if projection['ready'] else None,
            'momentum_24h':round(predicted,2) if predicted is not None else None,
            'forecast':projection,
            'source_forecasts':source_forecasts,
            'trend_score': round(score, 1), 'trend_ready': ready,
            'backtest':{'windows':len(backtest),
                        'mae':round(sum(abs(p['predicted']-p['actual']) for p in backtest)/len(backtest),2) if backtest else None,
                        'baseline_mae':round(sum(abs(p['baseline']-p['actual']) for p in backtest)/len(backtest),2) if backtest else None},
            'phase': '资料不足' if not ready else ('升温加速' if v > 0 and a > 0 else
                     '持续升温' if v > 0 else '降温' if v < 0 else '平稳'),
            'confidence': '中等' if ready and len(group) >= 20 else '低'}


def meme_statistics(posts, cov, now, denominator):
    """候选召回不联网、不读AI词典；DF是去重帖子数，不是重复采集次数。"""
    matches = defaultdict(list)
    for p in posts:
        for word in MEME_TERMS:
            if word in p['content'].lower():
                matches[word].append(p)
    # 从语料自动召回新词，沿用PMI/邻字熵，移除模型精筛步骤。
    from . import memes
    docs = [(p['content'], p['source']) for p in posts]
    novel = memes.discover_words(docs, min_df=4, top=20)
    templates = memes.discover_templates(docs, min_fillers=5, top=10)
    kinds = {w: '种子流行语匹配' for w in matches}
    keys = {w:'w:'+w for w in matches}
    for candidate in novel + templates:
        label = candidate['label']
        if label in kinds and kinds[label] == '种子流行语匹配':
            continue
        if candidate['kind'] == 'word':
            hits = [p for p in posts if label in p['content']]
        else:
            pre, suf = candidate['key'][2:].split('…')
            pattern = re.compile(re.escape(pre)+r'[\u4e00-\u9fff]{1,4}'+re.escape(suf))
            hits = [p for p in posts if pattern.search(p['content'])]
        matches[label] = hits
        kinds[label] = '统计新词候选' if candidate['kind'] == 'word' else '复用句式候选'
        keys[label] = candidate['key']
    out = []
    for word, hits in matches.items():
        if len(hits) < 3:
            continue
        source_counts = Counter(p['source'] for p in hits)
        entropy = -sum((n/len(hits))*math.log2(n/len(hits)) for n in source_counts.values())
        active = len({int((p['published']-(now-10*DAY))//DAY) for p in hits})
        tr = trend(hits, denominator, cov, now)
        recent = sum(p['published'] >= now-3*DAY for p in hits)
        before = sum(now-6*DAY <= p['published'] < now-3*DAY for p in hits)
        growth_ready = all(c['ready'] for c in cov[-6:])
        growth = (recent+1)/(before+1) if growth_ready else None
        persistence = active/max(1, sum(c['ready'] for c in cov))
        support = len(hits)/(len(hits)+5)
        score = math.log1p(len(hits))*(1+entropy)*(1+min(2, max(0, (growth or 1)-1)))*(1+min(1,persistence))*support
        out.append({'term': word, 'key':keys[word], 'kind': kinds[word], 'df': len(hits), 'by_source': dict(source_counts),
                    'source_entropy': round(entropy, 3), 'active_days': active,
                    'growth_3d': round(growth, 2) if growth is not None else None,
                    'diffusion_score': round(score, 3), 'status': '待人工核实的梗候选',
                    'examples': [p['gist'] or p['content'][:80] for p in hits[:3]],
                    'post_ids': [p['id'] for p in hits], **tr})
    return sorted(out, key=lambda m: (-m['diffusion_score'], -m['df'], m['term']))[:40]


def build(rows, annotations, now, classify, sanitize, feedback=None):
    from . import forecasting
    cov = coverage(rows, now)
    posts, excluded = prepare(rows, annotations, now, classify, sanitize)
    # 采集帖量分母包含所有可展示的独立帖，分论坛逐窗计算。
    denominators = [{s: 0 for s in SOURCES} for _ in range(10)]
    for p in posts:
        occupied = {int((r['batch_ts']-(now-10*DAY))//DAY) for r in p['observations']}
        for i in occupied:
            if 0 <= i < 10:
                denominators[i][p['source']] += 1
    by_theme = defaultdict(list)
    cloud = defaultdict(Counter)
    for p in posts:
        by_theme[p['theme']].append(p)
        cloud['all'].update(p['terms'])
        cloud[p['source']].update(p['terms'])
    themes = [{'theme': t, 'posts': len(ps), 'heat': round(sum(p['heat'] for p in ps), 1),
               'by_source': dict(Counter(p['source'] for p in ps)), 'keywords': [w for w,_ in Counter(w for p in ps for w in p['terms']).most_common(6)],
               **trend(ps, denominators, cov, now)} for t, ps in by_theme.items()]
    themes.sort(key=lambda t: (-t['trend_score'], -t['posts']))
    for theme in themes:
        theme['category']=forecasting.category(theme['theme'])
        theme['milestones']=forecasting.milestones(by_theme[theme['theme']],theme['timeline'])
    categories={k:[p for p in posts if forecasting.category(p['theme'])==k] for k in ('academic','life','social','other')}
    outlook={'overall':{'posts':len(posts),**trend(posts,denominators,cov,now)},
             'categories':{k:{'posts':len(ps),**trend(ps,denominators,cov,now)} for k,ps in categories.items()}}
    red = [p for p in posts if p['red_terms']]
    candidates = meme_statistics(posts, cov, now, denominators)
    feedback = feedback or {}
    def review_label(m):
        return (feedback.get(m['key']) or {}).get('label')
    # 新词发现本身不能证明是梗。术语/新词先进入待核实区，人工确认后才进入梗榜。
    blocked=('not_meme','outdated','common','duplicate')
    memes = [m for m in candidates if (m['kind']=='种子流行语匹配' or review_label(m)=='confirm') and review_label(m) not in blocked]
    unverified = [m for m in candidates if m not in memes and review_label(m) not in ('not_meme','outdated','common','duplicate')]
    public_posts = [{k: v for k,v in p.items() if k not in ('observations','terms','raw_heat')} for p in posts]
    return {'success': True, 'generated_at': now, 'window_days': 10, 'window_start': now-10*DAY,
            'observed_start': min((r['batch_ts'] for r in rows),default=None),
            'coverage': cov, 'posts': public_posts, 'total': len(posts),
            'by_source': dict(Counter(p['source'] for p in posts)), 'excluded': excluded,
            'themes': themes, 'outlook':outlook, 'wordcloud': {s:[{'term':w,'df':n} for w,n in c.most_common(60)] for s,c in cloud.items()},
            'red': {'post_ids': [p['id'] for p in red], 'terms': dict(Counter(w for p in red for w in p['red_terms'])),
                    'timeline': trend(red, denominators, cov, now)['timeline']}, 'memes': memes,'meme_candidates':unverified,
            'method': {'version':'ecust-stat-1', 'heat': '来源内分位数；狐友原始量 ln(1+曝光)+2ln(1+回复)，贴吧为2ln(1+回复)',
                       'intensity': '每24h：新增帖子数+已有帖互动对数增量，按本论坛独立采集帖数归一化，双论坛等权',
                       'trend': 'v=Hₜ−Hₜ₋₁；a=Hₜ−2Hₜ₋₁+Hₜ₋₂；趋势分=100×[0.4·v⁺/(1+|v|)+0.6·a⁺/(1+|a|)]×n/(n+8)',
                       'forecast': '每主题/分类/校内整体分别滚动比较持平、衰减趋势、速度与加速度模型；至少4个有效核验窗且误差比持平低5%才采用趋势模型，提供24/48/72h外推。近期少于3帖或缺测不预测。参考带为历史单步MAE×√时段，不是概率区间。',
                       'meme': 'S=ln(1+DF)×(1+来源熵)×(1+截断正增长)×(1+持续性)×DF/(DF+5)；来源熵=−Σp·log₂p',
                       'limits': '公开列表样本，不代表全校学生；不能还原人际传播链。缺失采集不等于零，首次观察不等于发帖时间；危机/广告不展示。'}}


def snapshot(force=False):
    from . import campus, storage
    from .sources.huyou import deidentify, mask_names
    now = int(time.time())
    key = now//300
    with _cache_lock:
        if not force and _cache.get('key') == key:
            return _cache['data']
        rows = storage.recent_items(list(SOURCES), now-10*DAY)
        # storage.kv_prefix已经去掉前缀，不能再次截断内容哈希。
        annotations = {r['key']: json.loads(r['value'])
                       for r in storage.kv_prefix(campus._PREFIX, limit=100000)}
        feedback={r['key']:json.loads(r['value']) for r in storage.kv_prefix('memefb:',limit=2000)}
        data = build(rows, annotations, now, campus._rule, lambda t: mask_names(deidentify(t)),feedback)
        _cache.update(key=key, data=data)
        return data
