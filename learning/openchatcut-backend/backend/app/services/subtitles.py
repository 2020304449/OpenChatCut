"""字幕导出：CaptionCue → SRT 纯文本（对齐 src/generate/subtitles.ts）。"""
from __future__ import annotations

from ..domain.captions import CaptionsData


def _srt_time(frame: int, fps: int) -> str:
    ms = int(round(frame / fps * 1000))
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    milli = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def captions_to_srt(captions: CaptionsData, fps: int) -> str:
    blocks: list[str] = []
    for i, cue in enumerate(captions.items, start=1):
        blocks.append(
            f"{i}\n{_srt_time(cue.startFrame, fps)} --> {_srt_time(cue.endFrame, fps)}\n{cue.text}\n"
        )
    return "\n".join(blocks)
