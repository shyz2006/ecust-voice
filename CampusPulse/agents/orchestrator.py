"""
编排器 —— Magentic-One 式双账本循环

Fourney et al., "Magentic-One" (2024)：Orchestrator 维护
  - 任务账本 Task Ledger（已知事实 / 待查事实 / 待推导 / 合理猜测 / 计划）——外循环
  - 进度账本 Progress Ledger（是否完成、是否空转、是否有进展、下一步交给谁）——内循环
发现停滞时更新任务账本并重新规划。

本实现的流程：
  路由（按任务特征选拓扑）→ 选择工作流变体（UCB）→ 建立任务账本
  → 工具型工作者并行取证 → 推理型工作者（单智能体或并行专家）
  → 中心验证 → 未通过则把问题写回任务账本、补充检索并修订（有上限，停滞即停）
每一步都写入 trace，前端可视化，便于老师理解结论从何而来。
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

from loguru import logger

from .. import lens, llm, storage
from ..config import settings
from . import router, schema, verifier, workflows, workers
from . import analysis_options as selection


# 各类任务的单次生成 token 上限：简单任务不需要长篇输出
TOKEN_BUDGET = {"meme_explain": 1800, "event_brief": 2200, "activity_design": 3200,
                "trend_scan": 3600, "deep_opinion": 3200}


class Orchestrator:
    def __init__(self, on_event: Optional[Callable[[Dict], None]] = None):
        self.on_event = on_event or (lambda e: None)
        self.trace: List[Dict] = []
        self.meter = llm.UsageMeter()

    # ---------------------------------------------------------- 进度账本
    def _step(self, agent: str, action: str, **info) -> Dict:
        step = {"t": round(time.time() - self._t0, 2), "agent": agent, "action": action, **info}
        self.trace.append(step)
        self.on_event(step)
        return step

    def run(self, query: str, force_intent: str = None, force_workflow: str = None, analysis_options: Dict = None) -> Dict:
        self._t0 = time.time()
        self.options = selection.normalize(analysis_options)
        if not settings.llm_ready:
            raise llm.LLMUnavailable("未配置 LLM，无法进行深度分析（热点雷达仍可使用）")
        profile = router.route(query, force_intent)
        self.budget = TOKEN_BUDGET.get(profile.intent, 3000)
        effort = self.options.get('thinking_effort')
        if effort:
            selected = selection.EFFORTS[effort]
            wf, pick_reason = workflows.WORKFLOWS[selected['workflow']], '输入栏指定思考程度：' + selected['label']
            self.budget = selection.budget(self.budget, effort)
            profile.topology = 'SAS' if wf.reasoning == 'single' else 'Centralized'
            profile.rationale = pick_reason
            self._step('Thinking', '应用思考程度', effort=effort, label=selected['label'],
                       workflow=wf.id, output_token_limit=self.budget)
        elif force_workflow in workflows.WORKFLOWS:
            wf, pick_reason = workflows.WORKFLOWS[force_workflow], "手动指定"
        else:
            pick = workflows.select(profile.candidate_workflows)
            wf, pick_reason = pick["workflow"], pick["reason"]
        self._step("Router", "选择拓扑", topology=profile.topology, intent=profile.intent_label,
                   note=profile.rationale)
        self._step("WorkflowSelector", "选择工作流", workflow=wf.name, note=pick_reason)

        pool = workers.EvidencePool()
        seen_queries: set = set()
        p = profile.as_dict()
        p['analysis_options'] = self.options

        # ---- 外循环第 0 轮：取证 + 任务账本
        if wf.memory:
            info = workers.meme_memory(query, pool)
            self._step("MemeMemory", "检索梗词典", **info)
        info = workers.trend_scout(query, profile.intent, [], pool)
        self._step("TrendScout", "检索本地热榜", **info)

        ledger: Dict = {}
        if wf.planning == "ledger":
            try:
                ledger = workers.planner(query, p, pool, self.meter)
                self._step("Orchestrator", "建立任务账本", ledger=ledger)
            except Exception as exc:
                self._step("Orchestrator", "任务账本失败，退化为默认计划", note=str(exc))
        queries = ledger.get("search_queries") or workers.default_queries(query, profile.intent)
        if ledger.get("keywords"):
            info = workers.trend_scout(query, profile.intent, ledger["keywords"], pool)
            self._step("TrendScout", "按账本关键词补充检索", **info)
        info = workers.web_researcher(queries, pool, seen_queries)
        self._step("WebResearcher", "博查检索", **info)

        # ---- 推理
        try:
            draft = schema.normalize_output(self._reason(query, p, wf, ledger, pool))
        except llm.LLMUnavailable as exc:
            # 优雅降级：模型服务不可用时，已检索到的证据仍然交给老师，且不计入工作流奖励
            self._step("Orchestrator", "模型服务不可用，返回检索证据", note=str(exc)[:160])
            return self._finish(query, profile, wf, pick_reason, ledger, pool, degraded_draft(pool),
                                verdict=None, degraded=True)

        # ---- 中心验证 + 修订（外循环）
        verdict = verifier.verify(query, profile.intent, draft, pool, self.trace,
                                  use_judge=wf.verification == "rule+judge", meter=self.meter)
        self._step("Verifier", "中心验证", score=verdict["score"], passed=verdict["passed"],
                   issues=verdict["issues"][:6])
        rounds = 0
        while not verdict["passed"] and rounds < min(wf.reflection, settings.max_replans):
            rounds += 1
            ledger.setdefault("facts_to_lookup", [])
            ledger["verifier_issues"] = verdict["issues"]
            if any("证据" in i for i in verdict["issues"]):
                extra = [f"{query} {kw}" for kw in ("最新", "网友评论")]
                info = workers.web_researcher(extra, pool, seen_queries)
                self._step("WebResearcher", f"第{rounds}轮补充检索", **info)
            try:
                revised = workers.reviser(query, draft, verdict["issues"], pool, self.meter, self.budget, profile=p)
            except Exception as exc:
                self._step("Reviser", "修订失败", note=str(exc))
                break
            revised = schema.normalize_output(revised)
            new_verdict = verifier.verify(query, profile.intent, revised, pool, self.trace,
                                          use_judge=wf.verification == "rule+judge", meter=self.meter)
            self._step("Verifier", f"第{rounds}轮复核", score=new_verdict["score"],
                       passed=new_verdict["passed"], issues=new_verdict["issues"][:6])
            if new_verdict["score"] <= verdict["score"]:
                # 进度账本：没有进展 → 保留较好的版本并停止，避免空转（MAST FM-1.5）
                self._step("Orchestrator", "检测到停滞，停止修订", note="复核分数未提升")
                break
            draft, verdict = revised, new_verdict

        return self._finish(query, profile, wf, pick_reason, ledger, pool, draft, verdict)

    def _finish(self, query, profile, wf, pick_reason, ledger, pool, draft, verdict, degraded=False) -> Dict:
        p = profile.as_dict()
        p['analysis_options'] = self.options
        usage = self.meter.as_dict()
        total_tokens = usage["prompt_tokens"] + usage["completion_tokens"]
        verdict = verdict or {"score": None, "passed": False, "checks": [], "judge": None,
                              "issues": ["模型服务不可用，未生成分析，本次不参与工作流评分"]}
        # 验证是安全门而不是提示：只有通过中心验证的结果才成为正式结果、写入梗词典、参与工作流奖励；
        # 未通过的只保存为“待人工复核草稿”，老师复核通过后才转为正式（不回补奖励）。
        if degraded:
            status = "degraded"
        elif verdict.get("passed"):
            status = "formal"
        else:
            status = "draft"
        reward = workflows.reward(verdict["score"], total_tokens) if status == "formal" else None
        if not degraded:
            lens.normalize_result(draft)  # 标签归一到标准分类，原文保留在 *_detail
        if status == "formal":
            workers.remember_memes(draft)
        self._step("Orchestrator", {"formal": "通过中心验证，发布为正式结果",
                                    "draft": "未通过中心验证，保存为待人工复核草稿",
                                    "degraded": "模型不可用，仅保留检索资料"}[status],
                   note="；".join(verdict.get("hard_fail_reasons") or []) or None)
        payload = {
            "profile": p,
            "analysis_options": self.options,
            "workflow": wf.as_dict(),
            "workflow_reason": pick_reason,
            "ledger": ledger,
            "result": draft,
            "verdict": verdict,
            "evidence": pool.as_list(),
            "trace": self.trace,
            "usage": {**usage, "total_tokens": total_tokens, "wall_seconds": round(time.time() - self._t0, 1)},
            "reward": reward,
            "escalate": profile.topology == "Escalate",
            "degraded": degraded,
            "status": status,
        }
        analysis_id = storage.save_analysis(query, wf.id, profile.topology, payload, reward, status)
        payload["id"] = analysis_id
        logger.info(f"[CampusPulse] 分析完成 #{analysis_id} wf={wf.id} score={verdict['score']} "
                    f"reward={reward} status={status}")
        return payload

    def _reason(self, query: str, p: Dict, wf, ledger: Dict, pool) -> Dict:
        if wf.reasoning == "single":
            draft = workers.solo_writer(query, p, ledger, pool, self.meter, max_tokens=self.budget)
            self._step("SoloWriter", "单智能体撰写")
            return draft if isinstance(draft, dict) else {}

        # 中心化多智能体：先把证据压成共享事实包，再让解读 & 心理透镜并行，活动策划依赖二者结果
        if len(pool.render()) > 4000:
            try:
                pool.fact_pack = workers.fact_pack(query, pool, self.meter) or None
                self._step("Orchestrator", "生成共享事实包", note=f"{len((pool.fact_pack or '').splitlines())} 条事实")
            except Exception as exc:
                self._step("Orchestrator", "事实包失败，专家使用原始证据", note=str(exc)[:80])
        half = max(1200, self.budget // 2)
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_interp = ex.submit(workers.interpreter, query, p, pool, self.meter, half)
            f_psych = ex.submit(workers.psych_lens, query, p, pool, self.meter, half)
            interp, interp_err = _safe(f_interp)
            psych, _ = _safe(f_psych)
        if not (interp.get("topics") or interp.get("summary")):
            # 解读是后续所有专家的基础；它失败时整体降级，而不是交给验证器和修订者空转
            raise llm.LLMUnavailable(f"解读专家未返回结果: {interp_err}")
        self._step("Interpreter", "热点/梗解读", topics=len(interp.get("topics") or []))
        self._step("PsychLens", "心理透镜分析", tone=str(psych.get("emotional_tone", ""))[:40])
        draft = _merge(interp, psych)
        try:
            acts = workers.activity_designer(query, p, draft, pool, self.meter, self.budget)
            draft["activities"] = (acts or {}).get("activities") or []
        except Exception as exc:
            draft["activities"] = []
            self._step("ActivityDesigner", "失败", note=str(exc))
        self._step("ActivityDesigner", "活动策划", activities=len(draft["activities"]))
        return draft


def _safe(future):
    try:
        out = future.result()
        return (out if isinstance(out, dict) else {}), None
    except Exception as exc:
        logger.warning(f"[CampusPulse] 专家执行失败: {exc}")
        return {}, exc


def degraded_draft(pool) -> Dict:
    """模型不可用时的降级输出：只列证据，不做任何推断。"""
    items = pool.as_list()
    return {
        "summary": (f"模型服务暂时不可用，未能生成分析。已检索到 {len(items)} 条资料，列在下方证据池中，"
                    "可先人工浏览，稍后重试。") if items else "模型服务暂时不可用，且未检索到资料，请稍后重试。",
        "topics": [],
        "activities": [],
        "risk_notes": [],
        "talking_points": [],
    }


def _merge(interp: Dict, psych: Dict) -> Dict:
    """确定性汇总：不额外调用 LLM，按话题名把心理透镜结果并入解读结果。"""
    per_topic = {str(t.get("name", "")).strip(): t for t in psych.get("per_topic") or []}
    topics = []
    for t in interp.get("topics") or []:
        name = str(t.get("name", "")).strip()
        match = per_topic.get(name) or next(
            (v for k, v in per_topic.items() if k and (k in name or name in k)), {})
        topics.append({**t, "psych_dimensions": match.get("psych_dimensions", []),
                       "crisis_level": match.get("crisis_level", "无"),
                       "content_risk": match.get("content_risk", "无")})
    return {
        "summary": interp.get("summary", ""),
        "topics": topics,
        "emotional_tone": psych.get("emotional_tone", ""),
        "risk_notes": psych.get("risk_notes") or [],
        "talking_points": psych.get("talking_points") or [],
    }
