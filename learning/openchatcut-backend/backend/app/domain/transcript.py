"""转写数据模型：词级转写 + 翻译/修正变体（对齐 src/transcript/types.ts）。

注意：transcript 时间戳用毫秒（ms），clip 用帧（startFrame/durationInFrames），
两者用 ms_to_frame 转换（对齐源码 msToFrame）。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptWord:
    text: str = ""
    startMs: int = 0          # 毫秒
    endMs: int = 0
    speaker: str | None = None   # 'A' | 'B' | ...（diarization 时）
    id: str | None = None


@dataclass(frozen=True)
class TranscriptVariantWord:
    i: int                      # 源词索引（sparse overlay）
    text: str


@dataclass(frozen=True)
class TranscriptVariant:
    id: str
    lang: str
    kind: str                   # 'translation' | 'corrected'
    label: str
    words: tuple[TranscriptVariantWord, ...] = ()


def ms_to_frame(ms: int, fps: int) -> int:
    """毫秒 → 帧（对齐源码 msToFrame 的 JS Math.round 语义：.5 向上）。"""
    return math.floor(ms / 1000 * fps + 0.5)
