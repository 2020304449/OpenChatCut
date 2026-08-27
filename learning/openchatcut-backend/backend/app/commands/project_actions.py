"""项目级命令（对齐 src/editor/reducerActions.ts 的 ProjectAction）。

作用于 ProjectDoc 顶层（多时间线 / 素材池 / 设计风格），而非 activeTimeline。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.media import MediaFolder
from ..domain.timeline import ProjectDoc, Timeline, active_timeline
from .actions import _map_active
from .base import Command


# ── 多时间线（tl.*） ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class TimelineCreate(Command):
    timeline: Timeline
    activate: bool = False

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        timelines = doc.timelines + (self.timeline,)
        active = self.timeline.id if self.activate else doc.activeTimelineId
        return replace(doc, timelines=timelines, activeTimelineId=active)


@dataclass(frozen=True)
class TimelineSwitch(Command):
    timeline_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        # 简化：导航也记历史（OpenChatCut 的 tl.switch 不产生历史，需 Executor 支持非历史命令，留待后续）
        return replace(doc, activeTimelineId=self.timeline_id)


@dataclass(frozen=True)
class TimelineDuplicate(Command):
    timeline_id: str
    new_id: str
    name: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        src = next((t for t in doc.timelines if t.id == self.timeline_id), None)
        if src is None:
            return doc
        dup = replace(src, id=self.new_id, name=self.name,
                      order=max((t.order for t in doc.timelines), default=0) + 1)
        return replace(doc, timelines=doc.timelines + (dup,))


@dataclass(frozen=True)
class TimelineDelete(Command):
    timeline_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        timelines = tuple(t for t in doc.timelines if t.id != self.timeline_id)
        active = doc.activeTimelineId
        if active == self.timeline_id:
            active = timelines[0].id if timelines else ""
        return replace(doc, timelines=timelines, activeTimelineId=active)


@dataclass(frozen=True)
class TimelineRename(Command):
    timeline_id: str
    name: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        timelines = tuple(replace(t, name=self.name) if t.id == self.timeline_id else t
                          for t in doc.timelines)
        return replace(doc, timelines=timelines)


@dataclass(frozen=True)
class TimelineRetarget(Command):
    timeline_id: str
    width: int
    height: int
    fit: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        timelines = tuple(
            replace(t, width=self.width, height=self.height, fit=self.fit)
            if t.id == self.timeline_id else t
            for t in doc.timelines
        )
        return replace(doc, timelines=timelines)


@dataclass(frozen=True)
class TimelineSetHidden(Command):
    timeline_id: str
    hidden: bool

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        timelines = tuple(replace(t, hidden=self.hidden) if t.id == self.timeline_id else t
                          for t in doc.timelines)
        return replace(doc, timelines=timelines)


@dataclass(frozen=True)
class TimelineSetDoc(Command):
    doc: ProjectDoc

    def apply(self, state: ProjectDoc) -> ProjectDoc:
        return self.doc


# ── 素材池剩余（pool.*） ───────────────────────────────────────────────────

@dataclass(frozen=True)
class PoolRenameFolder(Command):
    folder_id: str
    name: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        folders = tuple(replace(f, name=self.name) if f.id == self.folder_id else f
                        for f in doc.mediaFolders)
        return replace(doc, mediaFolders=folders)


@dataclass(frozen=True)
class PoolDeleteFolder(Command):
    folder_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        folders = tuple(f for f in doc.mediaFolders if f.id != self.folder_id)
        assets = tuple(replace(a, folderId=None) if a.folderId == self.folder_id else a
                       for a in doc.assets)
        return replace(doc, mediaFolders=folders, assets=assets)


@dataclass(frozen=True)
class PoolUpdateAsset(Command):
    asset_id: str
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        assets = tuple(replace(a, **self.patch) if a.id == self.asset_id else a
                       for a in doc.assets)
        return replace(doc, assets=assets)


@dataclass(frozen=True)
class PoolRelinkAsset(Command):
    asset_id: str
    src: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        assets = tuple(replace(a, src=self.src) if a.id == self.asset_id else a
                       for a in doc.assets)
        return replace(doc, assets=assets)


@dataclass(frozen=True)
class PoolCanonicalizeAsset(Command):
    duplicate_id: str
    canonical_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        # 简化：把 duplicate 从素材池移除，引用它的片段改指向 canonical
        def fn(tl: Timeline) -> Timeline:
            items = tuple(
                replace(i, sourceAssetId=self.canonical_id)
                if i.sourceAssetId == self.duplicate_id else i
                for i in tl.items
            )
            return replace(tl, items=items)
        doc = _map_active(doc, fn)
        return replace(doc, assets=tuple(a for a in doc.assets if a.id != self.duplicate_id))


# ── 设计风格（design.*） ───────────────────────────────────────────────────

@dataclass(frozen=True)
class SetDesignStyle(Command):
    style: dict[str, object] | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return replace(doc, designStyle=self.style)


@dataclass(frozen=True)
class PatchDesignStyle(Command):
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        cur = dict(doc.designStyle or {})
        cur.update(self.patch)
        return replace(doc, designStyle=cur)


# ── 整体状态 ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SetFullState(Command):
    patch: dict[str, object]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        # 简化：用 patch 语义更新 activeTimeline 的多个字段（源码是完整 TimelineState 替换）
        return _map_active(doc, lambda tl: replace(tl, **self.patch))
