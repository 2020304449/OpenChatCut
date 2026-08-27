"""编辑核心数据模型：时间线、轨道、片段。

刻意用 frozen dataclass 表达「不可变状态」——任何编辑都不是原地修改，
而是产出一个新的 Timeline。这与 OpenChatCut `src/editor/` 里不可变时间线
状态的思路一致（详见 docs/ai-editing-agent-jingdu.md）。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass


def new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass(frozen=True)
class Clip:
    id: str
    label: str
    kind: str        # "video" | "caption"
    start: float     # 起始时间（秒）
    duration: float  # 时长（秒）


@dataclass(frozen=True)
class Track:
    id: str
    kind: str                       # "video" | "caption"
    clips: tuple[Clip, ...] = ()


@dataclass(frozen=True)
class Timeline:
    tracks: tuple[Track, ...] = ()


def default_timeline() -> Timeline:
    """新工程：一个视频轨 + 一个字幕轨。"""
    return Timeline(tracks=(Track(id="v1", kind="video"), Track(id="c1", kind="caption")))


# ── 序列化（供 REST / SSE 输出 JSON） ──────────────────────────────────────

def clip_to_dict(clip: Clip) -> dict:
    return {
        "id": clip.id,
        "label": clip.label,
        "kind": clip.kind,
        "start": clip.start,
        "duration": clip.duration,
    }


def track_to_dict(track: Track) -> dict:
    return {
        "id": track.id,
        "kind": track.kind,
        "clips": [clip_to_dict(c) for c in track.clips],
    }


def timeline_to_dict(timeline: Timeline) -> dict:
    return {"tracks": [track_to_dict(t) for t in timeline.tracks]}
