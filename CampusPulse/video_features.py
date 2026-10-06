"""
短视频剪辑特征（镜头切换 / 卡点 / 节奏）

对 B 站热门视频下载 360P 流（临时文件，分析后立即删除，只保留数值特征）：
1. 镜头切换：ffmpeg scene 检测，得到每个切点时间；
2. 音频节奏：ffmpeg 解码为 11025Hz 单声道 PCM → 频谱通量（spectral flux）起音包络 → 起音峰值；
   自相关估计 BPM；
3. 卡点程度：切点落在起音峰 ±70ms 内的比例，与“随机切点”期望比例相比得到提升倍数 sync_lift；
4. 剪辑风格：卡点剪辑 / 快切转场 / 常规剪辑 / 长镜头口播。

局限：能量化“切得多快、是否踩点”，但不能区分具体转场手法（遮挡、甩镜、变装等），
这类需要视觉模型逐帧判断，成本较高，未在此实现。
"""

import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
from typing import Dict, List, Optional

import numpy as np
import requests
from loguru import logger

from . import storage

_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Referer": "https://www.bilibili.com/",
}
MAX_DURATION = 300          # 秒；更长的视频（多为长视频/番剧）跳过
MAX_BYTES = 40 * 1024 * 1024
SR = 11025
HOP = 256
SYNC_WINDOW = 0.07


