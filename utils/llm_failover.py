"""Cross-model failover for OpenAI-compatible LLM clients."""

from __future__ import annotations

import os
import threading
import time
from typing import Callable, Generic, List, Tuple, TypeVar

from loguru import logger


T = TypeVar("T")


def _http_status_code(exc: Exception):
    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    try:
        return int(status_code) if status_code is not None else None
    except (TypeError, ValueError):
        return None


def _float_env(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except ValueError:
        return default


_RATE_LIMIT_MARKERS = ("concurrency limit", "rate limit", "too many requests", "please retry later")


def _is_rate_limited(exc: Exception) -> bool:
    """账号级限流（与具体模型无关）：换模型没用，应原地等待后重试。"""
    return _http_status_code(exc) == 429 or any(m in str(exc).lower() for m in _RATE_LIMIT_MARKERS)


def _install_prompt_cache_key() -> None:
    """部分 OpenAI 兼容网关要求 prompt_cache_key / session_id（否则返回 400 “BPS session proxy requires…”）。
    为所有 chat.completions.create 请求自动附带；同一研究任务使用同一个键，也便于服务商侧缓存。"""
    if os.getenv("LLM_PROMPT_CACHE_KEY", "1") == "0":
        return
    try:
        from openai.resources.chat.completions import Completions
    except Exception:
        return
    if getattr(Completions.create, "_bf_cache_key", False):
        return
    original = Completions.create

    def create(self, *args, **kwargs):
        extra = dict(kwargs.get("extra_body") or {})
        if "prompt_cache_key" not in extra and "prompt_cache_key" not in kwargs:
            scope = os.getenv("BETTAFISH_TASK_ID") or f"proc-{os.getpid()}"
            extra["prompt_cache_key"] = f"bettafish-{scope}"
            kwargs["extra_body"] = extra
        return original(self, *args, **kwargs)

    create._bf_cache_key = True
    Completions.create = create


_install_prompt_cache_key()
try:
    from utils.llm_usage import install as _install_usage_ledger
except ImportError:
    from llm_usage import install as _install_usage_ledger
_install_usage_ledger()


class _LLMSlot:
    """跨进程的大模型并发闸门：所有引擎进程、报告线程、校园脉搏共享 LLM_MAX_CONCURRENCY 个名额。

    用 LLM_SLOT_DIR 下的 N 个文件锁实现（flock，进程崩溃时由内核自动释放），
    避免多个研究任务同时运行时超过服务商的并发上限而被拒绝。
    """

    def __init__(self):
        self.limit = int(os.getenv("LLM_MAX_CONCURRENCY", "10") or 0)
        root = os.getenv("LLM_SLOT_DIR") or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime", "llm_slots")
        self.dir = root
        self._fh = None

    def __enter__(self):
        if self.limit <= 0:
            return self
        try:
            import fcntl
        except ImportError:
            fcntl = None
        import random

        if fcntl is None:
            return self

        os.makedirs(self.dir, exist_ok=True)
        started = time.time()
        warned = False
        while True:
            for index in random.sample(range(self.limit), self.limit):
                fh = open(os.path.join(self.dir, f"slot{index}"), "a+")
                try:
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    fh.close()
                    continue
                self._fh = fh
                return self
            if not warned and time.time() - started > 10:
                logger.info(f"大模型并发名额（{self.limit}）已满，排队等待中…")
                warned = True
            time.sleep(0.3 + random.random() * 0.5)

    def __exit__(self, *exc):
        if self._fh is not None:
            try:
                import fcntl
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            except (ImportError, OSError):
                pass
            finally:
                self._fh.close()
                self._fh = None
        return False


_UNSUPPORTED_MARKERS = ("not supported", "unsupported_model", "model_not_found", "does not exist",
                        "no such model", "invalid model", "unknown model")


def _is_unsupported_model(exc: Exception) -> bool:
    """接口明确表示“没有这个模型”：短期内重试也不会成功。"""
    text = str(exc).lower()
    return _http_status_code(exc) in (400, 404) and any(m in text for m in _UNSUPPORTED_MARKERS)


class _ModelStats:
    """各模型最近表现（所有进程共享，存于 runtime/llm_stats.json）。

    cost = 每千字耗时（秒）的指数滑动平均；失败率单独做滑动平均。
    排序估计值 = cost × (1 + 4 × 失败率)；没有数据或数据超过 LLM_STATS_STALE 秒的模型
    按比当前最快者略快来估计（先试一次），并以 LLM_EXPLORE_RATE 的概率被随机提前试用，保证数据持续更新。
    """

    ALPHA = 0.3

    def __init__(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.path = os.getenv("LLM_STATS_FILE") or os.path.join(root, "runtime", "llm_stats.json")
        self.stale = _float_env("LLM_STATS_STALE", 1800.0)
        self.explore = _float_env("LLM_EXPLORE_RATE", 0.1)

    def _locked(self, mutate=None):
        try:
            import fcntl
        except ImportError:
            fcntl = None
        import json

        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        if fcntl is None:
            try:
                with open(self.path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                data = {}
            if mutate is None:
                return data
            mutate(data)
            tmp = f"{self.path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
            return data

        with open(self.path + ".lock", "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with open(self.path, encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, ValueError):
                data = {}
            if mutate is None:
                return data
            mutate(data)
            tmp = f"{self.path}.{os.getpid()}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
            return data

    @staticmethod
    def _size(result) -> int:
        if isinstance(result, str):
            return len(result)
        if isinstance(result, (list, tuple)):
            return sum(len(x) for x in result if isinstance(x, str))
        try:
            return len(result.choices[0].message.content or "")
        except Exception:
            return 0

    def record(self, model: str, elapsed: float, result=None, ok: bool = True, unsupported: bool = False) -> None:
        cost = elapsed * 1000.0 / max(self._size(result), 300) if ok else None

        def mutate(data):
            row = data.setdefault(model, {"cost": None, "fail": 0.0, "n": 0})
            if unsupported:
                row["unsupported_until"] = time.time() + 6 * 3600
            if cost is not None:
                row.pop("unsupported_until", None)
                row["cost"] = cost if row.get("cost") is None else (1 - self.ALPHA) * row["cost"] + self.ALPHA * cost
            row["fail"] = (1 - self.ALPHA) * row.get("fail", 0.0) + self.ALPHA * (0.0 if ok else 1.0)
            row["n"] = row.get("n", 0) + 1
            row["ts"] = time.time()

        try:
            self._locked(mutate)
        except Exception as exc:  # 统计失败不影响调用
            logger.debug(f"模型速度统计写入失败: {exc}")

    def order(self, models: List[str]) -> List[str]:
        import random

        try:
            data = self._locked()
        except Exception:
            return models
        now = time.time()
        blocked = {m for m, r in data.items() if m in models and r.get("unsupported_until", 0) > now}
        usable = [m for m in models if m not in blocked] or models
        fresh = {m: r for m, r in data.items()
                 if m in usable and now - r.get("ts", 0) <= self.stale and r.get("cost") is not None}
        if not fresh:
            return usable
        costs = sorted(r["cost"] * (1 + 4 * r.get("fail", 0.0)) for r in fresh.values())
        optimistic = costs[0] * 0.9  # 没有近期数据的模型：乐观估计，先试一次再按真实速度排序

        failing = {m for m, r in data.items() if m in usable and r.get("cost") is None and r.get("fail", 0) > 0.5}

        def score(m):
            if m in failing:  # 只失败过、从未成功的模型排到最后
                return float("inf")
            r = fresh.get(m)
            return r["cost"] * (1 + 4 * r.get("fail", 0.0)) if r else optimistic

        ranked = sorted(usable, key=score)
        if len(ranked) > 1 and random.random() < self.explore:
            pick = random.choice(ranked[1:])  # 偶尔先试其他模型，保持速度数据新鲜
            ranked.remove(pick)
            ranked.insert(0, pick)
        return ranked


_MODEL_STATS = _ModelStats()


def _extra_pool() -> List[str]:
    """runtime/llm_models.json 中的 {"pool": [...]}：无需重启即可加入候选模型。"""
    import json

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        with open(os.path.join(root, "runtime", "llm_models.json"), encoding="utf-8") as fh:
            return [str(m).strip() for m in json.load(fh).get("pool", []) if str(m).strip()]
    except (OSError, ValueError, AttributeError):
        return []


class ModelFailover(Generic[T]):
    """Try configured models in order and cool down transiently failing routes."""

    _lock = threading.Lock()
    _cooldowns = {}

    def __init__(self, primary_model: str, scope: str):
        self.primary_model = primary_model
        self.scope = scope.upper()
        raw_fallbacks = (
            os.getenv(f"{self.scope}_FALLBACK_MODELS")
            or os.getenv("LLM_FALLBACK_MODELS")
            or ""
        )
        models = [primary_model]
        models.extend(item.strip() for item in raw_fallbacks.split(","))
        models.extend(_extra_pool())
        self.models = list(dict.fromkeys(item for item in models if item))
        self.cooldown_seconds = _float_env("LLM_MODEL_COOLDOWN_SECONDS", 300.0)
        self.active_model = primary_model

    def _cooldown_key(self, model: str) -> Tuple[str, str]:
        return self.scope, model

    def _ordered_models(self) -> List[str]:
        now = time.monotonic()
        with self._lock:
            ready = [
                model
                for model in self.models
                if self._cooldowns.get(self._cooldown_key(model), 0.0) <= now
            ]
            if ready:
                if os.getenv("LLM_ADAPTIVE_ROUTING", "1") != "0":
                    return _MODEL_STATS.order(ready)
                return ready
            # If every route is cooling down, retry the one whose cooldown expires first.
            return sorted(
                self.models,
                key=lambda model: self._cooldowns.get(self._cooldown_key(model), 0.0),
            )

    @staticmethod
    def _can_failover(exc: Exception) -> bool:
        # Authentication/permission errors use the same credential for every model.
        # Rotating models cannot repair them and may hide a configuration problem.
        return _http_status_code(exc) not in {401, 403}

    def _mark_failure(self, model: str) -> None:
        with self._lock:
            self._cooldowns[self._cooldown_key(model)] = (
                time.monotonic() + self.cooldown_seconds
            )

    def _mark_success(self, model: str) -> None:
        with self._lock:
            self._cooldowns.pop(self._cooldown_key(model), None)
        self.active_model = model

    def run(self, operation: Callable[[str], T], operation_name: str) -> Tuple[str, T]:
        """依次尝试候选模型；账号级限流时原地等待重试同一模型；
        所有模型都失败（如接口 502 / 超时）时按退避间隔整体重试，最长等待 LLM_OUTAGE_MAX_WAIT 秒。"""
        import random

        max_wait = _float_env("LLM_OUTAGE_MAX_WAIT", 900.0)
        started = time.monotonic()
        round_index = 0
        last_exception = None
        while True:
            candidates = self._ordered_models()
            for index, model in enumerate(candidates):
                rate_retries = 0
                while True:
                    try:
                        with _LLMSlot():
                            t0 = time.monotonic()
                            result = operation(model)
                            _MODEL_STATS.record(model, time.monotonic() - t0, result, ok=True)
                        self._mark_success(model)
                        if model != self.primary_model:
                            logger.info(f"{self.scope} {operation_name} 使用模型 {model}（按实时速度选择）")
                        return model, result
                    except Exception as exc:
                        last_exception = exc
                        if not self._can_failover(exc):
                            raise
                        if not _is_rate_limited(exc):
                            _MODEL_STATS.record(model, 0.0, None, ok=False, unsupported=_is_unsupported_model(exc))
                        if _is_rate_limited(exc) and rate_retries < 6 and time.monotonic() - started < max_wait:
                            rate_retries += 1
                            delay = min(60.0, 5.0 * 2 ** min(rate_retries - 1, 4)) * (0.7 + 0.6 * random.random())
                            logger.warning(f"{self.scope} 服务商并发限流，{delay:.0f} 秒后重试 {model}（第 {rate_retries} 次）")
                            time.sleep(delay)
                            continue
                        break
                if not _is_rate_limited(last_exception):
                    self._mark_failure(model)
                next_model = candidates[index + 1] if index + 1 < len(candidates) else None
                if next_model:
                    logger.warning(
                        f"{self.scope} 模型 {model} 调用失败，立即切换至 {next_model}: {last_exception}"
                    )
            elapsed = time.monotonic() - started
            if elapsed >= max_wait:
                logger.error(f"{self.scope} 所有候选模型持续失败 {elapsed:.0f} 秒，放弃：{last_exception}")
                break
            round_index += 1
            delay = min(240.0, 30.0 * 2 ** min(round_index - 1, 4), max_wait - elapsed)
            logger.warning(
                f"{self.scope} 所有候选模型均调用失败（接口可能暂时不可用），{delay:.0f} 秒后整体重试"
                f"（已等待 {elapsed:.0f}/{max_wait:.0f} 秒）：{last_exception}"
            )
            time.sleep(delay)
            with self._lock:  # 整体重试前清除冷却，让主模型重新参与
                for model in self.models:
                    self._cooldowns.pop(self._cooldown_key(model), None)

        if last_exception is not None:
            raise last_exception
        raise RuntimeError(f"{self.scope} 没有可用的模型候选")

    def info(self):
        return {
            "primary_model": self.primary_model,
            "active_model": self.active_model,
            "fallback_models": self.models[1:],
        }
