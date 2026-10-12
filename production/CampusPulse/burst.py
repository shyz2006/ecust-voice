"""
突发词检测 —— TopicSketch (Xie et al., ICDM 2013) 思想的轻量实现

TopicSketch 的核心观察：突发话题的判据不是"量大"，而是"加速度大"。
它用两个不同时间尺度的指数平滑速度之差来估计加速度，并用 sketch
(哈希计数矩阵) 把状态压缩到固定内存，从而能在流上实时运行。

这里做了两点适配：
1. 热榜数据是"带名次的列表"而非原始推文流，每条观测按名次折损加权
   w(rank) = 1 / log2(rank + 1)，跨平台同时上榜会自然叠加权重；
2. 批次间隔不固定（手动/定时采集），速度按真实时间差做连续衰减：
   v <- v * exp(-dt / tau) + x / tau
"""

import io
import math
import re
import time
from typing import Dict, Iterable, List, Tuple

import numpy as np

from . import storage

try:
    import jieba

    jieba.setLogLevel(60)
except Exception:  # pragma: no cover
    jieba = None

_STOPWORDS = set(
    """
    的 了 是 在 和 与 及 或 被 把 对 为 从 到 有 也 就 都 而 又 很 更 最 还 并 等 这 那 其 之 以 于 上 下 中
    一个 什么 怎么 如何 为什么 哪些 没有 不是 可以 已经 回应 官方 最新 曝光 网友 热议 现场 视频 事件 公布
    今天 今年 明天 昨天 表示 发布 正式 称 将 后 前 个 年 月 日 我们 他们 你们 自己 还是 真的 就是 这个 那个
    """.split()
)

_TOKEN_RE = re.compile(r"[一-鿿A-Za-z0-9]+")


def tokenize(text: str) -> List[str]:
    text = text or ""
    if jieba is None:
        # 退化方案：中文按二元组切分
        out = []
        for seg in _TOKEN_RE.findall(text):
            if re.fullmatch(r"[A-Za-z0-9]+", seg):
                out.append(seg.lower())
            else:
                out.extend(seg[i : i + 2] for i in range(max(1, len(seg) - 1)))
        return [t for t in out if len(t) >= 2 and t not in _STOPWORDS]
    tokens = []
    for tok in jieba.lcut(text):
        tok = tok.strip().lower()
        if len(tok) < 2 or tok in _STOPWORDS or tok.isdigit():
            continue
        if not _TOKEN_RE.fullmatch(tok):
            continue
        tokens.append(tok)
    return tokens


def rank_weight(rank: int) -> float:
    return 1.0 / math.log2(rank + 1)


class AccelerationSketch:
    """d x w 的哈希矩阵，每个桶维护快/慢两个时间尺度的速度估计。"""

    KEY = "burst_sketch_v1"

    def __init__(self, depth: int = 4, width: int = 4096,
                 tau_fast_h: float = 2.0, tau_slow_h: float = 24.0):
        self.depth = depth
        self.width = width
        self.tau_fast = tau_fast_h * 3600
        self.tau_slow = tau_slow_h * 3600
        self.fast = np.zeros((depth, width), dtype=np.float64)
        self.slow = np.zeros((depth, width), dtype=np.float64)
        self.last_ts: float = 0.0
        self.n_batches = 0
        self._seeds = np.array([0x9E3779B1, 0x85EBCA77, 0xC2B2AE3D, 0x27D4EB2F, 0x165667B1,
                                0xD3A2646C, 0xFD7046C5, 0xB55A4F09][:depth], dtype=np.uint64)

    # --- 哈希：Python 的 hash() 带随机盐，跨进程不稳定，这里用 FNV-1a
    def _buckets(self, term: str) -> np.ndarray:
        h = 0xCBF29CE484222325
        for b in term.encode("utf-8"):
            h ^= b
            h = (h * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        mixed = (np.uint64(h) ^ self._seeds) * np.uint64(0x9E3779B97F4A7C15)
        return (mixed >> np.uint64(17)) % np.uint64(self.width)

    def _decay_to(self, ts: float) -> None:
        if self.last_ts:
            dt = max(0.0, ts - self.last_ts)
            self.fast *= math.exp(-dt / self.tau_fast)
            self.slow *= math.exp(-dt / self.tau_slow)
        self.last_ts = ts

    def update(self, observations: Dict[str, float], ts: float, expected_interval_s: float = 1800) -> None:
        rows = np.arange(self.depth)
        if self.n_batches == 0:
            # 冷启动种子化：假设首批已在榜的词处于稳态，直接写入稳态速度
            # v* = x·(3600/τ) / (1 - e^{-Δ/τ})，否则慢速基线要 1~2 天才收敛，期间所有词都像在"加速"
            gain_f = (3600 / self.tau_fast) / (1 - math.exp(-expected_interval_s / self.tau_fast))
            gain_s = (3600 / self.tau_slow) / (1 - math.exp(-expected_interval_s / self.tau_slow))
            for term, x in observations.items():
                cols = self._buckets(term).astype(np.int64)
                self.fast[rows, cols] += x * gain_f
                self.slow[rows, cols] += x * gain_s
            self.last_ts = ts
            self.n_batches = 1
            return
        self._decay_to(ts)
        # 速度单位：每小时权重
        for term, x in observations.items():
            cols = self._buckets(term).astype(np.int64)
            self.fast[rows, cols] += x * 3600 / self.tau_fast
            self.slow[rows, cols] += x * 3600 / self.tau_slow
        self.n_batches += 1

    def estimate(self, term: str) -> Tuple[float, float]:
        cols = self._buckets(term).astype(np.int64)
        rows = np.arange(self.depth)
        return float(self.fast[rows, cols].min()), float(self.slow[rows, cols].min())

    def burst_score(self, term: str) -> float:
        """加速度除以慢速度的平方根（泊松噪声近似），得到类 z 分数。"""
        fast, slow = self.estimate(term)
        return (fast - slow) / math.sqrt(slow + 0.05)

    # --- 持久化
    def dumps(self) -> bytes:
        buf = io.BytesIO()
        np.savez_compressed(buf, fast=self.fast, slow=self.slow,
                            meta=np.array([self.last_ts, self.n_batches, self.tau_fast, self.tau_slow]))
        return buf.getvalue()

    @classmethod
    def load(cls) -> "AccelerationSketch":
        sk = cls()
        blob = storage.kv_get(cls.KEY)
        if not blob:
            return sk
        try:
            data = np.load(io.BytesIO(blob))
            if data["fast"].shape == sk.fast.shape:
                sk.fast, sk.slow = data["fast"], data["slow"]
                sk.last_ts, n, sk.tau_fast, sk.tau_slow = data["meta"].tolist()
                sk.n_batches = int(n)
        except Exception:
            pass
        return sk

    def save(self) -> None:
        storage.kv_set(self.KEY, self.dumps())


def batch_observations(items: Iterable[Dict]) -> Dict[str, float]:
    """把一个批次的热榜条目转为 {词: 名次加权曝光量}；同一条目内的重复词只计一次。"""
    obs: Dict[str, float] = {}
    for it in items:
        w = rank_weight(int(it["rank"]))
        for tok in set(tokenize(it["title"])):
            obs[tok] = obs.get(tok, 0.0) + w
    return obs


def ingest_batch(items: List[Dict], ts: float = None, expected_interval_s: float = 1800) -> AccelerationSketch:
    sketch = AccelerationSketch.load()
    sketch.update(batch_observations(items), ts or time.time(), expected_interval_s)
    sketch.save()
    return sketch