def _download(bvid: str, cid: int, path: str) -> None:
    data = requests.get("https://api.bilibili.com/x/player/playurl",
                        params={"bvid": bvid, "cid": cid, "qn": 16, "fnval": 1, "platform": "html5"},
                        headers=_HEADERS, timeout=15).json()
    durl = ((data.get("data") or {}).get("durl") or [{}])[0]
    if not durl.get("url"):
        raise RuntimeError(f"playurl 无可用地址: {data.get('message')}")
    with requests.get(durl["url"], headers=_HEADERS, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        size = 0
        with open(path, "wb") as fh:
            for chunk in resp.iter_content(1 << 16):
                size += len(chunk)
                if size > MAX_BYTES:
                    raise RuntimeError("视频过大，跳过")
                fh.write(chunk)


def detect_cuts(path: str, threshold: float = 0.3) -> List[float]:
    proc = subprocess.run(
        ["nice", "-n", "15", "ffmpeg", "-hide_banner", "-nostats", "-i", path, "-an",
         "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, timeout=240)
    return [float(t) for t in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]


def onset_envelope(path: str) -> np.ndarray:
    proc = subprocess.run(
        ["nice", "-n", "15", "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path,
         "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
        capture_output=True, timeout=180)
    audio = np.frombuffer(proc.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    if audio.size < SR:
        return np.zeros(0)
    n_fft = 1024
    frames = 1 + (audio.size - n_fft) // HOP
    idx = np.arange(n_fft)[None, :] + HOP * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(audio[idx] * np.hanning(n_fft), axis=1))
    spec = np.log1p(10 * spec)
    flux = np.maximum(0.0, np.diff(spec, axis=0)).sum(axis=1)
    return (flux - flux.mean()) / (flux.std() + 1e-9)


def onset_peaks(env: np.ndarray) -> np.ndarray:
    if env.size < 5:
        return np.zeros(0)
    fps = SR / HOP
    w = max(1, int(0.05 * fps))
    local_max = np.array([env[i] == env[max(0, i - w): i + w + 1].max() for i in range(env.size)])
    peaks = np.where(local_max & (env > 1.0))[0]
    return (peaks + 1) / fps


def estimate_bpm(env: np.ndarray) -> Optional[float]:
    fps = SR / HOP
    if env.size < fps * 8:
        return None
    ac = np.correlate(env, env, mode="full")[env.size - 1:]
    lo, hi = int(fps * 60 / 180), int(fps * 60 / 70)  # 70~180 BPM
    if hi >= ac.size:
        return None
    lag = lo + int(np.argmax(ac[lo:hi]))
    return round(60 * fps / lag, 1)


def edit_features(cuts: List[float], peaks: np.ndarray, duration: float, bpm: Optional[float]) -> Dict:
    duration = max(duration, 1.0)
    n = len(cuts)
    shots = np.diff([0.0, *cuts, duration]) if n else np.array([duration])
    synced = sum(1 for c in cuts if peaks.size and np.min(np.abs(peaks - c)) <= SYNC_WINDOW)
    sync_ratio = synced / n if n else 0.0
    # 随机切点落在任一起音峰 ±窗口内的期望概率
    expected = min(1.0, peaks.size * 2 * SYNC_WINDOW / duration) if peaks.size else 0.0
    lift = sync_ratio / expected if expected > 0 else 0.0
    cpm = n / duration * 60
    first3 = sum(1 for c in cuts if c <= 3.0)
    if n >= 8 and lift >= 1.8 and sync_ratio >= 0.45:
        style = "卡点剪辑"
    elif cpm >= 30:
        style = "快切转场"
    elif cpm < 6:
        style = "长镜头/口播"
    else:
        style = "常规剪辑"
    return {
        "duration": round(duration, 1),
        "cuts": n,
        "cuts_per_min": round(cpm, 1),
        "median_shot": round(float(np.median(shots)), 2),
        "hook_cuts_3s": first3,
        "beat_sync_ratio": round(sync_ratio, 2),
        "sync_lift": round(lift, 2),
        "bpm": bpm,
        "style": style,
    }


def analyze_video(bvid: str, cid: int, duration: float) -> Dict:
    with tempfile.TemporaryDirectory(prefix="pulse_v_") as tmp:
        path = os.path.join(tmp, "v.mp4")
        _download(bvid, cid, path)
        cuts = detect_cuts(path)
        env = onset_envelope(path)
        feats = edit_features(cuts, onset_peaks(env), duration, estimate_bpm(env))
        # 高潜力视频（卡点 / 快切）再做具体转场手法识别；视频文件仍在临时目录中
        if feats["style"] in ("卡点剪辑", "快切转场"):
            from . import transitions

            trans = transitions.analyze(path, bvid, cuts, duration)
            if trans:
                feats["transition"] = trans.get("template_name") or trans.get("dominant")
        return feats


# ------------------------------------------------------------------ 后台队列

_queue: "queue.Queue[Dict]" = queue.Queue(maxsize=200)
_queued: set = set()
_worker: Optional[threading.Thread] = None


def queue_size() -> int:
    return _queue.qsize()


def cached(bvid: str) -> Optional[Dict]:
    blob = storage.kv_get("vfeat:" + bvid)
    return json.loads(blob) if blob else None


def enqueue(videos: List[Dict], limit: int = 12) -> int:
    """把尚未分析的短视频加入后台队列（每批次最多 limit 个）。"""
    n = 0
    for v in videos:
        bvid, cid, dur = v.get("bvid"), v.get("cid"), v.get("duration") or 0
        if not bvid or not cid or dur > MAX_DURATION or bvid in _queued:
            continue
        done = cached(bvid)
        # 已分析过的视频：只有“卡点 / 快切”且尚未做转场识别的才补做一次
        if done and (done.get("error") or done.get("style") not in ("卡点剪辑", "快切转场")
                     or storage.kv_get("vtrans:" + bvid)):
            continue
        try:
            _queue.put_nowait({"bvid": bvid, "cid": cid, "duration": dur})
        except queue.Full:
            break
        _queued.add(bvid)
        n += 1
        if n >= limit:
            break
    _ensure_worker()
    return n


def _ensure_worker() -> None:
    global _worker
    if _worker and _worker.is_alive():
        return

    def loop():
        while True:
            job = _queue.get()
            try:
                feats = analyze_video(job["bvid"], job["cid"], job["duration"])
                feats["analyzed_at"] = int(time.time())
                storage.kv_set("vfeat:" + job["bvid"], json.dumps(feats, ensure_ascii=False).encode("utf-8"))
                logger.info(f"[CampusPulse] 视频特征 {job['bvid']}: {feats['style']} "
                            f"cuts={feats['cuts']} lift={feats['sync_lift']}")
            except Exception as exc:
                storage.kv_set("vfeat:" + job["bvid"], json.dumps({"error": str(exc)[:200],
                               "analyzed_at": int(time.time())}).encode("utf-8"))
                logger.warning(f"[CampusPulse] 视频特征分析失败 {job['bvid']}: {exc}")
            finally:
                _queued.discard(job["bvid"])
                time.sleep(3)

    _worker = threading.Thread(target=loop, name="campus-pulse-video", daemon=True)
    _worker.start()
