"""校园主题多时段外推。短序列滚动验证选择模型；参考误差不是概率区间。"""
import math

DAY = 86400


def category(theme):
    import re
    if re.search('学业|考试|升学|就业', theme):
        return 'academic'
    if re.search('宿舍|食堂|设施|生活|二手|跑腿|失物', theme):
        return 'life'
    if re.search('社交|恋爱|情感|兴趣|搭子|孤独', theme):
        return 'social'
    return 'other'


MODELS = {'persistence':'最近强度持平', 'damped':'衰减趋势', 'momentum':'速度与加速度'}


def estimate(values, model, horizon=1):
    x0, x1, x2 = values[-3:]
    velocity, acceleration = x2-x1, x2-2*x1+x0
    if model == 'persistence':
        return x2
    if model == 'damped':
        value = x2+velocity*sum(0.6**k for k in range(1,horizon+1))
    else:
        # 越远的时段越衰减，避免二阶差分无界放大。
        value = x2+(0.5*velocity+0.25*acceleration)*sum(0.65**k for k in range(horizon))
    return max(0, min(2*x2+1, value))


def forecast(points, support):
    values = [p['heat'] for p in points]
    available = sum(v is not None for v in values)
    if len(values)<3 or any(v is None for v in values[-3:]):
        return {'ready':False,'reason':'最近三个日窗覆盖不足','path':[], 'validation':[], 'valid_windows':available}
    if support < 3:
        return {'ready':False,'reason':'最近三个日窗不足3条新帖，样本过少','path':[], 'validation':[], 'valid_windows':available}
    residuals = {m:[] for m in MODELS}
    for i in range(3,len(values)):
        window = values[i-3:i+1]
        if any(v is None for v in window):
            continue
        for model in MODELS:
            residuals[model].append(abs(estimate(window[:3],model)-window[3]))
    validation = [{'model':m,'label':MODELS[m],'windows':len(e),
                   'mae':round(sum(e)/len(e),3) if e else None} for m,e in residuals.items()]
    model='persistence'
    reason='有效核验不足4窗，采用持平参考'
    if len(residuals[model]) >= 4:
        means={m:sum(e)/len(e) for m,e in residuals.items()}
        best=min(means,key=means.get)
        if means[best] < means['persistence']*0.95:
            model=best
            reason='滚动核验误差比持平参考低至少5%'
        else:
            reason='趋势模型尚未优于持平参考，保留持平外推'
    error=sum(residuals[model])/len(residuals[model]) if residuals[model] else None
    origin=values[-1]
    path=[]
    for horizon in (1,2,3):
        predicted=estimate(values[-3:],model,horizon)
        margin=error*math.sqrt(horizon) if error is not None else None
        path.append({'hours':horizon*24,'ts':points[-1]['ts']+(horizon+1)*DAY,
                     'value':round(predicted,3), 'lower':round(max(0,predicted-margin),3) if margin is not None else None,
                     'upper':round(predicted+margin,3) if margin is not None else None,
                     'change':round(predicted-origin,3)})
    return {'ready':True, 'model':model,'label':MODELS[model],'reason':reason,
            'path':path,'validation':validation,'valid_windows':available,
            'error_basis':'历史单步MAE按√时段扩大，仅作误差参考，不是置信区间'}


def milestones(posts, points):
    if not posts:
        return []
    sources={}
    for p in posts:
        sources[p['source']]=min(sources.get(p['source'],p['first_observed']),p['first_observed'])
    events=[{'ts':ts,'kind':'source','source':s,'title':'首次采集到该论坛的讨论',
             'detail':'首次观察时间，不等于原帖发布时间或传播起点'} for s,ts in sources.items()]
    if len(sources)>1:
        events.append({'ts':max(sources.values()),'kind':'cross_source','title':'两个论坛均有该主题讨论',
                       'detail':'表示跨来源出现，不能据此断言存在转发链'})
    valid=[p for p in points if p['heat'] is not None and p['heat']>0]
    if valid:
        peak=max(valid,key=lambda p:p['heat'])
        events.append({'ts':peak['ts'],'kind':'peak','title':'窗口内关注强度峰值',
                       'detail':f"强度{peak['heat']}；该日窗新增{peak['posts']}帖"})
    for i,p in enumerate(points):
        if i<2 or any(q['heat'] is None for q in points[i-2:i+1]):
            continue
        x0,x1,x2=[q['heat'] for q in points[i-2:i+1]]
        if x2>x1 and x2-2*x1+x0>0:
            events.append({'ts':p['ts'],'kind':'acceleration','title':'首次观察到升温加速',
                           'detail':f'速度{x2-x1:+.2f}；加速度{x2-2*x1+x0:+.2f}，均由日窗计算'})
            break
    order={'source':0,'cross_source':1,'acceleration':2,'peak':3}
    return sorted(events,key=lambda e:(e['ts'],order[e['kind']]))
