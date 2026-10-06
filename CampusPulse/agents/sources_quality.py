"""
证据来源质量分级

A 官方 / 主流媒体：政府、高校、央媒与主要新闻网站
B 平台原帖 / 热榜：微博、B 站、抖音、知乎、贴吧、狐友等平台原始内容，以及本系统采集的热榜
C 普通媒体：其他新闻与门户网站
D 梗百科 / 自媒体聚合：百科、梗词典、自媒体号、内容农场 —— 可作释义线索，不宜单独支撑事实
"""

import re
from urllib.parse import urlparse

_A = re.compile(r"(\.gov\.cn|\.edu\.cn|people\.com\.cn|xinhuanet\.com|news\.cn|cctv\.com|cctv\.cn|chinanews\.com|"
                r"gmw\.cn|thepaper\.cn|china\.com\.cn|youth\.cn|chinadaily\.com\.cn|cnr\.cn|ce\.cn|jyb\.cn|"
                r"bjnews\.com\.cn|caixin\.com|yicai\.com|cyol\.com|81\.cn|ecnu\.edu|ecust\.edu)$")
_B = re.compile(r"(bilibili\.com|b23\.tv|weibo\.com|weibo\.cn|douyin\.com|zhihu\.com|tieba\.baidu\.com|"
                r"xiaohongshu\.com|hy\.sns\.sohu\.com|kuaishou\.com|v\.qq\.com)$")
_D = re.compile(r"(baike\.baidu\.com|baike\.sogou\.com|jikipedia\.com|wiki|baijiahao\.baidu\.com|mbd\.baidu\.com|"
                r"163\.com|sohu\.com|toutiao\.com|sina\.cn|qq\.com|ifeng\.com|zol\.com\.cn|360doc\.com|"
                r"jianshu\.com|csdn\.net|douban\.com|smzdm\.com|ximalaya\.com|xiaoheihe)$")
TIER_LABELS = {"A": "官方/主流媒体", "B": "平台原帖/热榜", "C": "普通媒体", "D": "梗百科/自媒体"}


def classify(kind: str, url: str = "") -> str:
    if kind == "H":
        return "B"
    if kind == "M":
        return "C"  # 系统自己的梗词典记忆：可复用，但不是独立来源
    host = (urlparse(url or "").hostname or "").lower()
    if not host:
        return "C"
    if _A.search(host):
        return "A"
    if _B.search(host):
        return "B"
    # sohu.com/a/ 与 163.com/dy/ 等为自媒体号；门户新闻频道记为 C
    if _D.search(host) or "/dy/" in (url or "") or "/a/" in (url or ""):
        return "D" if not host.startswith("news.") else "C"
    return "C"


def domain(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower()
    parts = host.split(".")
    return ".".join(parts[-3:] if host.endswith((".com.cn", ".edu.cn", ".gov.cn")) else parts[-2:]) if host else ""
