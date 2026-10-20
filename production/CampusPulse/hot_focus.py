"""Short focus text from existing annotations or title-based editorial rules; no LLM I/O."""
import re

LENSES = [
 (r'谣言|辟谣|掺水|网传', '核对传言出处、当事方回应与核查结果'),
 (r'事故|遇难|受伤|火灾|地震|暴雨|台风|救援', '关注现场进展、救援情况与公共安全提示'),
 (r'双开|纪委|贪腐|处分|判刑|起诉|法院|犯罪|警方', '关注调查通报、处理程序与后续进展'),
 (r'海域|军舰|美舰|外交|南沙|战争|冲突|抗议|遣返', '关注事件进展、各方公开回应及报道依据'),
 (r'政策|社保|国标|内需|税|补贴|就业|经济|基金', '关注政策内容、适用范围与实际影响'),
 (r'油价|降价|涨价|售价|消费|购买|赔偿|商标|汽车|手机|iPhone|小米|手表', '关注产品或服务变化、消费体验与权益'),
 (r'健康|咖啡|骨头|医院|疾病|肋骨|撸铁|肉球|防晒', '关注健康话题的证据来源与适用条件'),
 (r'英雄联盟|瑞士轮|赛程|球赛|退役|世界杯|奥运|曼城|降级|乒乓|马龙|吴艳妮', '关注赛事安排、竞技表现与选手动态'),
 (r'王者|三角洲|游戏|赛季|攻略|原神|使命召唤|新版本|妲己|KDA', '关注玩法更新、角色内容与玩家体验'),
 (r'电影|新剧|OST|首舞台|新歌|舞台|大秀|造型|演唱|清唱|配音|歌手|肖战|刘诗诗|嫁金钗|维密|IVE', '关注作品内容、舞台表达与观众反馈'),
 (r'设计|非遗|陶瓷|文化|何以中国|博物馆', '关注文化表达、创作细节与传播方式'),
 (r'大学|学校|学生|家长|老师|教育|社交', '关注当事人的具体处境与教育、社交体验'),
 (r'吃|餐|蟹|美食|乐园|东北人|南方人|少女|气质|喵|猫', '关注生活体验、表达方式与评论区的共鸣'),
]

def brief(title, cached=''):
    cached=re.sub(r'\s+',' ',str(cached or '')).strip()
    if cached:
        return (cached if len(cached)<=110 else cached[:109]+'…'),'cached_annotation'
    headline=re.sub(r'\s+',' ',str(title or '')).strip().strip('#')
    anchor=headline if len(headline)<=45 else headline[:44]+'…'
    for pattern,lens in LENSES:
        if re.search(pattern,headline,re.I):
            return '围绕“'+anchor+'”，'+lens+'。','title_rule'
    # Stay within the headline when no specific lens can be supported by it.
    return '话题要点：'+(headline if len(headline)<=88 else headline[:87]+'…')+'。','title_excerpt'
