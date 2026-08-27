"""素材池模型：媒体资产与文件夹（对齐 src/editor/mediaTypes.ts 的核心字段）。"""
from __future__ import annotations

from dataclasses import dataclass

from .transcript import TranscriptWord


@dataclass(frozen=True)
class MediaAsset:
    id: str
    name: str
    kind: str                # video / image / audio / gif / svg / ...
    src: str = ""
    durationInFrames: int | None = None
    width: int | None = None
    height: int | None = None
    favorite: bool = False
    folderId: str | None = None
    # transcript（pool.setTranscription 用，毫秒）
    transcript: tuple[TranscriptWord, ...] = ()
    transcriptSourceRevision: str | None = None
    transcriptStale: bool = False


@dataclass(frozen=True)
class MediaFolder:
    id: str
    name: str
