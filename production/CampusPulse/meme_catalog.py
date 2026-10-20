"""Reviewed expressions: definition references, observed examples and search are distinct."""
import re
from urllib.parse import quote,urlsplit

ANNUAL='https://finance.people.com.cn/n1/2024/1202/c1004-40373589.html'
LANGUAGE='https://nlp.ccnu.edu.cn/news/133'
MUSIC='https://k.sina.cn/article_6724296968_190cca10801901cf5w.html?from=tech'
# Definitions are short editorial paraphrases; examples below are illustrative, not student quotes.
CATALOG=[
 {'term':'哈基米','aliases':['哈基米'],'meaning':'从动画哼唱片段延伸出的音乐梗，也常出现在萌宠和鬼畜二创里。','usage':'给宠物视频配音，或和朋友分享洗脑小曲。','example':'这段小猫视频配上哈基米，已经循环三遍。','reference':MUSIC,'reference_title':'哈基米与曼波的二创传播','form':'音乐与空耳'},
 {'term':'曼波','aliases':['曼波'],'meaning':'由动画角色的哼唱经二创传播，常被用作轻快、魔性的音效和接梗口号。','usage':'评论区接梗、音效混剪和朋友间的无厘头互动。','example':'本来只想看十秒，结果脑子里一直在曼波。','reference':MUSIC,'reference_title':'哈基米与曼波的二创传播','form':'音乐与空耳'},
 {'term':'抽象','aliases':['抽象'],'meaning':'用跳脱常理、夸张错位的语言或表演制造荒诞的笑点。','usage':'调侃意料之外的操作，或分享看似离谱却好笑的小事。','example':'这个小组的汇报开场，有点抽象但很难忘。','reference':'https://health.people.com.cn/n1/2026/0104/c14739-40638215.html','reference_title':'抽象表达流行的背后','form':'表达风格'},
 {'term':'硬控','aliases':['硬控'],'meaning':'从游戏控制技能引申为注意力被某个人、内容或场景牢牢吸引。','usage':'形容一段演出、一个视频或一道菜让自己停下手边的事。','example':'被社团演出的开场硬控了三分钟。','reference':ANNUAL,'reference_title':'2024年度十大流行语解读','form':'词义延伸','pattern':r'被.{0,30}硬控|硬控.{0,12}(?:秒|分钟|小时|了)'},
 {'term':'电子榨菜','aliases':['电子榨菜'],'meaning':'适合吃饭时顺手观看、陪伴用餐的影视片段或视频内容。','usage':'分享下饭节目和轻松视频清单。','example':'今天的电子榨菜，是昨晚没看完的那一集。','reference':'https://opinion.people.com.cn/n1/2022/1214/c1003-32587056.html','reference_title':'看向电子榨菜的目光应多些善意','form':'生活比喻'},
 {'term':'搭子','aliases':['饭搭子','学习搭子','考研搭子','运动搭子','旅游搭子','搭子社交'],'meaning':'围绕吃饭、学习、运动等具体兴趣或任务结伴的伙伴。','usage':'寻找时间、目标或兴趣合拍的同伴。','example':'周末图书馆学习搭子，还缺一位。','reference':'https://news.wust.edu.cn/info/1081/364622.htm','reference_title':'高校记者调查：搭子社交','form':'社交表达'},
 {'term':'浓人 / 淡人','aliases':['浓人','淡人'],'meaning':'分别用来描述外显热情和内敛平和的表达风格，是轻松的自我描述。','usage':'聊一聊室友或朋友之间的性格与相处习惯。','example':'浓人负责欢呼，淡人负责把照片拍清楚。','reference':LANGUAGE,'reference_title':'语言资源监测中心：浓人淡人','form':'性格比喻'},
 {'term':'松弛感','aliases':['松弛感'],'meaning':'面对节奏、压力与变化时呈现出的从容、自在状态。','usage':'描述穿搭、出游或做事时自然放松的感觉。','example':'交完报告去操场走走，找回一点松弛感。','reference':ANNUAL,'reference_title':'2024年度十大流行语解读','form':'状态描述'},
 {'term':'破防','aliases':['破防'],'meaning':'从游戏术语延伸为心理防线被触动，既可表达感动，也可表达受挫。','usage':'被一句关心打动，或用自嘲回应小挫折。','example':'朋友记得我随口说过的小愿望，真的破防了。','reference':'https://opinion.people.com.cn/n1/2022/0101/c1003-32322288.html','reference_title':'破防的含义与语境','form':'情绪表达'},
 {'term':'班味','aliases':['班味','班味儿'],'meaning':'用来调侃工作节奏带来的疲惫感和状态变化。','usage':'实习或忙碌一周后，轻松聊聊自己的状态。','example':'实习结束先去吃顿好的，去去班味。','reference':LANGUAGE,'reference_title':'语言资源监测中心：班味儿','form':'自嘲表达'},
]

def observed_match(base,title):
    if not any(word.lower() in title.lower() for word in base['aliases']):return False
    return bool(re.search(base['pattern'],title)) if base.get('pattern') else True

def platform_search(platform,term):
    q=quote(term.replace(' / ',' '))
    return {'B站':f'https://search.bilibili.com/all?keyword={q}','抖音':f'https://www.douyin.com/search/{q}',
            '微博':f'https://s.weibo.com/weibo?q={q}','百度':f'https://www.baidu.com/s?wd={q}'}[platform]

def is_observed_url(url):
    parsed=urlsplit(url);host=parsed.hostname or ''
    return (parsed.scheme in ('http','https') and bool(parsed.path.strip('/'))
            and not host.startswith('search.') and host!='s.weibo.com'
            and not parsed.path.startswith('/search')
            and not (host.endswith('baidu.com') and parsed.path in ('/s','/link','/board')))

def build(items):
    result=[]
    for platform in ('B站','抖音','微博','百度'):
        for base in CATALOG:
            candidates=sorted((x for x in items if x['platform']==platform and x.get('url') and observed_match(base,x['title'])),key=lambda x:-x['ts'])
            seen=set();links=[]
            for item in candidates:
                parsed=urlsplit(item['url'])
                # Search entry points are discovery tools, not observed posts.
                if not is_observed_url(item['url']) or item['url'] in seen:continue
                seen.add(item['url']);links.append(item)
                if len(links)==2:break
            result.append({k:v for k,v in base.items() if k not in ('aliases','pattern')} | {
                'platform':platform,'links':links,'examples':[base['example']],
                'reference_url':base['reference'],'search_url':platform_search(platform,base['term']),
                'evidence_status':'近期采集用例' if links else '常用表达',
            })
    return result
