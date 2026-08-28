"""媒体探测：ffprobe 本地封装（对齐 media-normalization.ts 的 probeVideo 层）。

字段对齐原版 ProbeMeta：width/height/duration/videoCodec/audioCodec/hasAudio/
avgFrameRate/nominalFrameRate/frameCount/variableFrameRate。probe_media 工具复用
它并映射成工具返回结构（qualityRisks 等）。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any

from .ffmpeg import ffprobe_bin as _ffprobe_bin


def _parse_rate(rate: str | None) -> float | None:
    """解析 '30000/1001' 或 '29.97' 这类帧率字符串。"""
    if not rate or rate in ("0/0", "N/A"):
        return None
    try:
        if "/" in rate:
            num, den = rate.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else None
        return float(rate)
    except (ValueError, ZeroDivisionError):
        return None


def _quality_risks(p: dict) -> list[str]:
    risks: list[str] = []
    w, h = p.get("width"), p.get("height")
    if w is not None and h is not None and (w < 720 or h < 480):
        risks.append("low_resolution")
    if p.get("audio_channels") == 1:
        risks.append("mono_audio")
    dur = p.get("duration")
    if dur is not None and dur < 3.0:
        risks.append("very_short")
    if p.get("variable_frame_rate"):
        risks.append("variable_frame_rate")
    fps = p.get("fps")
    if fps is not None and fps < 20:
        risks.append("low_frame_rate")
    return risks


def probe_video(path: str) -> dict:
    """本地 ffprobe 探测，返回对齐原版 probeVideo 的完整字段。"""
    if not shutil.which(_ffprobe_bin()):
        return {"ok": False, "error": "ffprobe not found in PATH (set OPENCHATCUT_FFPROBE)"}
    try:
        out = subprocess.run(
            [_ffprobe_bin(), "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "error": str(exc)}
    if out.returncode != 0:
        return {"ok": False, "error": (out.stderr or "").strip()[:500]}
    try:
        data = json.loads(out.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"ffprobe output not parseable: {exc}"}

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    avg = _parse_rate((video or {}).get("avg_frame_rate"))
    nominal = _parse_rate((video or {}).get("r_frame_rate"))
    width = video.get("width")
    height = video.get("height")
    rotation = _rotation_of(video, data)
    if rotation in (90, -90, 270, -270):
        width, height = height, width

    frame_count = None
    try:
        if video and video.get("nb_frames"):
            frame_count = int(video["nb_frames"])
    except (ValueError, TypeError):
        frame_count = None

    duration = None
    for src in (fmt.get("duration"), (video or {}).get("duration"), (audio or {}).get("duration")):
        try:
            duration = float(src)
            break
        except (TypeError, ValueError):
            continue

    result = {
        "ok": True,
        "width": width,
        "height": height,
        "duration": duration,
        "video_codec": (video or {}).get("codec_name"),
        "audio_codec": (audio or {}).get("codec_name"),
        "has_audio": audio is not None,
        "has_video": video is not None,
        "audio_channels": (audio or {}).get("channels"),
        "avg_frame_rate": avg,
        "nominal_frame_rate": nominal,
        "frame_count": frame_count,
        "variable_frame_rate": _is_vfr(avg, nominal),
        "fps": avg or nominal,
        "source_bitrate": fmt.get("bit_rate"),
        "size": fmt.get("size"),
    }
    result["quality_risks"] = _quality_risks(result)
    return result


def probe_media(path: str) -> dict:
    """probe_media 工具层返回结构（对齐 probe-tools.ts 的 ProbeResult）。"""
    p = probe_video(path)
    if not p.get("ok"):
        return p
    return {
        "ok": True,
        "durationSeconds": p.get("duration"),
        "width": p.get("width"),
        "height": p.get("height"),
        "fps": p.get("fps"),
        "hasVideoTrack": p.get("has_video"),
        "hasAudioTrack": p.get("has_audio"),
        "videoCodec": p.get("video_codec"),
        "audioCodec": p.get("audio_codec"),
        "qualityRisks": p.get("quality_risks", []),
    }


def _rotation_of(video: dict | None, data: dict[str, Any]) -> int | None:
    if not video:
        return None
    for src in (video.get("rotation"), video.get("tags", {}).get("rotate")):
        try:
            if src is not None:
                return int(float(src))
        except (ValueError, TypeError):
            continue
    for side in (video.get("side_data_list") or []):
        try:
            if side.get("rotation"):
                return int(float(side["rotation"]))
        except (ValueError, TypeError):
            continue
    return None


def _is_vfr(avg: float | None, nominal: float | None) -> bool:
    if avg is None or nominal is None:
        return False
    return abs(avg - nominal) > 0.01
