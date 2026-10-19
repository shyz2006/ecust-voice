"""
CampusPulse（校园脉搏）—— 面向高校心理中心的热点 / 梗文化感知与活动策划模块

在 BettaFish 之上新增的两层架构：
1. 感知层（pipeline）：热榜采集 → TopicSketch 式加速度草图 → BERTopic 式跨平台聚类
   → 校园心理透镜标注。常驻运行、零/低 LLM 成本。
2. 推理层（agents）：按任务特征路由拓扑（单智能体 / 中心化多智能体 / 移交 BettaFish 全流程）
   → Magentic-One 式双账本编排 → MAST 中心验证 → 基于反馈的在线工作流选择。
"""

from .blueprint import init_campus_pulse, pulse_bp

__all__ = ["init_campus_pulse", "pulse_bp"]
