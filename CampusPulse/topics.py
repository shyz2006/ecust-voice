"""
跨平台话题聚合 —— BERTopic (Grootendorst, 2022) 流程的轻量版

BERTopic = 文档嵌入 → 降维 → 聚类 → class-based TF-IDF 提取主题词。
热榜标题很短（10~30 字），且同一事件在不同平台措辞不同，因此：
- 嵌入：字符 2~3 gram TF-IDF（对短中文标题比词袋更稳，无需下载模型）；
- 聚类：余弦相似度阈值 + 并查集（标题数只有几百，不需要 HDBSCAN）；
- 主题词：c-TF-IDF，W(t,c) = tf(t,c) * log(1 + A / f(t))，A 为每类平均词数。
"""

import math
from collections import Counter, defaultdict
from typing import Dict, List

import numpy as np

from .burst import AccelerationSketch, rank_weight, tokenize

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
except Exception:  # pragma: no cover
    TfidfVectorizer = None


def _similarity_matrix(titles: List[str]) -> np.ndarray:
    if TfidfVectorizer is not None:
        vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), sublinear_tf=True)
        X = vec.fit_transform(titles)
        return (X @ X.T).toarray()
    # 退化方案：词集合 Jaccard
    sets = [set(tokenize(t)) for t in titles]
    n = len(sets)
    sim = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            u = len(sets[i] | sets[j]) or 1
            sim[i, j] = sim[j, i] = len(sets[i] & sets[j]) / u
    return sim


def _union_find_clusters(sim: np.ndarray, threshold: float) -> List[List[int]]:
    n = sim.shape[0]
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    ii, jj = np.where(np.triu(sim, k=1) >= threshold)
    for i, j in zip(ii.tolist(), jj.tolist()):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
    groups: Dict[int, List[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values())


def c_tf_idf(cluster_tokens: List[List[str]], top_n: int = 6) -> List[List[str]]:
    tfs = [Counter(toks) for toks in cluster_tokens]
    avg_words = (sum(len(t) for t in cluster_tokens) / max(1, len(cluster_tokens))) or 1.0
    freq = Counter()
    for tf in tfs:
        freq.update(tf)
    out = []
    for tf in tfs:
        scored = {t: c * math.log(1 + avg_words / freq[t]) for t, c in tf.items()}
        out.append([t for t, _ in sorted(scored.items(), key=lambda kv: -kv[1])[:top_n]])
    return out


def build_topics(items: List[Dict], sketch: AccelerationSketch,
                 prev_titles: Dict[str, int] = None, threshold: float = 0.32,
                 max_topics: int = 60) -> List[Dict]:
    """
    items: 当前批次热榜条目；prev_titles: 上一批次 {标题: 最好名次}，用于计算新上榜与名次变化。
    返回按综合分降序的话题列表。
    """
    if not items:
        return []
    prev_titles = prev_titles or {}
    # 同标题（跨平台）先合并
    by_title: Dict[str, List[Dict]] = defaultdict(list)
    for it in items:
        by_title[it["title"]].append(it)
    titles = list(by_title.keys())

    sim = _similarity_matrix(titles)
    clusters = _union_find_clusters(sim, threshold)
    cluster_tokens = [[tok for i in idxs for tok in tokenize(titles[i])] for idxs in clusters]
    keywords = c_tf_idf(cluster_tokens)

    warm = sketch.n_batches >= 2  # 首批只用于种子化基线
    topics = []
    for idxs, kws in zip(clusters, keywords):
        entries = [e for i in idxs for e in by_title[titles[i]]]
        sources = sorted({e["source"] for e in entries})
        heat = sum(rank_weight(e["rank"]) for e in entries)
        best_rank = min(e["rank"] for e in entries)
        # 代表标题：该类内曝光权重最高的标题
        rep = max(idxs, key=lambda i: sum(rank_weight(e["rank"]) for e in by_title[titles[i]]))
        burst_terms = sorted(((sketch.burst_score(k), k) for k in kws), reverse=True)
        burst = max(0.0, burst_terms[0][0]) if burst_terms else 0.0
        is_new = all(titles[i] not in prev_titles for i in idxs)
        prev_best = min((prev_titles[titles[i]] for i in idxs if titles[i] in prev_titles), default=None)
        rank_delta = (prev_best - best_rank) if prev_best is not None else None

        score = heat * (1 + 0.35 * (len(sources) - 1))
        if warm:
            score *= 1 + min(burst, 6.0) / 3
        topics.append(
            {
                "label": titles[rep],
                "keywords": kws,
                "titles": [titles[i] for i in idxs][:12],
                "entries": [
                    {"source": e["source"], "rank": e["rank"], "title": e["title"], "url": e.get("url")}
                    for e in sorted(entries, key=lambda e: e["rank"])
                ][:20],
                "sources": sources,
                "heat": round(heat, 3),
                "best_rank": best_rank,
                "burst": round(burst, 3) if warm else None,
                "burst_terms": [k for s, k in burst_terms if s > 1.0][:3] if warm else [],
                "is_new": is_new and bool(prev_titles),
                "rank_delta": rank_delta,
                "score": round(score, 4),
            }
        )
    topics.sort(key=lambda t: -t["score"])
    return topics[:max_topics]
