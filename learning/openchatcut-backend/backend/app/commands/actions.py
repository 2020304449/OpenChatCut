"""38 种核心命令子集（对齐 src/editor/reducerActions.ts 的 Action 联合类型）。

命令作用域：per-timeline 命令落到 `activeTimeline`（`_map_active` 路由），
素材池命令落到 ProjectDoc 顶层。与 OpenChatCut 的 `projectReduce` 路由一致。

命令是纯值对象：`apply(state) -> new_state`，不原地改状态。注意 `tracks` / `keyframes`
等可变字段，命令里一律用「拷贝 + replace 出新 dict」而非原地修改。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.captions import CaptionsData
from ..domain.item import ClipEffect, ClipFilters, ClipTransform, Keyframe, ReframeKeyframe, TimelineItem, ZoomEffect
from ..domain.marker import Marker
from ..domain.media import MediaAsset, MediaFolder
from ..domain.timeline import ProjectDoc, Timeline, Watermark, active_timeline
from ..domain.track import TrackFlags
from ..domain.transition import TransitionItem
from .base import Command


# ── 作用域路由 helper ──────────────────────────────────────────────────────

def _map_active(doc: ProjectDoc, fn) -> ProjectDoc:
    tl = active_timeline(doc)
    new_tl = fn(tl)
    timelines = tuple(new_tl if t.id == tl.id else t for t in doc.timelines)
    return replace(doc, timelines=timelines)


def _map_item(doc: ProjectDoc, item_id: str, fn) -> ProjectDoc:
    def _fn(tl: Timeline) -> Timeline:
        items = tuple(fn(i) if i.id == item_id else i for i in tl.items)
        return replace(tl, items=items)
    return _map_active(doc, _fn)


# ── 轨道（4） ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TrackCreate(Command):
    track_id: str
    kind: str
    name: str | None = None
    order: int | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            flags = TrackFlags(kind=self.kind, name=self.name)
            tracks = {**tl.tracks, self.track_id: flags}
            order = list(tl.trackOrder)
            if self.track_id not in order:
                if self.order is not None and 0 <= self.order < len(order):
                    order.insert(self.order, self.track_id)
                else:
                    order.append(self.track_id)
            return replace(tl, tracks=tracks, trackOrder=tuple(order))
        return _map_active(doc, fn)


@dataclass(frozen=True)
class TrackUpdate(Command):
    track_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            cur = tl.tracks.get(self.track_id, TrackFlags())
            new = replace(cur, **self.patch)
            return replace(tl, tracks={**tl.tracks, self.track_id: new})
        return _map_active(doc, fn)


@dataclass(frozen=True)
class TrackDelete(Command):
    track_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            tracks = {k: v for k, v in tl.tracks.items() if k != self.track_id}
            order = tuple(t for t in tl.trackOrder if t != self.track_id)
            items = tuple(i for i in tl.items if i.track != self.track_id)
            return replace(tl, tracks=tracks, trackOrder=order, items=items)
        return _map_active(doc, fn)


@dataclass(frozen=True)
class ToggleTrackFlag(Command):
    track_id: str
    flag: str      # 'hidden' | 'muted' | 'locked' | 'collapsed'
    value: bool

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            cur = tl.tracks.get(self.track_id, TrackFlags())
            new = replace(cur, **{self.flag: self.value})
            return replace(tl, tracks={**tl.tracks, self.track_id: new})
        return _map_active(doc, fn)


# ── 片段基础（8） ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AddItem(Command):
    item: TimelineItem
    ripple: bool = False

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, items=tl.items + (self.item,)))


@dataclass(frozen=True)
class RemoveItem(Command):
    item_id: str
    ripple: bool = False

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            items = tuple(i for i in tl.items if i.id != self.item_id)
            transitions = tuple(
                t for t in tl.transitions
                if t.incomingItemId != self.item_id and t.id != self.item_id
            )
            return replace(tl, items=items, transitions=transitions)
        return _map_active(doc, fn)


@dataclass(frozen=True)
class ClearTimeline(Command):
    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(
            doc,
            lambda tl: replace(tl, items=(), transitions=(),
                               selectedId=None, selectedIds=()),
        )


@dataclass(frozen=True)
class DuplicateItem(Command):
    item_id: str
    new_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            out = []
            for it in tl.items:
                out.append(it)
                if it.id == self.item_id:
                    out.append(replace(it, id=self.new_id,
                                       startFrame=it.startFrame + it.durationInFrames))
            return replace(tl, items=tuple(out))
        return _map_active(doc, fn)


@dataclass(frozen=True)
class SplitItem(Command):
    item_id: str
    at_frame: int      # 绝对帧分割点
    new_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            out = []
            for it in tl.items:
                if it.id != self.item_id:
                    out.append(it)
                    continue
                start, dur = it.startFrame, it.durationInFrames
                if self.at_frame <= start or self.at_frame >= start + dur:
                    out.append(it)   # 分割点越界，保持原样
                    continue
                left_dur = self.at_frame - start
                right_dur = dur - left_dur
                out.append(replace(it, durationInFrames=left_dur))
                out.append(replace(it, id=self.new_id, startFrame=self.at_frame,
                                   durationInFrames=right_dur))
            return replace(tl, items=tuple(out))
        return _map_active(doc, fn)


@dataclass(frozen=True)
class MoveItem(Command):
    item_id: str
    track: str | None = None
    startFrame: int | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            updates: dict[str, object] = {}
            if self.track is not None:
                updates["track"] = self.track
            if self.startFrame is not None:
                updates["startFrame"] = self.startFrame
            return replace(item, **updates)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class RetimeItem(Command):
    item_id: str
    startFrame: int | None = None
    durationInFrames: int | None = None
    srcInFrame: int | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            updates: dict[str, object] = {}
            if self.startFrame is not None:
                updates["startFrame"] = self.startFrame
            if self.durationInFrames is not None:
                updates["durationInFrames"] = self.durationInFrames
            if self.srcInFrame is not None:
                updates["srcInFrame"] = self.srcInFrame
            return replace(item, **updates)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class UpdateItemProps(Command):
    item_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_item(doc, self.item_id, lambda it: replace(it, **self.patch))


# ── 片段属性（7） ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SetItemVolume(Command):
    item_id: str
    volume: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_item(doc, self.item_id, lambda it: replace(it, volume=self.volume))


@dataclass(frozen=True)
class SetItemFade(Command):
    item_id: str
    fadeInFrames: int | None = None
    fadeOutFrames: int | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            updates: dict[str, object] = {}
            if self.fadeInFrames is not None:
                updates["fadeInFrames"] = self.fadeInFrames
            if self.fadeOutFrames is not None:
                updates["fadeOutFrames"] = self.fadeOutFrames
            return replace(item, **updates)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetItemTransform(Command):
    item_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            cur = item.transform or ClipTransform()
            return replace(item, transform=replace(cur, **self.patch))
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetItemFilters(Command):
    item_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            cur = item.filters or ClipFilters()
            return replace(item, filters=replace(cur, **self.patch))
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetItemSpeed(Command):
    item_id: str
    rate: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_item(doc, self.item_id, lambda it: replace(it, playbackRate=self.rate))


@dataclass(frozen=True)
class SetItemZoom(Command):
    item_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            cur = item.zoom or ZoomEffect()
            return replace(item, zoom=replace(cur, **self.patch))
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetItemEffects(Command):
    item_id: str
    effects: tuple[ClipEffect, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_item(doc, self.item_id, lambda it: replace(it, effects=self.effects))


# ── 转场（3） ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AddTransition(Command):
    transition: TransitionItem

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, transitions=tl.transitions + (self.transition,)))


@dataclass(frozen=True)
class SetTransition(Command):
    transition_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            ts = tuple(replace(t, **self.patch) if t.id == self.transition_id else t
                       for t in tl.transitions)
            return replace(tl, transitions=ts)
        return _map_active(doc, fn)


@dataclass(frozen=True)
class RemoveTransition(Command):
    transition_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            ts = tuple(t for t in tl.transitions if t.id != self.transition_id)
            return replace(tl, transitions=ts)
        return _map_active(doc, fn)


# ── 字幕（3） ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SetCaptions(Command):
    captions: CaptionsData | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, captions=self.captions))


@dataclass(frozen=True)
class UpdateCaptions(Command):
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            cur = tl.captions or CaptionsData()
            return replace(tl, captions=replace(cur, **self.patch))
        return _map_active(doc, fn)


@dataclass(frozen=True)
class SetCaptionsHidden(Command):
    hidden: bool

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, captionsHidden=self.hidden))


# ── 关键帧（3） ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SetKeyframe(Command):
    item_id: str
    prop: str
    frame: int
    value: float
    easing: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            curves = dict(item.keyframes or {})
            kfs = [k for k in curves.get(self.prop, ()) if k.frame != self.frame]
            kfs.append(Keyframe(frame=self.frame, value=self.value, easing=self.easing))
            kfs.sort(key=lambda k: k.frame)
            curves[self.prop] = tuple(kfs)
            return replace(item, keyframes=curves)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class RemoveKeyframe(Command):
    item_id: str
    prop: str
    frame: int

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            curves = dict(item.keyframes or {})
            kfs = tuple(k for k in curves.get(self.prop, ()) if k.frame != self.frame)
            if kfs:
                curves[self.prop] = kfs
            else:
                curves.pop(self.prop, None)
            return replace(item, keyframes=curves or None)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class ClearKeyframes(Command):
    item_id: str
    prop: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            if self.prop is None:
                return replace(item, keyframes=None)
            curves = dict(item.keyframes or {})
            curves.pop(self.prop, None)
            return replace(item, keyframes=curves or None)
        return _map_item(doc, self.item_id, fn)


# ── 标记（3） ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AddMarker(Command):
    marker: Marker

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_active(doc, lambda tl: replace(tl, markers=tl.markers + (self.marker,)))


@dataclass(frozen=True)
class UpdateMarker(Command):
    marker_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            ms = tuple(replace(m, **self.patch) if m.id == self.marker_id else m
                       for m in tl.markers)
            return replace(tl, markers=ms)
        return _map_active(doc, fn)


@dataclass(frozen=True)
class RemoveMarker(Command):
    marker_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            ms = tuple(m for m in tl.markers if m.id != self.marker_id)
            return replace(tl, markers=ms)
        return _map_active(doc, fn)


# ── 选择（3） ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Select(Command):
    item_id: str | None
    mode: str = "replace"      # 'replace' | 'toggle' | 'add'

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            if self.mode == "replace":
                return replace(tl, selectedId=self.item_id,
                               selectedIds=(self.item_id,) if self.item_id else ())
            ids = list(tl.selectedIds)
            if self.mode == "toggle":
                if self.item_id in ids:
                    ids.remove(self.item_id)
                elif self.item_id:
                    ids.append(self.item_id)
            elif self.mode == "add":
                if self.item_id and self.item_id not in ids:
                    ids.append(self.item_id)
            return replace(tl, selectedId=(ids[-1] if ids else None),
                           selectedIds=tuple(ids))
        return _map_active(doc, fn)


@dataclass(frozen=True)
class SelectMany(Command):
    ids: tuple[str, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            return replace(tl, selectedId=(self.ids[-1] if self.ids else None),
                           selectedIds=self.ids)
        return _map_active(doc, fn)


@dataclass(frozen=True)
class SelectAll(Command):
    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            ids = tuple(i.id for i in tl.items)
            return replace(tl, selectedId=(ids[-1] if ids else None), selectedIds=ids)
        return _map_active(doc, fn)


# ── 素材池（4） ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class AddAsset(Command):
    asset: MediaAsset

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return replace(doc, assets=doc.assets + (self.asset,))


@dataclass(frozen=True)
class PoolCreateFolder(Command):
    folder: MediaFolder

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return replace(doc, mediaFolders=doc.mediaFolders + (self.folder,))


@dataclass(frozen=True)
class PoolMoveAssets(Command):
    ids: tuple[str, ...]
    folderId: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        id_set = set(self.ids)
        assets = tuple(replace(a, folderId=self.folderId) if a.id in id_set else a
                       for a in doc.assets)
        return replace(doc, assets=assets)


@dataclass(frozen=True)
class PoolRemoveAsset(Command):
    asset_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return replace(doc, assets=tuple(a for a in doc.assets if a.id != self.asset_id))


# ── 片段属性补充（8，A-2） ─────────────────────────────────────────────────

@dataclass(frozen=True)
class SlipItem(Command):
    item_id: str
    delta_in_frames: int

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            cur = item.srcInFrame or 0
            return replace(item, srcInFrame=cur + self.delta_in_frames)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetBackgroundFill(Command):
    item_id: str
    enabled: bool
    strength: int | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            return replace(item, backgroundFill=self.enabled,
                           backgroundFillStrength=self.strength if self.strength is not None else item.backgroundFillStrength)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class ReplaceMedia(Command):
    item_id: str
    src: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_item(doc, self.item_id, lambda it: replace(it, src=self.src))


@dataclass(frozen=True)
class RelinkTimelineItem(Command):
    item_id: str
    src: str | None = None
    source_asset_id: str | None = None
    source_revision: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            updates: dict[str, object] = {}
            if self.src is not None:
                updates["src"] = self.src
            if self.source_asset_id is not None:
                updates["sourceAssetId"] = self.source_asset_id
            if self.source_revision is not None:
                updates["sourceRevision"] = self.source_revision
            return replace(item, **updates)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class UpdateWatermark(Command):
    enabled: bool | None = None
    text: str | None = None
    position: str | None = None
    opacity: float | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            cur = tl.watermark or Watermark()
            updates: dict[str, object] = {}
            if self.enabled is not None:
                updates["enabled"] = self.enabled
            if self.text is not None:
                updates["text"] = self.text
            if self.position is not None:
                updates["position"] = self.position
            if self.opacity is not None:
                updates["opacity"] = self.opacity
            return replace(tl, watermark=replace(cur, **updates))
        return _map_active(doc, fn)


@dataclass(frozen=True)
class SetItemDenoise(Command):
    item_id: str
    denoised_src: str | None
    strength: int | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            return replace(item, denoisedSrc=self.denoised_src,
                           denoiseStrength=self.strength if self.strength is not None else item.denoiseStrength)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetReframeKeyframe(Command):
    item_id: str
    frame: int
    focal_point_x: float
    focal_point_y: float
    magnification: float

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            kfs = [k for k in item.reframeKeyframes if k.frame != self.frame]
            kfs.append(ReframeKeyframe(frame=self.frame, focalPointX=self.focal_point_x,
                                       focalPointY=self.focal_point_y, magnification=self.magnification))
            kfs.sort(key=lambda k: k.frame)
            return replace(item, reframeKeyframes=tuple(kfs))
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class RemoveReframeKeyframe(Command):
    item_id: str
    frame: int

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            kfs = tuple(k for k in item.reframeKeyframes if k.frame != self.frame)
            return replace(item, reframeKeyframes=kfs)
        return _map_item(doc, self.item_id, fn)
