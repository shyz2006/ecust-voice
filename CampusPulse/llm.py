"""
OpenAI 兼容 LLM 客户端，附带 JSON 输出解析与用量统计。
"""

import json
import re
import threading
import time
from typing import Any, Dict, Optional

from loguru import logger

from . import metrics
from .config import settings

try:
    from json_repair import repair_json
except Exception:  # pragma: no cover
    repair_json = None


class LLMUnavailable(RuntimeError):
    pass


class UsageMeter:
    """统计一次编排中的 LLM 调用成本，供工作流选择器做成本惩罚。"""

    def __init__(self):
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.seconds = 0.0
        self._lock = threading.Lock()

    def add(self, usage, seconds: float) -> None:
        with self._lock:
            self.calls += 1
            self.seconds += seconds
            if usage is not None:
                self.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
                self.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "calls": self.calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "llm_seconds": round(self.seconds, 1),
        }


_client = None
_client_lock = threading.Lock()

try:  # 复用线上 BettaFish 的跨模型故障转移（LLM_FALLBACK_MODELS），不存在时直连主模型
    import sys
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parent.parent / "utils"))
    from llm_failover import ModelFailover
except Exception:  # pragma: no cover
    ModelFailover = None

_failover = None


def _get_failover():
    global _failover
    if ModelFailover is not None and _failover is None:
        _failover = ModelFailover(settings.llm_model, "PULSE")
    return _failover


def _get_client():
    global _client
    if not settings.llm_ready:
        raise LLMUnavailable("未配置 LLM（PULSE_LLM_* 或 QUERY_ENGINE_*）")
    with _client_lock:
        if _client is None:
            from openai import OpenAI

            kwargs = {"api_key": settings.llm_api_key, "max_retries": 1}
            if settings.llm_base_url:
                kwargs["base_url"] = settings.llm_base_url
            _client = OpenAI(**kwargs)
    return _client


def chat(system: str, user: str, temperature: float = 0.3,
         meter: Optional[UsageMeter] = None, retries: int = 2, max_tokens: Optional[int] = None) -> str:
    client = _get_client()
    now = time.strftime("%Y年%m月%d日 %H:%M")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"当前时间：{now}\n\n{user}"},
    ]
    last_exc = None
    truncated_once = False
    # 故障转移已在多个模型间切换；服务商常见间歇性 502，外层只再整体重试一次
    attempts = (2 if _get_failover() else retries + 1) + (1 if max_tokens else 0)
    for attempt in range(attempts):
        started = time.time()

        def request(model: str):
            kwargs = {"max_tokens": max_tokens} if max_tokens else {}
            from . import telemetry
            request_start = time.time()
            globally_tracked = getattr(client.chat.completions.create,'_bf_usage_ledger',False)
            try:
                response = client.chat.completions.create(
                    model=model, messages=messages, temperature=temperature,
                    timeout=settings.llm_timeout, **kwargs)
            except Exception:
                if not globally_tracked:
                    telemetry.record_response(None, time.time()-request_start, success=False)
                raise
            if not globally_tracked:
                telemetry.record_response(getattr(response, 'usage', None), time.time()-request_start)
            return response

        try:
            failover = _get_failover()
            resp = failover.run(request, "CampusPulse")[1] if failover else request(settings.llm_model)
            if meter is not None:
                meter.add(getattr(resp, "usage", None), time.time() - started)
            usage = getattr(resp, "usage", None)
            metrics.incr("llm_calls")
            metrics.incr("llm_prompt_tokens", getattr(usage, "prompt_tokens", 0) or 0)
            metrics.incr("llm_completion_tokens", getattr(usage, "completion_tokens", 0) or 0)
            content = (resp.choices[0].message.content or "").strip()
            if max_tokens and resp.choices[0].finish_reason == "length":
                metrics.incr("llm_truncated")
                if not content:
                    # 截断且没有任何正文：模型的隐藏推理占满了输出上限。去掉上限重试，由模型自行决定长度
                    logger.info("[CampusPulse] 输出上限被隐藏推理占满（无正文），去掉输出上限重试")
                    max_tokens = None
                    last_exc = RuntimeError("模型输出被截断且没有正文（输出上限不足）")
                    continue
                if not truncated_once:
                    # 预算不够导致截断：一次放宽到 3 倍（上限 12000）重试，避免返回残缺 JSON
                    truncated_once = True
                    max_tokens = min(max_tokens * 3, 12000)
                    logger.info(f"[CampusPulse] 输出被截断，放宽输出上限到 {max_tokens} 重试")
                    continue
                # 放宽后仍被截断：交给 parse_json 的 JSON 修复补全，而不是整次失败
                logger.warning("[CampusPulse] 放宽上限后输出仍被截断，使用已生成部分")
            return content
        except Exception as exc:  # 网络抖动 / 限流
            last_exc = exc
            metrics.incr("llm_failures")
            logger.warning(f"[CampusPulse] LLM 调用失败({attempt + 1}/{attempts}): {exc}")
            if attempt + 1 < attempts:
                time.sleep(5 * (attempt + 1))
    raise LLMUnavailable(f"LLM 调用失败: {last_exc}")


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json(text: str) -> Any:
    if not text:
        raise ValueError("空响应")
    m = _FENCE_RE.search(text)
    body = m.group(1) if m else text
    start = min([i for i in (body.find("{"), body.find("[")) if i >= 0], default=-1)
    if start > 0:
        body = body[start:]
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        if repair_json is None:
            raise
        return json.loads(repair_json(body))


def chat_json(system: str, user: str, temperature: float = 0.2,
              meter: Optional[UsageMeter] = None, max_tokens: Optional[int] = None) -> Any:
    text = chat(system + "\n\n只输出 JSON，不要输出任何解释。", user, temperature, meter, max_tokens=max_tokens)
    try:
        return parse_json(text)
    except Exception:
        # 一次自我修复：把原文交回模型要求只输出合法 JSON
        fixed = chat("你是 JSON 修复器。", f"把下面内容整理为合法 JSON，只输出 JSON：\n{text}", 0.0, meter)
        return parse_json(fixed)
