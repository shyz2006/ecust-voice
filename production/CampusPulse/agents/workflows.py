"""
工作流设计空间与在线选择

- AgentSquare (Shang et al., 2024) 把智能体拆成 规划 / 推理 / 工具 / 记忆 四类模块，
  在模块组合空间里搜索最优设计；
- AFlow (Zhang et al., 2024) / GPTSwarm (Zhuge et al., 2024) 用执行反馈迭代优化
  工作流图（节点=LLM 调用，边=信息流）。

它们都是离线在 benchmark 上搜索。心理中心场景没有标准答案集，因此改为"在线"版本：
每个工作流变体是一组模块选择，路由器先按任务特征圈定候选，再用 UCB1 在候选中选择，
奖励 = 中心验证器的自动评分 + 老师的人工评分 - 成本惩罚。随使用积累，系统会自己
收敛到"又好又省"的工作流。
"""

import math
import random
from dataclasses import asdict, dataclass
from typing import Dict, List

from .. import storage


@dataclass(frozen=True)
class Workflow:
    id: str
    name: str
    planning: str        # none | ledger（Magentic-One 任务账本）
    reasoning: str       # single（单智能体写作）| specialists（并行专家 + 汇总）
    verification: str    # rule | rule+judge
    reflection: int      # 验证未通过时的最多修订轮数
    memory: bool = True  # 是否复用梗词典记忆

    def as_dict(self) -> Dict:
        return asdict(self)


WORKFLOWS: Dict[str, Workflow] = {
    w.id: w
    for w in [
        Workflow("lean", "单智能体·精简", "none", "single", "rule", 0),
        Workflow("lean_verified", "单智能体·中心验证", "ledger", "single", "rule+judge", 1),
        Workflow("central", "中心化多智能体", "ledger", "specialists", "rule", 0),
        Workflow("central_verified", "中心化多智能体·中心验证", "ledger", "specialists", "rule+judge", 1),
    ]
}

# 成本惩罚：每 1 万 token 扣 0.03 分
COST_PER_10K_TOKENS = 0.03


def _reward_table() -> Dict[str, Dict]:
    table = {}
    for row in storage.workflow_rewards():
        auto = row["auto_mean"] if row["auto_mean"] is not None else 0.5
        if row["human_mean"] is not None:
            human = (row["human_mean"] - 1) / 4  # 1~5 星 → 0~1
            weight = min(0.6, 0.15 * row["n_human"])  # 人工评分越多，权重越高
            mean = (1 - weight) * auto + weight * human
        else:
            mean = auto
        table[row["workflow_id"]] = {"n": row["n"], "mean": mean}
    return table


def select(candidates: List[str], explore: float = 0.6) -> Dict:
    """UCB1：未试过的优先；否则 mean + c*sqrt(ln N / n)。"""
    candidates = [c for c in candidates if c in WORKFLOWS] or ["central_verified"]
    table = _reward_table()
    untried = [c for c in candidates if table.get(c, {}).get("n", 0) == 0]
    if untried:
        chosen = random.choice(untried)
        return {"workflow": WORKFLOWS[chosen], "reason": "冷启动探索（该变体尚无历史记录）", "scores": {}}
    total = sum(table[c]["n"] for c in candidates)
    scores = {
        c: table[c]["mean"] + explore * math.sqrt(math.log(total) / table[c]["n"]) for c in candidates
    }
    chosen = max(scores, key=scores.get)
    return {
        "workflow": WORKFLOWS[chosen],
        "reason": f"UCB1 选择（历史均分 {table[chosen]['mean']:.2f}，n={table[chosen]['n']}）",
        "scores": {k: round(v, 3) for k, v in scores.items()},
    }


def reward(auto_score: float, total_tokens: int) -> float:
    return max(0.0, auto_score - COST_PER_10K_TOKENS * total_tokens / 10000)


def leaderboard() -> List[Dict]:
    table = _reward_table()
    out = []
    for wid, wf in WORKFLOWS.items():
        stats = table.get(wid, {"n": 0, "mean": None})
        out.append({**wf.as_dict(), "runs": stats["n"],
                    "mean_reward": round(stats["mean"], 3) if stats["mean"] is not None else None})
    return out
