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

# The public taxonomy is broader than the legacy psychological tagging vocabulary.
# Exact phrases and intent patterns keep the decision inspectable without forcing a quota.
TOPIC_WORDS = {
 '学业课程': '作业 课程 上课 下课 选课 退课 老师 教授 导师 助教 教材 课本 习题 答案 网课 学分 绩点 学时 学位 论文 开题 答辩 实验 报告 高数 线代 大物 高化 物化 有机 无机 分析化学 分离分析 工程制图 数据结构 算法 统计学 会计 军理 军事理论 大创 数模 美赛 数学建模 小组 组员 学习方法 学不会 补课 水课 满课 教务 培养方案 综测 奖学金 助学金 贫困生 补助 助学贷款 优干 优生 专业 智能制造 分流 转专业'.split(),
 '考试考证': '考试 考题 考卷 试卷 往届题 真题 刷题 期中 期末 补考 重修 挂科 缓考 监考 考场 复习 成绩 查分 四级 六级 雅思 托福 考证 普通话 计算机二级 驾照 驾校 科目一 科目二 科目三 科目四 教资 资格证'.split(),
 '升学就业': '考研 保研 推免 读研 研究生 专硕 学硕 博士 硕士 留学 复试 调剂 择校 直博 学校排名 985 211 秋招 春招 实习 offer 简历 面试 招聘 找工作 找不到工作 就业 考公 考编 选调 公务员 校招 签约 三方 考博 出国 升学'.split(),
 '校园设施与管理': '图书馆 教室 机房 场馆 校园卡 一卡通 门禁 校门 通行证 共享单车 自行车 电动车 充气 校车 巴士 公交 地铁 停车 充电桩 出行 路灯 路面 臭水沟 排水 空调 网络 断网 宽带 wifi vpn 账号 注册 认证 财务大厅 报修 信号 电话卡 套餐 移动 联通 电信 校历 公休 放假 调休 开学 门口 围合 操场 开放时间'.split(),
 '食堂与生活服务': '食堂 外卖 吃饭 早餐 午饭 晚饭 夜宵 餐厅 饭店 美食 麻辣烫 小面 烧烤 火锅 咖啡 奶茶 酸奶 面包 红烧肉 一卡司 全家 瑞幸 蜜雪 饿了 肚子饿 好吃 难吃 商业街 天街 超市 快递 驿站 理发 剪发 剪头发 发型 打耳洞 洗衣 饮水 接水 热水器 取餐 生活费 退卡 红力 健身房 店铺 开门 营业'.split(),
 '宿舍生活': '宿舍 寝室 舍友 室友 床位 床帘 床垫 围合楼 寝楼 搬宿舍 熄灯 洗澡 浴室 水卡 水费 电费 宿管 阿姨查寝 门锁 蟑螂 老鼠 洗漱 吹风机 干发器 楼道 走廊 打呼噜 打鼾 隔音 扰民 吵醒 深夜噪音 合租 转租 租房 公寓 房租 押金 租金 loft'.split(),
 '社交与同伴': '搭子 组队 队友 捞人 捞捞 一起 一块 交友 朋友 没朋友 孤独 社恐 破冰 融入 约饭 拼桌 群聊 进群 微信群 qq群 乒乓球群 姐妹 学长 学姐 诡秘 闺蜜 互勉 摄影 互相拍照 同学关系 人际 舍友情 同伴 聚会 聚餐 聚一聚 谁愿意'.split(),
 '恋爱情感': '恋爱 对象 男朋友 女朋友 男友 女友 暗恋 表白 分手 复合 前任 失恋 脱单 追女生 追男生 相亲 心动 喜欢的人 男生喜欢 女生喜欢 感情 暧昧 牵手 情侣 异地恋 嫁给 约会'.split(),
 '身心与情绪': '焦虑 难过 难受 崩溃 压力 抑郁 失眠 睡不着 心理咨询 心情 伤心 委屈 烦躁 烦死 情绪 破防 内耗 绷不住 苦闷 绝望 生病 感冒 医院 医保 校医院 发烧 咳嗽 近视 受伤 疼痛 疼死 挂号 看病 健康 身体 牙齿 牙疼 胃疼 头疼 疲惫 疲劳 累死 好累 戒烟'.split(),
 '文体与实践': '体测 免测 重测 补测 缺项 肺活量 体锻 晨跑 校园跑 健康跑 引体向上 八百米 800米 1000米 体育 健身 羽毛球 乒乓球 篮球 足球 排球 网球 游泳 飞盘 跑步 运动 比赛 球赛 百团大战 社团 招新 志愿 团日 党日 支教 义工 公益 献血 实践 音乐 演唱会 音乐节 歌手 弹琴 动漫 动画 番剧 漫画 电影 电视剧 综艺 游戏 原神 王者 荣耀 星穹 铁道 lol cs2 三角洲 二次元 cos 汉服 旅游 旅行 出游 拍照 摄影 展览 迪士尼 港迪 嫁金钗 bleach'.split(),
 '交易与互助': '二手 闲置 转让 跑腿 代取 代课 代签 代写 代做 有偿 失物 丢失 遗失 捡到 拾到 招领 寻物 归还 拾取 借用 求借 借一下 租正装 低价 拼单 拼团 代购 求购 卖书 卖掉 出售 收购 帮忙 互助 诈骗 骗子 被骗 避雷 退钱 赔偿'.split(),
}
for _theme,_extra in {
 '学业课程':'概率论 大英赛 平时分 国励 社工奖 助学贷 学生干部 拔尖计划 德育分 贯通课 免听 讲座 荣誉称号 报告册 python',
 '校园设施与管理':'消防警报 非机动车道 邮箱 邮件 登录 登不上 请假 报销 打印 atm 银行卡 保卫处 北侧门 通海厅 保质期 校务',
 '宿舍生活':'晒被子 蚊子 噪音 小声 睡觉 偷袜子',
 '食堂与生活服务':'汉堡 豆浆 便利店 眼镜店 配眼镜 可乐 洗头膏 食品',
 '文体与实践':'万智牌 赛博朋克 边缘行者 观影 奶龙 初音 赛马娘 乒乓 体适能 inbody 手游 手办 吧唧 杨玉环 电影节 读书',
 '身心与情绪':'肚子疼 皮炎 性压抑 peer pressure',
 '交易与互助':'出这本书 收概率论 书本 正装 出iphone',
}.items():TOPIC_WORDS[_theme].extend(_extra.split())

