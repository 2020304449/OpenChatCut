"""片段模型：TimelineItem 及其视觉/音频子结构（对齐 src/editor/clipTypes.ts 核心字段）。

沿用帧单位（startFrame / durationInFrames / srcInFrame / fadeInFrames），不换算秒。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .transcript import TranscriptVariant, TranscriptWord

# TimelineItem.kind 的 9 种取值
ITEM_KINDS = (
    "motion-graphic", "audio", "video", "image", "text",
    "gif", "svg", "solid", "sequence",
)


@dataclass(frozen=True)
class ClipTransform:
    scale: float | None = None
    scaleX: float | None = None
    scaleY: float | None = None
    x: float | None = None
    y: float | None = None
    rotation: float | None = None
    opacity: float | None = None
    borderRadius: float | None = None


@dataclass(frozen=True)
class ClipFilters:
    brightness: float | None = None
    contrast: float | None = None
    saturate: float | None = None
    blur: float | None = None


@dataclass(frozen=True)
class ZoomEffect:
    magnification: float | None = None
    focalPointX: float | None = None
    focalPointY: float | None = None
    shape: str | None = None


@dataclass(frozen=True)
class ClipEffect:
    id: str
    assetId: str
    overrides: dict[str, object] | None = None


@dataclass(frozen=True)
class Keyframe:
    frame: int
    value: float
    easing: str | None = None


@dataclass(frozen=True)
class ReframeKeyframe:
    frame: int
    focalPointX: float        # 0..1
    focalPointY: float        # 0..1
    magnification: float      # 0.05..16


@dataclass(frozen=True)
class TimelineItem:
    id: str
    track: str
    startFrame: int
    durationInFrames: int
    name: str
    kind: str                      # 见 ITEM_KINDS
    # motion-graphic
    templateId: str | None = None
    code: str | None = None
    props: dict[str, object] | None = None
    width: int | None = None
    height: int | None = None
    # media source
    src: str | None = None
    sourceAssetId: str | None = None
    sourceFilename: str | None = None
    sourceRevision: str | None = None
    sourceContentHash: str | None = None
    # audio / video
    volume: float | None = None
    srcInFrame: int | None = None
    fadeInFrames: int | None = None
    fadeOutFrames: int | None = None
    # visual
    transform: ClipTransform | None = None
    keyframes: dict[str, tuple[Keyframe, ...]] | None = None   # prop -> 关键帧曲线
    filters: ClipFilters | None = None
    zoom: ZoomEffect | None = None
    effects: tuple[ClipEffect, ...] = ()
    # speed
    playbackRate: float | None = None
    # transcript（词级转写，时间戳用毫秒）
    transcript: tuple[TranscriptWord, ...] | None = None
    transcriptGenerationId: str | None = None
    transcriptStale: bool = False
    variants: tuple[TranscriptVariant, ...] = ()
    deletedWordIdx: tuple[int, ...] = ()
    silenceFrames: int | None = None
    cutPadFrames: int | None = None
    gapCapsMs: dict[str, int] | None = None
    transcriptPlayOrder: tuple[int, ...] | None = None
    # A-2 补充：背景填充 / 降噪 / reframe
    backgroundFill: bool = False
    backgroundFillStrength: int | None = None
    denoisedSrc: str | None = None
    denoiseStrength: int | None = None
    reframeKeyframes: tuple[ReframeKeyframe, ...] = ()
    # A-3: 多机位
    multicamGroupId: str | None = None
    multicamAngleId: str | None = None
