"""导出：纯 FFmpeg 合成（对齐 src/generate/media-export.ts 的输入输出契约）。

首版覆盖：视频片段线性 concat + 音频混流 + 帧范围裁剪。转场 xfade、分辨率
归一化、字幕烧录为首版降级项（见各函数注释）。字幕/XML 走 subtitles.py / fcpxml.py。
"""
from __future__ import annotations

import os
import shutil
import subprocess
from typing import Sequence

from ..domain.captions import CaptionsData
from ..domain.item import TimelineItem
from ..domain.timeline import Timeline
from .subtitles import captions_to_srt

VIDEO_KINDS = ("video", "image", "gif", "svg")


def _ffmpeg_bin() -> str:
    return os.environ.get("OPENCHATCUT_FFMPEG") or os.environ.get("FFMPEG_PATH") or "ffmpeg"


def _clip_seconds(item: TimelineItem, fps: int) -> float:
    return item.durationInFrames / fps


def _codec_flags(codec: str) -> list[str]:
    if codec == "vp8":
        return ["-c:v", "libvpx", "-c:a", "libvorbis"]
    if codec == "mp3":
        return ["-c:a", "libmp3lame"]
    if codec == "wav":
        return ["-c:a", "pcm_s16le"]
    return ["-c:v", "libx264", "-c:a", "aac"]  # h264


def render_timeline(
    tl: Timeline,
    out_path: str,
    format: str = "video",
    codec: str = "h264",
    fps: int | None = None,
    start_frame: int = 0,
    end_frame_exclusive: int | None = None,
) -> dict:
    """渲染时间线到 out_path。返回 {ok, path, durationSeconds, ...} 或 {ok:False, error}。"""
    ffmpeg = _ffmpeg_bin()
    if not shutil.which(ffmpeg):
        return {"ok": False, "error": "ffmpeg not found in PATH (set OPENCHATCUT_FFMPEG)"}
    fps = fps or tl.fps or 30

    video_clips = sorted(
        (i for i in tl.items if i.src and i.kind in VIDEO_KINDS),
        key=lambda x: x.startFrame,
    )
    audio_clips = [i for i in tl.items if i.src and i.kind == "audio"]

    if format == "audio":
        return _render_audio(audio_clips or video_clips, out_path, codec, fps)

    if not video_clips:
        return {"ok": False, "error": "no video clips with src to render"}

    return _render_video(video_clips, audio_clips, out_path, codec, fps,
                         start_frame, end_frame_exclusive)


def _render_audio(sources: Sequence[TimelineItem], out_path: str, codec: str, fps: int) -> dict:
    if not sources:
        return {"ok": False, "error": "no audio sources"}
    cmd = [_ffmpeg_bin(), "-y"]
    for s in sources:
        cmd += ["-i", s.src]
    # 多源混流
    if len(sources) > 1:
        inputs = "".join(f"[{i}:a]" for i in range(len(sources)))
        cmd += ["-filter_complex", f"{inputs}amix=inputs={len(sources)}:duration=longest[a]",
                "-map", "[a]"]
    else:
        cmd += ["-map", "0:a"]
    cmd += _codec_flags(codec) + [out_path]
    return _run(cmd, out_path)


def _render_video(video_clips, audio_clips, out_path, codec, fps,
                  start_frame, end_frame_exclusive) -> dict:
    cmd = [_ffmpeg_bin(), "-y"]
    for c in video_clips:
        cmd += ["-i", c.src]
    n = len(video_clips)

    # 视频 concat（首版：线性 concat，不做 xfade 转场 / 分辨率归一化）
    v_in = "".join(f"[{i}:v]" for i in range(n))
    filter_parts = [f"{v_in}concat=n={n}:v=1:a=0[v]"]

    # 音频：优先用音频轨 amix，否则用 video clips 自身音频
    if audio_clips:
        for a in audio_clips:
            cmd += ["-i", a.src]
        a_in = "".join(f"[{n + i}:a]" for i in range(len(audio_clips)))
        filter_parts.append(f"{a_in}amix=inputs={len(audio_clips)}:duration=longest[a]")
        maps = ["-map", "[v]", "-map", "[a]"]
    else:
        maps = ["-map", "[v]"]

    cmd += ["-filter_complex", ";".join(filter_parts)] + maps

    # 帧范围裁剪（半开 [start, end)）→ 输出端 -ss/-t
    if start_frame > 0 or end_frame_exclusive is not None:
        cmd += ["-ss", f"{start_frame / fps:.6f}"]
        if end_frame_exclusive is not None:
            cmd += ["-t", f"{(end_frame_exclusive - start_frame) / fps:.6f}"]

    cmd += _codec_flags(codec) + [out_path]
    return _run(cmd, out_path)


def _run(cmd: list[str], out_path: str) -> dict:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ffmpeg render timed out"}
    if proc.returncode != 0:
        return {"ok": False, "error": (proc.stderr or "").strip()[-500:]}
    if not os.path.exists(out_path):
        return {"ok": False, "error": "ffmpeg produced no output"}
    return {"ok": True, "path": out_path}


def export_subtitles(captions: CaptionsData, fps: int, out_path: str) -> dict:
    """导出字幕为 SRT 文件。"""
    try:
        srt = captions_to_srt(captions, fps)
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(srt)
        return {"ok": True, "path": out_path}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
