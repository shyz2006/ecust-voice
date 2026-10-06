"""
狐友（hy.sns.sohu.com）校园社区采集 —— “本校声音”

只读取公开页面的服务端渲染数据（__NUXT_DATA__），不调用带签名的分页接口、不登录：
- 推荐流  https://hy.sns.sohu.com/?tab=recommend   （全国各校热帖，作为“校园同龄人”背景）
- 本校圈  https://hy.sns.sohu.com/circle/<circleId> （最新 24 条 + 圈内热帖 10 条）

隐私原则：
- 不保存任何用户标识（userId、昵称、头像、性别、认证状态都在解析时丢弃）；
- 正文入库前脱敏：手机号、微信/QQ 号、邮箱、学号/卡号等长数字、@提及；
- 中文姓名用 jieba 词性标注遮蔽；老师可在“本校声音”中按主题查看脱敏后的帖子正文（不含发帖人信息）。
"""

import json
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from loguru import logger

BASE = "https://hy.sns.sohu.com"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_NUXT_RE = re.compile(r'<script[^>]*id="__NUXT_DATA__"[^>]*>(.*?)</script>', re.S)
_WRAPPERS = {"Reactive", "ShallowReactive", "Ref", "ShallowRef", "EmptyRef"}

_PII_PATTERNS = [
    (re.compile(r"1[3-9]\d{9}"), "[手机号]"),
    (re.compile(r"(?i)(微信|vx|v信|wx|wechat|qq|扣扣)\s*[:：号]?\s*[A-Za-z0-9_\-]{5,}"), r"\1[已隐藏]"),
    (re.compile(r"[\w.\-]+@[\w\-]+\.[\w.]+"), "[邮箱]"),
    (re.compile(r"@\S{1,20}"), "@[同学]"),
    (re.compile(r"\d{6,}"), "[数字]"),
]
_IMG_RE = re.compile(r"\[图片\]")


def deidentify(text: str) -> str:
    text = _IMG_RE.sub("", text or "")
    for pattern, repl in _PII_PATTERNS:
        text = pattern.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()


_NAME_KEEP = {"华理", "华东", "徐汇", "奉贤", "梅陇", "上海", "高数", "马原", "毛概"}
# 常见姓氏（覆盖约 90% 人口）；jieba 的 nr 词性误报较多（如“雅思”“宝山”），只遮蔽以常见姓氏开头的 2~3 字词
_SURNAMES = set(
    "王李张刘陈杨黄赵吴周徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董袁潘于蒋蔡余杜叶程苏魏吕丁任沈姚卢姜崔"
    "钟谭陆汪范金石廖贾夏韦付方白邹孟熊秦邱江尹薛闫段雷侯龙史陶黎贺顾毛郝龚邵万钱严覃武戴莫孔向汤常温康施文牛樊葛邢"
    "安齐易乔伍庞颜倪庄聂章鲁岳翟殷詹申欧耿关兰焦俞左柳甘祝包宁尚符舒阮柯纪梅童凌毕单季裴霍涂成苗谷盛曲翁冉骆蓝路游辛"
    "靳管柴蒙鲍华喻祁蒲房滕屈饶解牟艾尤阳时穆农司卓古吉缪简车项连芦麦褚娄窦戚岑景党宫费卜冷晏席卫米柏宗瞿桂全佟应臧闵"
    "苟邬边卞姬师和仇栾隋商刁沙荣巫寇桑郎甄丛仲虞敖巩明佘池查麻苑迟邝")


def _looks_like_name(word: str) -> bool:
    return 2 <= len(word) <= 3 and word[0] in _SURNAMES and word not in _NAME_KEEP


def mask_names(text: str) -> str:
    """用 jieba 词性标注（nr=人名）遮蔽帖子中的真实姓名；正则无法覆盖中文姓名。"""
    try:
        import jieba.posseg as pseg
    except Exception:  # pragma: no cover
        return text
    out = []
    for word, flag in pseg.cut(text or ""):
        out.append("[姓名]" if flag == "nr" and _looks_like_name(word) else word)
    # “杨yi老师”“z同学”这类姓 + 拼音 / 字母缩写的称呼
    return _PINYIN_NAME_RE.sub("[姓名]", "".join(out))


_PINYIN_NAME_RE = re.compile(
    r"(?:(?<![\u4e00-\u9fff])[" + "".join(sorted(_SURNAMES)) + r"][A-Za-z]{1,8}|[A-Za-z]{1,3})"
    r"(?=老师|教授|导师|同学|学长|学姐|学弟|学妹)")


