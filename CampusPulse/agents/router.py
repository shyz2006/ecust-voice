"""
拓扑路由器 —— 依据任务可测特征选择智能体拓扑

依据 Kim et al., "Towards a Science of Scaling Agent Systems" (2025) 的三条结论：
1. 单智能体基线已经够强时，多智能体协调收益递减（capability saturation）；
2. 工具密集、强顺序依赖的任务，多智能体会带来额外协调开销，甚至显著退化；
3. 没有中心化验证的拓扑更容易放大错误。
因此：可分解任务 → 中心化多智能体（Orchestrator + 专家 + 中心验证）；
      顺序依赖/单点任务 → 单智能体 + 中心验证；
      需要全网 30+ 平台深挖的舆情任务 → 移交 BettaFish 原有三引擎 + 论坛流程。
BettaFish 原流程是"固定拓扑"（每个问题都启动三个 Agent + 论坛），这是主要改进点。
"""

import re
from dataclasses import asdict, dataclass
from typing import Dict, List

INTENTS = {
    "meme_explain": "梗/流行语释义",
    "event_brief": "热点事件简报",
    "trend_scan": "学生关注趋势扫描",
    "activity_design": "心理活动策划",
    "deep_opinion": "全网深度舆情",
}

_PATTERNS = [
    ("deep_opinion", r"舆情|全网|深度分析|完整报告|研究报告|多平台|评论区.*分析"),
    ("activity_design", r"活动|策划|方案|工作坊|团辅|讲座|班会|怎么开展|如何开展|主题月|宣传"),
    ("trend_scan", r"(最近|本周|这周|今天|近期|当下).*(关注|热点|流行|在聊|在玩|火)|有哪些.*(梗|热点)|趋势|热榜"),
    ("meme_explain", r"什么梗|啥梗|梗是|什么意思|啥意思|出处|怎么火|由来|是什么$|指什么|转场"),
]

# 每类意图的可测任务特征（0~1）
_PROFILE = {
    #                 可分解度  工具强度  顺序深度
    "meme_explain":    (0.2,     0.6,     3),
    "event_brief":     (0.5,     0.6,     2),
    "trend_scan":      (0.9,     0.3,     1),
    "activity_design": (0.8,     0.4,     2),
    "deep_opinion":    (0.9,     0.9,     4),
}


@dataclass
class TaskProfile:
    intent: str
    intent_label: str
    decomposability: float
    tool_intensity: float
    sequential_depth: int
    topology: str           # SAS | Centralized | Escalate
    candidate_workflows: List[str]
    rationale: str

    def as_dict(self) -> Dict:
        return asdict(self)


def classify_intent(query: str) -> str:
    q = query.strip()
    for intent, pattern in _PATTERNS:
        if re.search(pattern, q, re.I):
            return intent
    return "event_brief"


def route(query: str, force_intent: str = None) -> TaskProfile:
    intent = force_intent if force_intent in INTENTS else classify_intent(query)
    decomp, tools, depth = _PROFILE[intent]

    if intent == "deep_opinion":
        topology = "Escalate"
        candidates = ["central_verified"]
        why = "需要覆盖 30+ 平台评论与长篇报告，交给 BettaFish 三引擎 + 论坛流程；此处先给出校园视角速览"
    elif decomp >= 0.7:
        topology = "Centralized"
        candidates = ["central", "central_verified"]
        why = f"可分解度 {decomp:.1f}：子任务可并行，采用中心化编排 + 中心验证以抑制错误传播"
    elif decomp <= 0.3 and tools >= 0.5:
        topology = "SAS"
        candidates = ["lean", "lean_verified"]
        why = f"顺序依赖强（深度 {depth}）、工具密集（{tools:.1f}）：多智能体协调开销大于收益，采用单智能体 + 中心验证"
    else:
        topology = "Adaptive"
        candidates = ["lean", "lean_verified", "central", "central_verified"]
        why = "任务特征处于中间区域，由工作流选择器依据历史得分在单/多智能体间在线选择"
    return TaskProfile(
        intent=intent,
        intent_label=INTENTS[intent],
        decomposability=decomp,
        tool_intensity=tools,
        sequential_depth=depth,
        topology=topology,
        candidate_workflows=candidates,
        rationale=why,
    )
