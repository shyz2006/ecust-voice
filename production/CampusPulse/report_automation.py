"""Bounded, durable final-report recovery, independent of browser polling."""
import json
import os
import threading
import time
from loguru import logger

MAX_SUBMISSIONS = 3
_lock = threading.RLock()
_started = False


def _path(task_id):
    from utils.task_runtime import task_output_dir
    return task_output_dir(task_id, 'report') / 'automatic-completion.json'


def state(task_id):
    try:
        value = json.loads(_path(task_id).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(task_id, value):
    path = _path(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(temp, path)


def enable(task_id):
    """An explicit manual retry starts a new bounded cycle."""
    with _lock:
        _save(task_id, {'enabled': True, 'submissions': 0, 'next_at': 0})


def _enabled(task_id, value):
    from utils.task_runtime import read_task_metadata
    meta = read_task_metadata(task_id)
    return meta.get('pulse_revision') == 2 and (meta.get('auto_report') is True or value.get('enabled') is True)


def _permanent(result):
    error = str(result.get('error') or '').lower()
    return result.get('automatic_retry_allowed') is False or result.get('information_gap') or any(word in error for word in (
        '401', '403', 'invalid api key', 'incorrect api key', 'insufficient',
        'quota', '余额', '密钥无效', '未配置', '权限不足', 'authentication',
    ))


def waiting_message(task_id, result):
    value = state(task_id)
    if not _enabled(task_id, value) or value.get('submissions', 0) >= MAX_SUBMISSIONS or _permanent(result):
        return None
    if result.get('status') not in ('awaiting_report', 'failed') or not result.get('can_resume_report'):
        return None
    return '正在自动接续报告汇总，已完成章节会继续使用。' if value.get('submissions') else '研究材料已齐备，正在准备最终报告。'


def reconcile(task_ids=None, now=None):
    from . import research
    from utils.task_runtime import list_task_ids
    now = time.time() if now is None else now
    started = []
    for task_id in task_ids if task_ids is not None else list_task_ids():
        try:
            with _lock:
                value = state(task_id)
                if not _enabled(task_id, value) or value.get('submissions', 0) >= MAX_SUBMISSIONS:
                    continue
                if value.get('next_at', 0) > now:
                    continue
                result = research.status(task_id, auto=False)
                if not waiting_message(task_id, result):
                    continue
                # Claim before submission so restarts/polls never reset the limit.
                count = value.get('submissions', 0) + 1
                value.update(submissions=count, next_at=now + (60, 180, 600)[count-1])
                _save(task_id, value)
                research.resume_report(task_id, automatic=True)
                started.append(task_id)
        except Exception as exc:
            logger.warning('自动接续报告 {} 暂未完成: {}', task_id, type(exc).__name__)
    return started


def start_monitor():
    global _started
    with _lock:
        if _started:
            return
        _started = True

    def loop():
        time.sleep(25)
        while True:
            try:
                reconcile()
            except Exception as exc:
                logger.warning('报告接续检查暂未完成: {}', type(exc).__name__)
            time.sleep(20)

    threading.Thread(target=loop, name='report-completion-monitor', daemon=True).start()
