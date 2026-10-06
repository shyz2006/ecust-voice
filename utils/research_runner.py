"""
服务器端研究调度器：研究在服务器后台进程中运行，与浏览器会话完全解耦。

- start_research：为 task 认领引擎运行锁，并为每个引擎启动独立的后台 worker 进程；
  浏览器关闭 / 刷新 / 断网 / 换设备都不会影响研究。
- 三个引擎全部完成后，由最后完成的 worker 在服务器端触发最终报告生成（maybe_trigger_report）。
- rerun：失败或中断的引擎原地重新运行；引擎都已完成但报告缺失时重新生成报告。
- reap_orphans：服务重启后，清理没有对应进程的“运行中”锁并标记为失败，避免永远卡在运行中。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from loguru import logger

from utils.task_runtime import (
    claim_engine_run,
    engine_run_status,
    ensure_task,
    finish_engine_run,
    is_task_deleted,
    latest_task_report,
    list_task_ids,
    read_task_metadata,
    task_log_path,
    task_logs_dir,
    task_output_dir,
    task_runs_dir,
    validate_runtime_id,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENGINES = ("insight", "media", "query")
_WORKER = PROJECT_ROOT / "SingleEngineApp" / "research_worker.py"
_procs: Dict[str, subprocess.Popen] = {}
_procs_lock = threading.Lock()


def _lock_path(task_id: str, engine: str) -> Path:
    return task_runs_dir(task_id) / f"{engine}.lock"


def _pid_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # 僵尸进程也会通过 kill(0) 检查；读取 /proc 状态排除
    try:
        state = Path(f"/proc/{pid}/stat").read_text().split(")")[-1].split()[0]
        return state != "Z"
    except OSError:
        return True


def _write_lock_owner(task_id: str, engine: str, pid: int) -> None:
    path = _lock_path(task_id, engine)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    payload.update({"pid": pid, "runner": "background", "updated_at": time.time()})
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _spawn(task_id: str, engine: str, query: str, token: str) -> int:
    out_dir = task_logs_dir(task_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = open(out_dir / f"worker_{engine}.out", "ab")
    proc = subprocess.Popen(
        [sys.executable, str(_WORKER), engine, "--query", query, "--task-id", task_id, "--token", token],
        cwd=str(PROJECT_ROOT),
        stdout=out,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # 独立进程组：不随请求 / 浏览器会话结束
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )
    out.close()
    _write_lock_owner(task_id, engine, proc.pid)
    key = f"{task_id}:{engine}"
    with _procs_lock:
        _procs[key] = proc

    def _wait():  # 回收子进程，避免僵尸
        proc.wait()
        with _procs_lock:
            _procs.pop(key, None)

    threading.Thread(target=_wait, name=f"reap-{engine}-{task_id[-6:]}", daemon=True).start()
    return proc.pid


MAX_CONCURRENT_RESEARCH = int(os.environ.get("MAX_CONCURRENT_RESEARCH", "2") or 2)


def _admission_lock():
    """跨进程互斥（Flask 与三个 Streamlit 进程都可能发起研究），保证排队判断不冲突。"""
    from utils.task_runtime import queue_dir

    queue_dir().mkdir(parents=True, exist_ok=True)
    fh = open(queue_dir() / ".admission.lock", "a+")
    try:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_EX)
    except ImportError:
        try:
            import msvcrt
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        except Exception:
            pass
    return fh


def _release(fh) -> None:
    if fh is None:
        return
    try:
        import fcntl
        fcntl.flock(fh, fcntl.LOCK_UN)
    except ImportError:
        try:
            import msvcrt
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
    finally:
        try:
            fh.close()
        except Exception:
            pass


def active_research_tasks() -> List[str]:
    return [t for t in list_task_ids() if any(engine_run_status(t, e) == "running" for e in ENGINES)]


def queued_tasks() -> List[Dict[str, object]]:
    from utils.task_runtime import queue_dir

    entries = []
    for path in queue_dir().glob("task_*.json") if queue_dir().exists() else []:
        try:
            entries.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return sorted(entries, key=lambda e: e.get("queued_at", 0))


def queue_position(task_id: str) -> Optional[int]:
    for index, entry in enumerate(queued_tasks(), 1):
        if entry.get("task_id") == task_id:
            return index
    return None


def start_research(task_id: str, query: str, engines: Optional[Iterable[str]] = None) -> Dict[str, str]:
    """为 task 启动（尚未运行的）引擎；超过同时运行上限（MAX_CONCURRENT_RESEARCH）时进入排队。

    返回 {engine: started|queued|running|completed|failed|error:...}。
    """
    from utils.task_runtime import queue_dir, queued_entry

    task_id = validate_runtime_id(task_id)
    ensure_task(task_id, query=query)
    wanted = [e for e in (engines or ENGINES) if engine_run_status(task_id, e) not in ("running", "completed")]
    if not wanted:
        return {e: engine_run_status(task_id, e) for e in (engines or ENGINES)}
    fh = _admission_lock()
    try:
        entry = queued_entry(task_id)
        active = active_research_tasks()
        if entry is not None or (task_id not in active and len(active) >= MAX_CONCURRENT_RESEARCH):
            merged = sorted(set((entry or {}).get("engines") or []) | set(wanted))
            payload = {"task_id": task_id, "query": query, "engines": merged,
                       "queued_at": (entry or {}).get("queued_at") or time.time()}
            path = queue_dir() / f"{task_id}.json"
            tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
            if entry is None:
                logger.info(f"[ResearchRunner] task={task_id} 进入排队（运行中 {len(active)}/{MAX_CONCURRENT_RESEARCH}）")
            return {e: "queued" for e in wanted}
        return _start_now(task_id, query, wanted)
    finally:
        _release(fh)


def dispatch_queue() -> List[str]:
    """有空闲名额时按排队先后启动任务（由 Flask 进程中的调度线程周期调用）。"""
    from utils.task_runtime import queue_dir

    started = []
    fh = _admission_lock()
    try:
        for entry in queued_tasks():
            task_id = str(entry.get("task_id") or "")
            path = queue_dir() / f"{task_id}.json"
            if not task_id or is_task_deleted(task_id):
                path.unlink(missing_ok=True)
                continue
            if len(active_research_tasks()) >= MAX_CONCURRENT_RESEARCH:
                break
            path.unlink(missing_ok=True)
            engines = [e for e in entry.get("engines") or ENGINES
                       if engine_run_status(task_id, e) not in ("running", "completed")]
            if engines:
                _start_now(task_id, str(entry.get("query") or ""), engines)
                started.append(task_id)
                logger.info(f"[ResearchRunner] 排队任务 {task_id} 已开始运行")
    finally:
        _release(fh)
    return started


def _start_now(task_id: str, query: str, engines: Iterable[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for engine in engines:
        token, status = claim_engine_run(task_id, engine)
        if status != "claimed":
            result[engine] = status
            continue
        try:
            pid = _spawn(task_id, engine, query, token)
            result[engine] = "started"
            logger.info(f"[ResearchRunner] task={task_id} engine={engine} 已在后台启动 pid={pid}")
        except Exception as exc:  # 启动失败：释放锁并记为失败，可重新运行
            finish_engine_run(task_id, engine, token, success=False)
            result[engine] = f"error:{exc}"
            logger.exception(f"[ResearchRunner] 启动 {engine} 失败: {exc}")
    return result


def _report_files(task_id: str) -> List[Path]:
    directory = task_output_dir(task_id, "report")
    return sorted(directory.glob("final_report_*.html"), key=lambda p: p.stat().st_mtime) if directory.exists() else []


def all_engines_completed(task_id: str) -> bool:
    return all(engine_run_status(task_id, e) == "completed" for e in ENGINES)


def maybe_trigger_report(task_id: str, query: str = "", force: bool = False) -> str:
    """三个引擎都完成后在服务器端触发报告生成（不依赖浏览器是否停在报告页）。"""
    if not all_engines_completed(task_id):
        return "engines_not_ready"
    if _report_files(task_id) and not force:
        return "exists"
    query = query or str(read_task_metadata(task_id).get("query") or "智能舆情分析报告")
    port = int(os.environ.get("PORT") or _config_port())
    import requests

    for attempt in range(5):
        try:
            resp = requests.post(f"http://127.0.0.1:{port}/api/report/generate",
                                 json={"research_task_id": task_id, "query": query, "regenerate": force},
                                 timeout=30)
            if resp.status_code in (200, 409):
                logger.info(f"[ResearchRunner] task={task_id} 已触发报告生成: {resp.status_code}")
                return "triggered" if resp.status_code == 200 else "running"
            logger.warning(f"[ResearchRunner] 触发报告失败 {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:
            logger.warning(f"[ResearchRunner] 触发报告失败（第 {attempt + 1} 次）: {exc}")
        time.sleep(10 * (attempt + 1))
    return "failed"


def _config_port() -> int:
    try:
        from config import settings

        return int(settings.PORT)
    except Exception:
        return 5000


def reset_failed(task_id: str, engine: str) -> bool:
    """清除失败标记（以及没有存活进程的陈旧锁），使该引擎可以重新运行。"""
    runs = task_runs_dir(task_id)
    changed = False
    failed = runs / f"{engine}.failed"
    if failed.exists():
        failed.unlink()
        changed = True
    lock = runs / f"{engine}.lock"
    if lock.exists():
        try:
            pid = int(json.loads(lock.read_text(encoding="utf-8")).get("pid") or 0)
        except (OSError, ValueError):
            pid = 0
        if not _pid_alive(pid) or pid == os.getpid():
            lock.unlink(missing_ok=True)
            changed = True
    return changed


def rerun(task_id: str) -> Dict[str, object]:
    """失败 / 中断的引擎原地重跑；若引擎均已完成但报告缺失或失败，则重新生成报告。"""
    task_id = validate_runtime_id(task_id)
    if is_task_deleted(task_id):
        raise FileNotFoundError(task_id)
    query = str(read_task_metadata(task_id).get("query") or "")
    if not query:
        raise ValueError("任务缺少查询内容，无法重新运行")
    to_start = []
    for engine in ENGINES:
        status = engine_run_status(task_id, engine)
        if status == "failed" or (status == "running" and _orphaned(task_id, engine)):
            reset_failed(task_id, engine)
            to_start.append(engine)
        elif status not in ("running", "completed"):
            to_start.append(engine)
    started = start_research(task_id, query, to_start) if to_start else {}
    report = None
    if not to_start and all_engines_completed(task_id):
        threading.Thread(target=maybe_trigger_report, args=(task_id, query, True), daemon=True).start()
        report = "regenerating"
    return {"engines": started, "report": report}


def _orphaned(task_id: str, engine: str, grace_seconds: float = 120) -> bool:
    lock = _lock_path(task_id, engine)
    try:
        payload = json.loads(lock.read_text(encoding="utf-8"))
        age = time.time() - lock.stat().st_mtime
    except (OSError, ValueError):
        return False
    pid = int(payload.get("pid") or 0)
    if payload.get("runner") != "background" and pid == os.getpid():
        return False
    return age > grace_seconds and not _pid_alive(pid)


def reap_orphans() -> List[str]:
    """把“运行中但进程已不存在”（如服务重启中断）的引擎标记为失败，便于用户重新运行。"""
    reaped = []
    for task_id in list_task_ids():
        for engine in ENGINES:
            lock = _lock_path(task_id, engine)
            if not lock.exists() or not _orphaned(task_id, engine):
                continue
            try:
                token = json.loads(lock.read_text(encoding="utf-8")).get("token")
                finish_engine_run(task_id, engine, token, success=False)
                with task_log_path(task_id, engine).open("a", encoding="utf-8") as fh:
                    fh.write(time.strftime("%Y-%m-%d %H:%M:%S") +
                             f" | WARNING | research_runner - {engine} 后台进程已不存在（可能因服务重启中断），"
                             "已标记为失败，可在侧边栏点击“重新运行”继续\n")
                reaped.append(f"{task_id}:{engine}")
            except Exception as exc:
                logger.warning(f"[ResearchRunner] 清理 {task_id}:{engine} 失败: {exc}")
    if reaped:
        logger.warning(f"[ResearchRunner] 已标记中断的引擎运行: {reaped}")
    return reaped


_reaper_started = False


def start_reaper(interval: float = 120) -> None:
    global _reaper_started
    if _reaper_started:
        return
    _reaper_started = True

    def dispatch_loop():
        time.sleep(15)
        while True:
            try:
                dispatch_queue()
            except Exception as exc:
                logger.warning(f"[ResearchRunner] 排队调度异常: {exc}")
            time.sleep(5)

    threading.Thread(target=dispatch_loop, name="research-dispatcher", daemon=True).start()

    def loop():
        time.sleep(30)
        while True:
            try:
                reap_orphans()
            except Exception as exc:
                logger.warning(f"[ResearchRunner] 清理线程异常: {exc}")
            time.sleep(interval)

    threading.Thread(target=loop, name="research-reaper", daemon=True).start()
