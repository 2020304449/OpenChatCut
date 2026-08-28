"""导出：纯 FFmpeg 合成（对齐 src/generate/media-export.ts 的输入输出契约）。

轨道语义：
- V1 的 video 片段 = 主视频序列，按 startFrame 线性拼接，相邻片段可做 xfade crossfade。
  每个片段按 [srcInFrame, srcInFrame+durationInFrames) 裁剪（秒，项目 fps）。
- 非 V1 的 image/gif/svg = 叠层，按时间窗 overlay 到主序列（居中，保持原尺寸）。
- audio 片段 = 背景音乐/人声轨，按 item 时长裁剪后 amix 混流。
- captions = 字幕，烧录进视频（SRT → subtitles filter）。

首版仍降级：多叠层位置/缩放未接 transform；主序列存在 gap/xfade 时叠层时间轴按「无 gap」近似。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from typing import Sequence

from ..domain.captions import CaptionsData
from ..domain.item import TimelineItem
from ..domain.timeline import Timeline
from ..domain.transition import TransitionItem
from .ffmpeg import ffmpeg_bin as _ffmpeg_bin
from .subtitles import captions_to_srt

OVERLAY_KINDS = ("image", "gif", "svg")


def _codec_flags(codec: str) -> list[str]:
    if codec == "vp8":
        return ["-c:v", "libvpx", "-c:a", "libvorbis"]
    if codec == "mp3":
        return ["-c:a", "libmp3lame"]
    if codec == "wav":
        return ["-c:a", "pcm_s16le"]
    return ["-c:v", "libx264", "-c:a", "aac"]  # h264


def _video_filter(w: int, h: int, fps: int, item: TimelineItem) -> str:
    """视频片段：裁剪到 [srcInFrame, srcInFrame+dur)（秒）→ 归一化尺寸/帧率。"""
    sf = (item.srcInFrame or 0) / fps
    ef = ((item.srcInFrame or 0) + item.durationInFrames) / fps
    return (f"trim=start={sf:.3f}:end={ef:.3f},setpts=PTS-STARTPTS,"
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}")


def _escape_filter_path(p: str) -> str:
    """subtitles filter 的 filename 转义（Windows 冒号/反斜杠）。"""
    return p.replace("\\", "/").replace(":", "\\:")


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
    w = tl.width or 1920
    h = tl.height or 1080

    main_clips = sorted(
        (i for i in tl.items if i.src and i.kind == "video" and i.track == "V1"),
        key=lambda x: x.startFrame,
    )
    overlays = sorted(
        (i for i in tl.items if i.src and i.kind in OVERLAY_KINDS and i.track != "V1"),
        key=lambda x: x.startFrame,
    )
    audio_clips = [i for i in tl.items if i.src and i.kind == "audio"]

    if format == "audio":
        return _render_audio(audio_clips or main_clips, out_path, codec, fps)

    if not main_clips:
        return {"ok": False, "error": "no V1 video clips to render"}

    return _render_video(main_clips, overlays, audio_clips, tl.captions, tl.transitions,
                         out_path, codec, fps, w, h, start_frame, end_frame_exclusive)


def _render_audio(sources: Sequence[TimelineItem], out_path: str, codec: str, fps: int) -> dict:
    if not sources:
        return {"ok": False, "error": "no audio sources"}
    cmd = [_ffmpeg_bin(), "-y"]
    for s in sources:
        cmd += ["-i", s.src]
    if len(sources) > 1:
        inputs = "".join(f"[{i}:a]" for i in range(len(sources)))
        cmd += ["-filter_complex", f"{inputs}amix=inputs={len(sources)}:duration=longest[a]",
                "-map", "[a]"]
    else:
        cmd += ["-map", "0:a"]
    cmd += _codec_flags(codec) + [out_path]
    return _run(cmd, out_path)


def _transition_for(clip: TimelineItem, transitions: Sequence[TransitionItem]) -> TransitionItem | None:
    """返回「进入该片段」的 crossfade 转场，无则 None。"""
    for t in transitions:
        if t.incomingItemId == clip.id and t.durationInFrames and t.transType and "crossfade" in t.transType.lower():
            return t
    return None


def _render_video(
    main_clips: Sequence[TimelineItem],
    overlays: Sequence[TimelineItem],
    audio_clips: Sequence[TimelineItem],
    captions: CaptionsData | None,
    transitions: Sequence[TransitionItem],
    out_path: str,
    codec: str,
    fps: int,
    w: int,
    h: int,
    start_frame: int,
    end_frame_exclusive: int | None,
) -> dict:
    cmd = [_ffmpeg_bin(), "-y"]
    filters: list[str] = []

    # ── 主序列：逐片段裁剪 + 归一化 ──
    for c in main_clips:
        cmd += ["-i", c.src]
    for i, c in enumerate(main_clips):
        filters.append(f"[{i}:v]{_video_filter(w, h, fps, c)}[n{i}]")

    # ── 主序列合并：相邻片段 xfade（crossfade）否则 concat ──
    cur_label = "n0"
    cur_dur = main_clips[0].durationInFrames / fps
    for i in range(1, len(main_clips)):
        out_label = f"m{i}"
        tr = _transition_for(main_clips[i], transitions)
        if tr:
            xdur = (tr.durationInFrames or 0) / fps
            offset = max(cur_dur - xdur, 0.0)
            filters.append(
                f"[{cur_label}][n{i}]xfade=transition=fade:duration={xdur:.3f}:offset={offset:.3f}[{out_label}]"
            )
            cur_dur = cur_dur + main_clips[i].durationInFrames / fps - xdur
        else:
            filters.append(f"[{cur_label}][n{i}]concat=n=2:v=1:a=0[{out_label}]")
            cur_dur = cur_dur + main_clips[i].durationInFrames / fps
        cur_label = out_label

    video_label = cur_label

    # ── 叠层：非 V1 图像，按时间窗居中 overlay（静态图循环） ──
    for j, o in enumerate(overlays):
        if o.kind == "image":
            cmd += ["-loop", "1", "-i", o.src]
        else:
            cmd += ["-i", o.src]
        src_idx = len(main_clips) + j
        start_s = o.startFrame / fps
        end_s = (o.startFrame + o.durationInFrames) / fps
        out_label = f"ov{j}"
        filters.append(
            f"[{video_label}][{src_idx}:v]overlay=(W-w)/2:(H-h)/2"
            f":enable='between(t,{start_s:.3f},{end_s:.3f})'[{out_label}]"
        )
        video_label = out_label

    # ── 字幕烧录 ──
    srt_tmp: str | None = None
    if captions and captions.enabled and captions.items:
        fd, srt_tmp = tempfile.mkstemp(suffix=".srt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(captions_to_srt(captions, fps))
        out_label = "vsub"
        filters.append(
            f"[{video_label}]subtitles=filename='{_escape_filter_path(srt_tmp)}'[{out_label}]"
        )
        video_label = out_label

    maps = ["-map", f"[{video_label}]"]

    # ── 音频：按 item 时长裁剪后 amix ──
    if audio_clips:
        base = len(main_clips) + len(overlays)
        for i, a in enumerate(audio_clips):
            cmd += ["-i", a.src]
            sf = (a.srcInFrame or 0) / fps
            ef = ((a.srcInFrame or 0) + a.durationInFrames) / fps
            filters.append(f"[{base + i}:a]atrim=start={sf:.3f}:end={ef:.3f},asetpts=PTS-STARTPTS[a{i}]")
        a_in = "".join(f"[a{i}]" for i in range(len(audio_clips)))
        filters.append(f"{a_in}amix=inputs={len(audio_clips)}:duration=first[a]")
        maps += ["-map", "[a]"]

    cmd += ["-filter_complex", ";".join(filters)] + maps

    # 帧范围裁剪（半开 [start, end)）→ 输出端 -ss/-t
    if start_frame > 0 or end_frame_exclusive is not None:
        cmd += ["-ss", f"{start_frame / fps:.6f}"]
        if end_frame_exclusive is not None:
            cmd += ["-t", f"{(end_frame_exclusive - start_frame) / fps:.6f}"]
    else:
        # 无显式裁剪时，以最短流（视频）为准，避免 BGM 比画面长拖出黑屏尾
        cmd += ["-shortest"]

    cmd += _codec_flags(codec) + [out_path]

    result = _run(cmd, out_path)

    # subtitles filter 在 ffmpeg 运行期间读取 SRT，跑完再清理临时文件
    if srt_tmp is not None:
        try:
            os.unlink(srt_tmp)
        except OSError:
            pass

    return result


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
