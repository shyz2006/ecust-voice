"""
百度贴吧本校吧采集 —— “本校声音”的第二个数据源

使用贴吧移动网页版自己调用的公开列表接口（/mg/f/getFrsData，无需登录、无签名）。
PC 版 /f?kw= 对脚本访问会返回“百度安全验证”，不做绕过。

隐私原则与狐友一致：不保存作者信息；保存公开原帖链接用于核查，正文作主题聚合。
"""

import time
from typing import Any, Dict, List

import requests
from loguru import logger

from .huyou import deidentify, mask_names

_URL = "https://tieba.baidu.com/mg/f/getFrsData"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
                   "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"),
    "Referer": "https://tieba.baidu.com/",
}


def _abstract(thread: Dict[str, Any]) -> str:
    parts = thread.get("abstract") or []
    return " ".join(p.get("text", "") for p in parts if isinstance(p, dict))


def fetch_forum(kw: str, pages: int = 2) -> List[Dict[str, Any]]:
    threads: List[Dict[str, Any]] = []
    for pn in range(1, pages + 1):
        resp = requests.get(_URL, params={"kw": kw, "rn": 30, "pn": pn, "sort_type": 0},
                            headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        data = (resp.json() or {}).get("data") or {}
        threads += data.get("thread_list") or []
        time.sleep(1.0)
    posts = []
    for t in threads:
        if t.get("is_top"):  # 置顶多为吧规/公告
            continue
        title = mask_names(deidentify(t.get("title") or ""))
        body = mask_names(deidentify(_abstract(t)))
        content = f"{title}｜{body}" if body and body not in title else title
        if len(content) < 4:
            continue
        posts.append({
            "content": content[:400],
            "circle": kw + "吧",
            "exposure": 0,
            "comments": int(t.get("reply_num") or 0),
            "published": int(t.get("create_time") or 0) or None,
            "hot": False,
            "link": f"https://tieba.baidu.com/p/{t['tid']}" if t.get("tid") else None,
        })
    return posts


def collect(forums: List[str]) -> Dict[str, Any]:
    items, errors = [], {}
    for kw in forums:
        try:
            posts = fetch_forum(kw)
        except Exception as exc:
            errors[f"tieba:{kw}"] = str(exc)[:200]
            continue
        for rank, p in enumerate(sorted(posts, key=lambda p: -p["comments"]), start=1):
            items.append({"source": "tieba-school", "rank": rank, "title": p["content"][:80], "url": None,
                          "extra": p})
    logger.info(f"[CampusPulse] 本校贴吧：{len(items)} 帖 {forums}")
    return {"items": items, "errors": errors}
