"""Run a research engine independently from a Streamlit browser session.

任务模式（--task-id/--token，由 utils.research_runner 启动）：研究在服务器后台进程中完成，
日志写入该 task 的日志文件、产物写入 task 输出目录，结束时释放运行锁；
三个引擎都完成后，最后完成的 worker 在服务器端触发最终报告生成。
浏览器关闭、刷新或断网都不会影响研究。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings  # noqa: E402


STATUS_DIR = PROJECT_ROOT / "logs"


def _status_path(engine: str) -> Path:
    return STATUS_DIR / f"research_{engine}_status.json"


def write_status(engine: str, **values) -> None:
    """Atomically publish worker state for the Flask UI and diagnostics."""
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    path = _status_path(engine)
    previous = {}
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        pass

    previous.update(values)
    previous["engine"] = engine
    previous["pid"] = os.getpid()
    previous["updated_at"] = datetime.now(timezone.utc).isoformat()

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=str(STATUS_DIR), text=True
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(previous, handle, ensure_ascii=False, indent=2)
        os.chmod(temporary_name, 0o664)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def build_agent(engine: str, task_id: str | None = None):
    """Build the requested agent from the same settings used by Streamlit."""
    def out_dir(default: str) -> str:
        if task_id:
            from utils.task_runtime import task_output_dir

            return str(task_output_dir(task_id, engine))
        return default

    if engine == "query":
        from QueryEngine import DeepSearchAgent, Settings

        if not settings.QUERY_ENGINE_API_KEY:
            raise RuntimeError("QUERY_ENGINE_API_KEY 未配置")
        if settings.SEARCH_TOOL_TYPE == "BochaAPI":
            if not settings.BOCHA_WEB_SEARCH_API_KEY:
                raise RuntimeError("BOCHA_WEB_SEARCH_API_KEY 未配置")
        elif settings.SEARCH_TOOL_TYPE == "TavilyAPI":
            if not settings.TAVILY_API_KEY:
                raise RuntimeError("TAVILY_API_KEY 未配置")
        else:
            raise RuntimeError(f"Query Agent 不支持搜索工具: {settings.SEARCH_TOOL_TYPE}")
        config = Settings(
            QUERY_ENGINE_API_KEY=settings.QUERY_ENGINE_API_KEY,
            QUERY_ENGINE_BASE_URL=settings.QUERY_ENGINE_BASE_URL,
            QUERY_ENGINE_MODEL_NAME=settings.QUERY_ENGINE_MODEL_NAME or "deepseek-chat",
            SEARCH_TOOL_TYPE=settings.SEARCH_TOOL_TYPE,
            TAVILY_API_KEY=settings.TAVILY_API_KEY,
            BOCHA_BASE_URL=settings.BOCHA_BASE_URL,
            BOCHA_WEB_SEARCH_API_KEY=settings.BOCHA_WEB_SEARCH_API_KEY,
            MAX_REFLECTIONS=2,
            SEARCH_CONTENT_MAX_LENGTH=20000,
            OUTPUT_DIR=out_dir("query_engine_streamlit_reports"),
        )
        return DeepSearchAgent(config, task_id=task_id)

    if engine == "insight":
        from InsightEngine import DeepSearchAgent, Settings

        if not settings.INSIGHT_ENGINE_API_KEY:
            raise RuntimeError("INSIGHT_ENGINE_API_KEY 未配置")
        config = Settings(
            INSIGHT_ENGINE_API_KEY=settings.INSIGHT_ENGINE_API_KEY,
            INSIGHT_ENGINE_BASE_URL=settings.INSIGHT_ENGINE_BASE_URL,
            INSIGHT_ENGINE_MODEL_NAME=(
                settings.INSIGHT_ENGINE_MODEL_NAME or "kimi-k2-0711-preview"
            ),
            DB_HOST=settings.DB_HOST,
            DB_USER=settings.DB_USER,
            DB_PASSWORD=settings.DB_PASSWORD,
            DB_NAME=settings.DB_NAME,
            DB_PORT=settings.DB_PORT,
            DB_CHARSET=settings.DB_CHARSET,
            DB_DIALECT=settings.DB_DIALECT,
            MAX_REFLECTIONS=2,
            MAX_CONTENT_LENGTH=500000,
            OUTPUT_DIR=out_dir("insight_engine_streamlit_reports"),
        )
        return DeepSearchAgent(config, task_id=task_id)

    if engine == "media":
        from MediaEngine import AnspireSearchAgent, DeepSearchAgent, Settings

        if not settings.MEDIA_ENGINE_API_KEY:
            raise RuntimeError("MEDIA_ENGINE_API_KEY 未配置")
        common = dict(
            MEDIA_ENGINE_API_KEY=settings.MEDIA_ENGINE_API_KEY,
            MEDIA_ENGINE_BASE_URL=settings.MEDIA_ENGINE_BASE_URL,
            MEDIA_ENGINE_MODEL_NAME=settings.MEDIA_ENGINE_MODEL_NAME or "gemini-2.5-pro",
            SEARCH_TOOL_TYPE=settings.SEARCH_TOOL_TYPE,
            MAX_REFLECTIONS=2,
            SEARCH_CONTENT_MAX_LENGTH=20000,
            OUTPUT_DIR=out_dir("media_engine_streamlit_reports"),
        )
        if settings.SEARCH_TOOL_TYPE == "BochaAPI":
            if not settings.BOCHA_WEB_SEARCH_API_KEY:
                raise RuntimeError("BOCHA_WEB_SEARCH_API_KEY 未配置")
            config = Settings(
                **common,
                BOCHA_WEB_SEARCH_API_KEY=settings.BOCHA_WEB_SEARCH_API_KEY,
            )
            return DeepSearchAgent(config, task_id=task_id)
        if settings.SEARCH_TOOL_TYPE == "AnspireAPI":
            if not settings.ANSPIRE_API_KEY:
                raise RuntimeError("ANSPIRE_API_KEY 未配置")
            config = Settings(**common, ANSPIRE_API_KEY=settings.ANSPIRE_API_KEY)
            return AnspireSearchAgent(config, task_id=task_id)
        raise RuntimeError(f"未知的搜索工具类型: {settings.SEARCH_TOOL_TYPE}")

    raise ValueError(f"未知研究引擎: {engine}")


def run(engine: str, query: str) -> None:
    write_status(
        engine,
        status="running",
        query=query,
        stage="initializing",
        current_paragraph=0,
        total_paragraphs=0,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=None,
        error=None,
    )
    logger.info(f"后台研究任务启动: engine={engine}, query={query}")

    try:
        agent = build_agent(engine)
        write_status(engine, stage="generating_structure")
        agent._generate_report_structure(query)

        total = len(agent.state.paragraphs)
        write_status(engine, stage="researching", total_paragraphs=total)
        for index, paragraph in enumerate(agent.state.paragraphs):
            write_status(
                engine,
                stage="initial_search",
                current_paragraph=index + 1,
                paragraph_title=paragraph.title,
            )
            agent._initial_search_and_summary(index)
            write_status(engine, stage="reflection")
            agent._reflection_loop(index)
            paragraph.research.mark_completed()
            write_status(engine, stage="paragraph_completed")

        write_status(engine, stage="generating_report")
        final_report = agent._generate_final_report()
        write_status(engine, stage="saving_report")
        agent._save_report(final_report)
        write_status(
            engine,
            status="completed",
            stage="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info(f"后台研究任务完成: engine={engine}, query={query}")
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            state = "cancelled"
        else:
            state = "failed"
        write_status(
            engine,
            status=state,
            stage=state,
            error=str(exc),
            traceback=traceback.format_exc(),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.exception(f"后台研究任务失败: engine={engine}, query={query}: {exc}")
        raise


def _warm_up_insight(agent) -> None:
    """并行前预先加载 Insight 的情感 / 聚类模型，避免多个线程同时初始化。"""
    try:
        analyzer = agent.sentiment_analyzer
        if not analyzer.is_initialized and not analyzer.is_disabled:
            analyzer.initialize()
    except Exception as exc:
        logger.warning(f"[后台研究] 情感模型预加载失败（将按原逻辑处理）：{exc}")
    try:
        import InsightEngine.agent as insight_module

        if getattr(insight_module, "ENABLE_CLUSTERING", False):
            agent._get_clustering_model()
    except Exception as exc:
        logger.warning(f"[后台研究] 聚类模型预加载失败：{exc}")


def _run_paragraphs_parallel(agent, engine: str) -> None:
    """各段落互不依赖：并行执行“首次搜索+总结→反思循环”（RESEARCH_PARAGRAPH_CONCURRENCY，默认 5）。"""
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    paragraphs = list(agent.state.paragraphs)
    total = len(paragraphs)
    workers = max(1, min(total or 1, int(os.getenv("RESEARCH_PARAGRAPH_CONCURRENCY", "5") or 5)))
    if engine == "insight" and workers > 1:
        _warm_up_insight(agent)

    def one(index, paragraph):
        logger.info(f"[后台研究] 段落 {index + 1}/{total}：{paragraph.title}")
        agent._initial_search_and_summary(index)
        agent._reflection_loop(index)
        paragraph.research.mark_completed()
        logger.info(f"[后台研究] 段落 {index + 1}/{total} 完成")

    logger.info(f"[后台研究] {total} 个段落并行处理，并发数 {workers}")
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"{engine}-para") as pool:
        futures = [pool.submit(contextvars.copy_context().run, one, i, para) for i, para in enumerate(paragraphs)]
        errors = []
        for future in futures:
            try:
                future.result()
            except Exception as exc:
                errors.append(exc)
    if errors:
        raise errors[0]


def run_task(engine: str, query: str, task_id: str, token: str) -> None:
    """任务模式：在 task 日志上下文中运行，结束时按 token 释放运行锁并按需触发报告。"""
    import signal

    from utils.task_runtime import finish_engine_run, task_log_context

    # 容器停止 / 手动终止时也要把运行锁释放为“失败”，而不是永远停在“运行中”
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    os.environ["BETTAFISH_TASK_ID"] = task_id  # 检索网关按研究任务统计 / 限制博查调用
    success = False
    try:
        with task_log_context(task_id, engine):
            logger.info(f"[后台研究] {engine} 在服务器后台开始运行（浏览器关闭不影响）：{query}")
            agent = build_agent(engine, task_id)
            agent._generate_report_structure(query)
            _run_paragraphs_parallel(agent, engine)
            final_report = agent._generate_final_report()
            agent._save_report(final_report)
            success = True
            logger.info(f"[后台研究] {engine} 完成")
    except BaseException as exc:
        with task_log_context(task_id, engine):
            logger.exception(f"[后台研究] {engine} 失败：{exc}")
    finally:
        finish_engine_run(task_id, engine, token, success=success)
    if success:
        from utils.research_runner import maybe_trigger_report

        with task_log_context(task_id, engine):
            outcome = maybe_trigger_report(task_id, query)
            if outcome in ("triggered", "running"):
                logger.info("[后台研究] 三个引擎均已完成，已在服务器端启动最终报告生成")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("engine", choices=("insight", "media", "query"))
    parser.add_argument("--query", required=True)
    parser.add_argument("--task-id")
    parser.add_argument("--token")
    args = parser.parse_args()
    if args.task_id and args.token:
        run_task(args.engine, args.query.strip(), args.task_id, args.token)
    else:
        run(args.engine, args.query.strip())


if __name__ == "__main__":
    main()
