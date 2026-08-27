"""时间线与工程模型（对齐 src/editor/timelineTypes.ts + projectTypes.ts 核心字段）。

- ProjectDoc = 多时间线 + 共享素材池 + activeTimelineId
- Timeline = 帧单位状态（fps/width/height/items/tracks/transitions/markers/captions/selection）

序列化统一用 dataclasses.asdict 递归转 dict；FastAPI 会把 tuple 序列化为 JSON 数组。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .captions import CaptionsData
from .item import TimelineItem
from .marker import Marker
from .media import MediaAsset, MediaFolder
from .multicam import MulticamGroup, TimelineLinkGroup
from .track import TRACK_ORDER, TrackFlags
from .transition import TransitionItem


@dataclass(frozen=True)
class Watermark:
    enabled: bool = False
    text: str = ""
    position: str = "br"      # 'tl' | 'tr' | 'bl' | 'br'
    opacity: float = 0.7


@dataclass(frozen=True)
class Timeline:
    id: str
    name: str
    order: int = 0
    hidden: bool = False
    # 画布 / 时间基准
    fps: int = 30
    width: int = 1920
    height: int = 1080
    fit: str | None = None
    # 内容
    items: tuple[TimelineItem, ...] = ()
    trackOrder: tuple[str, ...] = TRACK_ORDER
    tracks: dict[str, TrackFlags] = field(default_factory=dict)
    transitions: tuple[TransitionItem, ...] = ()
    markers: tuple[Marker, ...] = ()
    captionsHidden: bool = False
    # 选择
    selectedId: str | None = None
    selectedIds: tuple[str, ...] = ()
    # 字幕
    captions: CaptionsData | None = None
    # 水印
    watermark: Watermark | None = None
    # A-3: 联动组 / 多机位
    linkGroups: tuple[TimelineLinkGroup, ...] = ()
    multicamGroups: tuple[MulticamGroup, ...] = ()


@dataclass(frozen=True)
class ProjectDoc:
    version: int = 1
    assets: tuple[MediaAsset, ...] = ()
    mediaFolders: tuple[MediaFolder, ...] = ()
    timelines: tuple[Timeline, ...] = ()
    activeTimelineId: str = ""
    designStyle: dict[str, object] | None = None


def default_project() -> ProjectDoc:
    """新工程：一条默认时间线。"""
    tl = Timeline(id="tl1", name="时间线 1", order=0)
    return ProjectDoc(timelines=(tl,), activeTimelineId="tl1")


def active_timeline(doc: ProjectDoc) -> Timeline:
    """激活时间线；id 失效时回退到第一条。"""
    for tl in doc.timelines:
        if tl.id == doc.activeTimelineId:
            return tl
    return doc.timelines[0] if doc.timelines else Timeline(id="tl1", name="时间线 1")


def project_to_dict(doc: ProjectDoc) -> dict:
    # JSON round-trip 规范化：tuple → list，确保输出是纯 JSON 类型
    return json.loads(json.dumps(asdict(doc)))


def timeline_to_dict(tl: Timeline) -> dict:
    return json.loads(json.dumps(asdict(tl)))
