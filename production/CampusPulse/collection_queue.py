"""Durable, single-worker Redis Streams queue for CampusPulse collection.

The cache Redis is intentionally separate: queued work is stored in an AOF-backed
Redis instance and is acknowledged only after the pipeline has finished.
"""

import os
import time
import uuid
import hashlib
import hmac
import json
from functools import lru_cache

import redis
import requests


STREAM = "campuspulse:collection:stream:v1"
GROUP = "campuspulse:collection:workers:v1"
ACTIVE = "campuspulse:collection:active:v1"
LAST = "campuspulse:collection:last:v1"
HEARTBEAT = "campuspulse:collection:worker-heartbeat:v1"
JOB_PREFIX = "campuspulse:collection:job:v1:"

_ENQUEUE = """
local active = redis.call('GET', KEYS[1])
if active then
  local status = redis.call('HGET', ARGV[1] .. active, 'status')
  if status == 'queued' or status == 'running' then
    return {active, 'existing'}
  end
  redis.call('DEL', KEYS[1])
end
redis.call('HSET', ARGV[1] .. ARGV[2],
  'id', ARGV[2], 'status', 'queued', 'source', ARGV[3], 'submitted_at', ARGV[4])
redis.call('EXPIRE', ARGV[1] .. ARGV[2], 604800)
redis.call('SET', KEYS[1], ARGV[2])
redis.call('SET', KEYS[2], ARGV[2])
redis.call('XADD', KEYS[3], '*', 'job_id', ARGV[2])
return {ARGV[2], 'created'}
"""

_FINISH = """
redis.call('HSET', KEYS[1], 'status', ARGV[2], 'completed_at', ARGV[3],
  'result', ARGV[4])
redis.call('EXPIRE', KEYS[1], 604800)
if redis.call('GET', KEYS[2]) == ARGV[1] then
  redis.call('DEL', KEYS[2])
end
redis.call('XACK', KEYS[3], ARGV[5], ARGV[6])
redis.call('XDEL', KEYS[3], ARGV[6])
"""


@lru_cache(maxsize=1)
def client():
    url = os.environ.get("QUEUE_REDIS_URL", "").strip()
    if not url:
        raise RuntimeError("QUEUE_REDIS_URL 未配置")
    return redis.Redis.from_url(
        url, decode_responses=True, socket_connect_timeout=2, socket_timeout=10,
        health_check_interval=30,
    )


def job_key(job_id):
    return JOB_PREFIX + job_id


def _service_request(method, path, payload=None):
    """Call the internal collection API; the browser never sees this URL."""
    base = os.environ.get("COLLECTION_SERVICE_URL", "").rstrip("/")
    secret = os.environ.get("WEB_SESSION_SECRET", "")
    if not base or not secret:
        raise RuntimeError("采集服务地址或内部认证密钥未配置")
    body = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if payload is not None else b"")
    timestamp = str(int(time.time()))
    key = hashlib.sha256(b"CampusPulse collection service v1\0" + secret.encode()).digest()
    signed = (timestamp + "\n" + method + "\n" + path + "\n").encode() + body
    signature = hmac.new(key, signed, hashlib.sha256).hexdigest()
    response = requests.request(
        method, base + path, data=body if payload is not None else None,
        headers={"Content-Type": "application/json", "X-Collection-Timestamp": timestamp,
                 "X-Collection-Signature": signature},
        timeout=(1, 3),
    )
    response.raise_for_status()
    return response.json()


def enqueue(source="manual"):
    if os.environ.get("COLLECTION_SERVICE_URL"):
        return _service_request("POST", "/enqueue", {"source": source})
    return enqueue_local(source)


def enqueue_local(source="manual"):
    job_id = str(uuid.uuid4())
    result = client().eval(
        _ENQUEUE, 3, ACTIVE, LAST, STREAM, JOB_PREFIX, job_id,
        source, str(int(time.time())),
    )
    return {"job_id": result[0], "created": result[1] == "created"}


def status():
    if os.environ.get("COLLECTION_SERVICE_URL"):
        try:
            state = _service_request("GET", "/status")
            if not isinstance(state, dict) or "available" not in state:
                raise ValueError("采集服务返回无效状态")
            return state
        except (requests.RequestException, RuntimeError, ValueError):
            return {"available": False, "worker_alive": False, "running": False,
                    "stage": None, "job": None}
    return status_local()


def status_local():
    try:
        r = client()
        active_id, last_id, heartbeat = r.mget(ACTIVE, LAST, HEARTBEAT)
        job_id = active_id or last_id
        job = r.hgetall(job_key(job_id)) if job_id else {}
        if job and active_id == job_id and job.get("status") in ("queued", "running"):
            running = True
        else:
            running = False
        return {
            "available": True,
            "worker_alive": bool(heartbeat),
            "running": running,
            "stage": "排队中" if running and job.get("status") == "queued"
                     else "采集中" if running else None,
            "job": job or None,
        }
    except (redis.RedisError, RuntimeError):
        return {"available": False, "worker_alive": False, "running": False,
                "stage": None, "job": None}


def finish(job_id, message_id, result, failed=False):
    client().eval(
        _FINISH, 3, job_key(job_id), ACTIVE, STREAM, job_id,
        "failed" if failed else "complete", str(int(time.time())),
        str(result)[:500], GROUP, message_id,
    )
