"""
CampusPulse 配置

复用 BettaFish 根目录 .env：LLM 默认沿用 QUERY_ENGINE_*，搜索沿用 BOCHA_*。
所有 PULSE_* 变量均为可选，用于单独覆盖。
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=False)
except Exception:  # pragma: no cover - python-dotenv 缺失时直接读环境变量
    pass


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except (TypeError, ValueError):
        return default


# 面向高校学生群体的热榜源（newsnow 聚合接口的 source id）
DEFAULT_SOURCES = [
    "weibo",
    "douyin",
    "bilibili-hot-search",
    "zhihu",
    "tieba",
    "toutiao",
    "baidu",
    "thepaper",
]


@dataclass
class PulseSettings:
    llm_api_key: Optional[str] = field(
        default_factory=lambda: _env("PULSE_LLM_API_KEY", _env("QUERY_ENGINE_API_KEY"))
    )
    llm_base_url: Optional[str] = field(
        default_factory=lambda: _env("PULSE_LLM_BASE_URL", _env("QUERY_ENGINE_BASE_URL"))
    )
    llm_model: Optional[str] = field(
        default_factory=lambda: _env("PULSE_LLM_MODEL_NAME", _env("QUERY_ENGINE_MODEL_NAME"))
    )
    llm_timeout: int = field(default_factory=lambda: _env_int("PULSE_LLM_TIMEOUT", 180))

    search_tool: str = field(default_factory=lambda: _env("SEARCH_TOOL_TYPE", "BochaAPI"))
    bocha_api_key: Optional[str] = field(default_factory=lambda: _env("BOCHA_WEB_SEARCH_API_KEY"))
    bocha_base_url: str = field(
        default_factory=lambda: _env("BOCHA_BASE_URL", "https://api.bocha.cn/v1/ai-search")
    )

    newsnow_base_url: str = field(
        default_factory=lambda: _env("PULSE_NEWSNOW_BASE_URL", "https://newsnow.busiyi.world")
    )
    sources: List[str] = field(
        default_factory=lambda: [
            s.strip() for s in _env("PULSE_SOURCES", ",".join(DEFAULT_SOURCES)).split(",") if s.strip()
        ]
    )

    db_path: Path = field(
        default_factory=lambda: Path(_env("PULSE_DB_PATH", str(PROJECT_ROOT / "data" / "campus_pulse.db")))
    )
    # 后台采集间隔（分钟），0 表示关闭后台调度，仅手动触发
    collect_interval_min: int = field(default_factory=lambda: _env_int("PULSE_COLLECT_INTERVAL_MIN", 30))
    # 狐友本校圈子 ID（逗号分隔；也可在页面“设置”中粘贴圈子链接，页面设置优先）
    huyou_circles: List[str] = field(
        default_factory=lambda: [s for s in re.findall(r"\d{12,20}", _env("PULSE_HUYOU_CIRCLES", "") or "")]
    )
    tieba_forums: List[str] = field(
        default_factory=lambda: [s for s in re.split(r"[,，\s]+", _env("PULSE_TIEBA_FORUMS", "") or "") if s]
    )
    huyou_enabled: bool = field(default_factory=lambda: _env("PULSE_HUYOU", "1") == "1")
    bilibili_enabled: bool = field(default_factory=lambda: _env("PULSE_BILIBILI", "1") == "1")
    video_analysis_enabled: bool = field(default_factory=lambda: _env("PULSE_VIDEO_ANALYSIS", "1") == "1")
    video_per_batch: int = field(default_factory=lambda: _env_int("PULSE_VIDEO_PER_BATCH", 8))
    # 编排器最多重新规划的轮数（Magentic-One 外循环上限）
    max_replans: int = field(default_factory=lambda: _env_int("PULSE_MAX_REPLANS", 2))

    @property
    def llm_ready(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)

    @property
    def search_ready(self) -> bool:
        return bool(self.bocha_api_key)


settings = PulseSettings()

def reload_settings() -> PulseSettings:
    global settings
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env", override=True)
    except Exception:
        pass
    settings = PulseSettings()
    return settings

