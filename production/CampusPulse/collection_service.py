"""Internal HTTP boundary for the collection queue.

Only the main application calls this service. It has no published host port;
requests are authenticated with a short-lived HMAC derived from the existing
server-side session secret, without sending that secret over the network.
"""

import hashlib
import hmac
import os
import time

import eventlet
import eventlet.wsgi
from flask import Flask, jsonify, request

from . import collection_queue


app = Flask(__name__)


@app.before_request
def authenticate_internal_call():
    if request.path == "/health":
        return None
    timestamp = request.headers.get("X-Collection-Timestamp", "")
    signature = request.headers.get("X-Collection-Signature", "")
    secret = os.environ.get("WEB_SESSION_SECRET", "")
    try:
        fresh = abs(time.time() - int(timestamp)) <= 30
    except ValueError:
        fresh = False
    if not (secret and fresh and len(signature) == 64):
        return jsonify(success=False, message="未授权"), 403
    key = hashlib.sha256(b"CampusPulse collection service v1\0" + secret.encode()).digest()
    signed = (timestamp + "\n" + request.method + "\n" + request.path + "\n").encode() + request.get_data()
    expected = hmac.new(key, signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return jsonify(success=False, message="未授权"), 403
    return None


@app.get("/health")
def health():
    available = collection_queue.status_local()["available"]
    return jsonify(success=available), 200 if available else 503


@app.get("/status")
def status():
    return jsonify(collection_queue.status_local())


@app.post("/enqueue")
def enqueue():
    body = request.get_json(silent=True)
    source = body.get("source") if isinstance(body, dict) else None
    if source not in ("manual", "scheduled"):
        return jsonify(success=False, message="无效任务来源"), 400
    try:
        return jsonify(collection_queue.enqueue_local(source))
    except Exception:
        app.logger.exception("Collection queue enqueue failed")
        return jsonify(success=False, message="采集队列暂时不可用"), 503


def main():
    port = int(os.environ.get("COLLECTION_SERVICE_PORT", "5101"))
    eventlet.wsgi.server(eventlet.listen(("0.0.0.0", port)), app, log_output=False)


if __name__ == "__main__":
    main()
