"""Readable campus metrics. Keep source counters separate from new-post forecasts.

Exposure is Huyou's exposureCount (impressions), not unique people or Tieba views.
Counters are the latest sampled lifetime counters of each deduplicated post.
Grouping them by publication window does not turn them into daily increments.
"""
import math
from . import forecasting

SOURCES = ('huyou-school', 'tieba-school')
DAY = 86400


def counter(post, field):
    observations = post.get('observations') or []
    extra = (observations[-1].get('extra') or {}) if observations else post
    value = extra.get(field)
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return int(value) if math.isfinite(value) and value >= 0 else None


def counters(posts):
    exposure_posts = [p for p in posts if p['source'] == 'huyou-school']
    exposures = [counter(p, 'exposure') for p in exposure_posts]
    replies = [counter(p, 'comments') for p in posts]
    known_exposures = [v for v in exposures if v is not None]
    known_replies = [v for v in replies if v is not None]
    return {
        'exposure': sum(known_exposures) if known_exposures or not exposure_posts else None,
        'exposure_known_posts': len(known_exposures), 'exposure_sample_posts': len(exposure_posts),
        'replies': sum(known_replies) if known_replies or not posts else None,
        'replies_known_posts': len(known_replies), 'replies_sample_posts': len(posts),
    }


def summarize(posts, coverage, now):
    start = now - len(coverage) * DAY
    groups = [[] for _ in coverage]
    for p in posts:
        index = int((p['published'] - start) // DAY)
        if 0 <= index < len(groups):
            groups[index].append(p)
    points = []
    for group, window in zip(groups, coverage):
        source_counts = {s: sum(p['source'] == s for p in group) for s in SOURCES}
        observed_counts = {
            s: source_counts[s] if window['sources'][s]['ready'] else None for s in SOURCES
        }
        values = counters(group)
        values['exposure_observed'] = values['exposure'] if window['sources']['huyou-school']['ready'] else None
        values['replies_observed'] = values['replies'] if window['ready'] else None
        points.append({
            'ts': window['ts'], 'posts': len(group),
            'new_posts': len(group) if window['ready'] else None,
            'by_source': source_counts, 'source_new_posts': observed_counts,
            'observed': window['ready'], **values,
        })
    # Reuse the validated mathematical model with a COUNT series, never the heat series.
    support = sum(p['posts'] for p in points[-3:])
    projection = forecasting.forecast([{'ts': p['ts'], 'heat': p['new_posts']} for p in points], support)
    projection['metric'] = 'new_posts'
    projection['unit'] = '篇 / 24小时'
    projection['label'] = {'persistence': '近期发帖量持平', 'damped': '发帖增长衰减', 'momentum': '发帖增速变化'}.get(projection.get('model'), '暂不预计')
    forecasts = {}
    for s in SOURCES:
        result = forecasting.forecast([{'ts': p['ts'], 'heat': p['source_new_posts'][s]} for p in points], sum(p['by_source'][s] for p in points[-3:]))
        result.update(metric='new_posts', unit='篇 / 24小时')
        result['label'] = {'persistence': '近期发帖量持平', 'damped': '发帖增长衰减', 'momentum': '发帖增速变化'}.get(result.get('model'), '暂不预计')
        forecasts[s] = result
    recent = [p['new_posts'] for p in points[-3:]]
    delta = recent[-1] - recent[-2] if len(recent) >= 2 and all(v is not None for v in recent[-2:]) else None
    acceleration = recent[-1] - 2 * recent[-2] + recent[-3] if len(recent) == 3 and all(v is not None for v in recent) else None
    phase = '覆盖不足' if delta is None else '增长加快' if delta > 0 and acceleration is not None and acceleration > 0 else '发帖增加' if delta > 0 else '发帖减少' if delta < 0 else '发帖持平'
    return {
        'version': 'campus-counts-1', 'summary': {'posts': len(posts), **counters(posts)},
        'timeline': points, 'delta_posts': delta, 'acceleration_posts': acceleration,
        'phase': phase, 'forecast': projection, 'source_forecasts': forecasts,
        'counter_basis': '按新帖发布时间归窗；取每帖最新采集的累计计数并去重求和，不是当天新增浏览/回复。狐友曝光量不是独立浏览人数，贴吧未采集曝光量。',
    }
