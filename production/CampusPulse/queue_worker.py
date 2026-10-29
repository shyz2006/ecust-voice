"""Run with ``python -m CampusPulse.queue_worker`` in one dedicated container."""

import threading
import time

import redis
from loguru import logger

from . import collection_queue as queue
from . import pipeline


def _heartbeat(stop):
    while not stop.is_set():
        try:
            queue.client().setex(queue.HEARTBEAT, 30, str(int(time.time())))
        except redis.RedisError:
            logger.warning("[CampusPulse] 队列心跳写入失败")
        stop.wait(10)


def _process(message_id, fields):
    job_id = fields.get("job_id", "")
    if not job_id:
        queue.client().xack(queue.STREAM, queue.GROUP, message_id)
        return
    job = queue.client().hgetall(queue.job_key(job_id))
    if job.get("status") in ("complete", "failed"):
        queue.finish(job_id, message_id, job.get("result", ""),
                     failed=job["status"] == "failed")
        return
    logger.info("[CampusPulse] 开始队列采集 {} ({})", job_id, job.get("source"))
    queue.client().hset(queue.job_key(job_id), mapping={
        "status": "running", "started_at": str(int(time.time())),
    })
    try:
        pipeline.recover_pending()
        result = pipeline.run_once()
        failed = bool(result.get("error") or result.get("skipped"))
        summary = result.get("error") or result.get("reason") or (
            "采集完成：{} 条".format(result.get("items", 0)))
    except Exception as exc:
        logger.exception("[CampusPulse] 队列任务执行失败：{}", exc)
        failed, summary = True, str(exc)
    queue.finish(job_id, message_id, summary, failed=failed)
    logger.info("[CampusPulse] 队列任务 {} {}", job_id, "失败" if failed else "完成")


def main():
    stop = threading.Event()
    threading.Thread(target=_heartbeat, args=(stop,), daemon=True,
                     name="collection-queue-heartbeat").start()
    try:
        while True:
            try:
                r = queue.client()
                try:
                    r.xgroup_create(queue.STREAM, queue.GROUP, id="0", mkstream=True)
                except redis.ResponseError as exc:
                    if "BUSYGROUP" not in str(exc):
                        raise
                # Fixed consumer name lets a restarted worker resume its own
                # unacknowledged task before taking any new task.
                pending = r.xreadgroup(queue.GROUP, "collection-worker",
                                       {queue.STREAM: "0"}, count=1)
                if pending and any(entries for _, entries in pending):
                    messages = pending
                else:
                    messages = r.xreadgroup(
                        queue.GROUP, "collection-worker", {queue.STREAM: ">"},
                        count=1, block=5000,
                    )
                for _, entries in messages:
                    for message_id, fields in entries:
                        _process(message_id, fields)
            except (redis.RedisError, RuntimeError) as exc:
                logger.warning("[CampusPulse] 队列暂时不可用：{}", exc)
                time.sleep(5)
    finally:
        stop.set()


if __name__ == "__main__":
    main()
