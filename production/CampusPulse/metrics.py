"""
运行指标（进程内累计计数，按批次 / 按分析取差值写入统计）

计数项：llm_calls / llm_failures / llm_prompt_tokens / llm_completion_tokens /
       cache_hit:<类别> / cache_miss:<类别>
"""

import threading
from collections import Counter
from typing import Dict

_lock = threading.Lock()
_counters: Counter = Counter()


def incr(name: str, n: float = 1) -> None:
    with _lock:
        _counters[name] += n


def snapshot() -> Dict[str, float]:
    with _lock:
        return dict(_counters)


def delta(before: Dict[str, float]) -> Dict[str, float]:
    now = snapshot()
    return {k: v - before.get(k, 0) for k, v in now.items() if v - before.get(k, 0)}


def summarize_delta(d: Dict[str, float]) -> Dict:
    hits = sum(v for k, v in d.items() if k.startswith("cache_hit:"))
    misses = sum(v for k, v in d.items() if k.startswith("cache_miss:"))
    return {
        "llm_calls": int(d.get("llm_calls", 0)),
        "llm_failures": int(d.get("llm_failures", 0)),
        "llm_tokens": int(d.get("llm_prompt_tokens", 0) + d.get("llm_completion_tokens", 0)),
        "cache_hit_rate": round(hits / (hits + misses), 3) if hits + misses else None,
        "cache_hits": int(hits),
        "cache_misses": int(misses),
    }
