"""校园观察 v2：页面和统计共享的固定十二类，不改写历史标注。"""
import re

THEMES = (
    '学业课程', '考试考证', '升学就业', '校园设施与管理', '食堂与生活服务', '宿舍生活',
    '社交与同伴', '恋爱情感', '身心与情绪', '文体与实践', '交易与互助', '其他校园讨论',
)
COLORS = ('#527a99','#8278a6','#547d70','#ba8954','#bf8173','#95816f',
          '#6f91a0','#b97b97','#7b9770','#aa9158','#819398','#96958f')
ALIASES = {
    '宿舍室友':'宿舍生活', '找搭子/兴趣活动':'社交与同伴', '社交孤独':'社交与同伴',
    '身心健康':'身心与情绪', '情绪宣泄':'身心与情绪', '跑腿/二手交易':'交易与互助',
    '失物招领/求助':'交易与互助', '其他':'其他校园讨论', '灌水/水楼':'其他校园讨论',
}
PRACTICE = re.compile(r'志愿(?:服务|者|活动)|团日|党日|社会实践|支教|义工|公益活动|献血|文艺|音乐节|运动会|社团活动|球赛|艺术节')

def canonical(theme, content=''):
    if PRACTICE.search(content or ''):
        return '文体与实践'
    return theme if theme in THEMES else ALIASES.get(theme,'其他校园讨论')

POSITIVE = ('开心','快乐','喜欢','感谢','谢谢','满意','顺利','期待','幸福','治愈','优秀','好吃','好评','支持','加油','推荐','成功','热爱')
NEGATIVE = ('焦虑','难过','烦躁','生气','失望','讨厌','崩溃','痛苦','伤心','孤独','抑郁','担心','害怕','难吃','投诉','不满','糟糕','委屈','难受')
NEGATORS = ('不','没','无','未','别')

def sentiment(text):
    """词典出现次数；前三字中存在否定词时反转。仅描述文本倾向。"""
    counts={'积极':0,'消极':0}
    for words,category in ((POSITIVE,'积极'),(NEGATIVE,'消极')):
        for word in words:
            for hit in re.finditer(re.escape(word),text or ''):
                prefix=(text or '')[max(0,hit.start()-3):hit.start()]
                negate=sum(prefix.count(x) for x in NEGATORS)%2
                target=('消极' if category=='积极' else '积极') if negate else category
                counts[target]+=1
    score=counts['积极']-counts['消极']
    return {'label':'积极' if score>0 else '消极' if score<0 else '中性',
            'positive_hits':counts['积极'],'negative_hits':counts['消极'],'version':'lexicon-1'}