def _decode_nuxt(html: str) -> Optional[Dict[str, Any]]:
    m = _NUXT_RE.search(html)
    if not m:
        return None
    data = json.loads(m.group(1))

    def res(i, depth=0):
        v = data[i]
        if depth > 16:
            return None
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in _WRAPPERS:
                return res(v[1], depth + 1) if len(v) > 1 else None
            return [res(x, depth + 1) if isinstance(x, int) else x for x in v]
        if isinstance(v, dict):
            return {k: (res(x, depth + 1) if isinstance(x, int) else x) for k, x in v.items()}
        return v

    return res(0)


def _fetch(path: str) -> Optional[Dict[str, Any]]:
    resp = requests.get(BASE + path, headers={"User-Agent": _UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                        timeout=20)
    resp.raise_for_status()
    root = _decode_nuxt(resp.text)
    return (root or {}).get("data") or {}


def _post(feed: Dict[str, Any], scope: str, hot: bool) -> Optional[Dict[str, Any]]:
    src = feed.get("sourceFeed") or feed
    content = mask_names(deidentify(src.get("content") or ""))
    if len(content) < 4:
        return None
    circle = src.get("circle") or {}
    ts_ms = src.get("score") or 0
    return {
        "feed_id": str(src.get("feedId") or ""),
        "content": content[:400],
        "circle": circle.get("circleName") or "",
        "exposure": int(src.get("exposureCount") or 0),
        "comments": int(src.get("commentCount") or 0),
        "published": int(ts_ms / 1000) if ts_ms and ts_ms > 1e12 else None,
        "scope": scope,
        "hot": hot,
    }


def _walk_feed_lists(obj: Any) -> List[Dict[str, Any]]:
    out = []
    if isinstance(obj, dict):
        if isinstance(obj.get("feedList"), list):
            out.extend(obj["feedList"])
        for v in obj.values():
            if isinstance(v, (dict, list)):
                out.extend(_walk_feed_lists(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_walk_feed_lists(v))
    return out


def fetch_recommend() -> List[Dict[str, Any]]:
    data = _fetch("/?tab=recommend")
    posts = [_post(f, "national", True) for f in _walk_feed_lists(data)]
    return [p for p in posts if p]


def fetch_circle(circle_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    data = _fetch(f"/circle/{circle_id}")
    name = ""
    posts: List[Dict[str, Any]] = []
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        if "hotFeedList" in value:  # 圈子信息块
            name = value.get("circleName") or name
            posts += [_post(f, "school", True) for f in value.get("hotFeedList") or []]
        if key.startswith("feed-circle"):
            posts += [_post(f, "school", False) for f in value.get("feedList") or []]
    return name, [p for p in posts if p]


def collect(circle_ids: List[str], include_recommend: bool = True) -> Dict[str, Any]:
    """返回可直接入库的条目（source=huyou-school / huyou-national），rank 按互动量排序。"""
    posts: List[Dict[str, Any]] = []
    errors: Dict[str, str] = {}
    circles: Dict[str, str] = {}
    for cid in circle_ids:
        try:
            name, got = fetch_circle(cid)
            circles[cid] = name
            posts += got
            time.sleep(1.0)
        except Exception as exc:
            errors[f"huyou:{cid}"] = str(exc)[:200]
    if include_recommend:
        try:
            posts += fetch_recommend()
        except Exception as exc:
            errors["huyou:recommend"] = str(exc)[:200]

    # 去重（同一帖子可能同时出现在热帖与最新列表）
    seen, unique = set(), []
    for p in posts:
        key = p["feed_id"] or p["content"][:40]
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    items = []
    for scope, source in (("school", "huyou-school"), ("national", "huyou-national")):
        group = sorted((p for p in unique if p["scope"] == scope),
                       key=lambda p: -(p["exposure"] + 30 * p["comments"]))
        for rank, p in enumerate(group, start=1):
            items.append({
                "source": source,
                "rank": rank,
                "title": p["content"][:80],
                "url": "https://hy.sns.sohu.com/?feedDetail=" + p["feed_id"] if p["feed_id"].isdigit() else None,  # 公开帖子地址；不保存作者标识
                "extra": {k: p[k] for k in ("content", "circle", "exposure", "comments", "published", "hot", "feed_id")},
            })
    if circle_ids and not any(i["source"] == "huyou-school" for i in items):
        errors.setdefault("huyou:school", "本校圈子未取到帖子")
    logger.info(f"[CampusPulse] 狐友：本校 {sum(i['source'] == 'huyou-school' for i in items)} 条，"
                f"全国推荐 {sum(i['source'] == 'huyou-national' for i in items)} 条，圈子 {circles}")
    return {"items": items, "errors": errors, "circles": circles}
