"""字幕模型（对齐 src/captions/types.ts 的简化版）。

核心子集只表达「字幕轨道 + 若干 cue」，样式/翻译/避让等高级能力延后。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CaptionCue:
    startFrame: int
    endFrame: int
    text: str
    speakerId: str | None = None


@dataclass(frozen=True)
class CaptionsData:
    enabled: bool = True
    items: tuple[CaptionCue, ...] = ()