INTENTS = {
 '交易与互助': re.compile(r'(?:^|[，。！？\s])(?:出|收|求购|shou)(?:一本|一套|一桶|[这那本张件个]|书|票|羽毛球|电动车|校园卡)|(?:\d+(?:\.\d+)?\s*(?:元|块|r|米).{0,8}(?:出|收|带走))|(?:求|借).{0,6}(?:电子版|答案|资料)|(?:丢|掉|落).{0,5}(?:耳机|帽子|钱包|证件|卡)|(?:耳机|帽子|校园卡).{0,6}(?:捡|丢|招领)|(?:有一个|有个).{0,4}(?:耳机|校园卡|钥匙)|有没有人拼'),
 '学业课程': re.compile(r'(?:学|上|听|这|这些).{0,3}课|(?:求|交|写|改).{0,4}报告|老师.{0,8}(?:时间|地点|讲|课)|(?:化学|物理|数学|金融|经济|会计|统计|计算机).{0,6}(?:学|课|题|原理|实验)'),
 '社交与同伴': re.compile(r'(?:有没有|找|捞|求|约).{0,8}(?:搭子|队友|朋友|一起|一块|组员)|(?:捞|找).{0,8}(?:姐妹|同学|人一起)'),
}

def classify(content):
    text=(content or '').lower()
    hits={theme:[w for w in words if w.lower() in text] for theme,words in TOPIC_WORDS.items()}
    scores={theme:sum(min(len(w),4) for w in words) for theme,words in hits.items()}
    for theme,pattern in INTENTS.items():
        if pattern.search(text):scores[theme]+=8;hits[theme].append('表达意图')
    if re.search(r'[零一二三四五六七八九十百]+(?:元|块).{0,5}出',text):
        scores['交易与互助']+=8;hits['交易与互助'].append('金额与转让意图')
    # Specific contexts outrank generic mentions (e.g. playing together vs finding a teammate).
    if re.search(r'找|捞|求|有没有|约',text) and re.search(r'搭子|队友|一起|一块|组员',text):
        scores['社交与同伴']+=9
    if re.search(r'体测|晨跑|校园跑|健康跑|肺活量|引体向上',text):scores['文体与实践']+=10
    if re.search(r'转租|租房|公寓|房租|合租',text):scores['宿舍生活']+=8
    if re.search(r'捡到|拾到|招领|丢失|遗失',text):scores['交易与互助']+=10
    best=max(scores,key=scores.get)
    return {'theme':best if scores[best] else '其他校园讨论','matched':hits[best] if scores[best] else [],
            'score':scores[best],'version':'campus-topics-2'}

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
