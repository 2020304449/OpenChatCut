"""文本稿词级编辑命令（12 种，对齐 src/editor/reducerActions.ts 的 transcript Action）。

复用 actions.py 的 `_map_active` / `_map_item` 作用域路由 helper。
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from ..domain.item import TimelineItem
from ..domain.transcript import TranscriptVariant, TranscriptWord
from ..domain.timeline import ProjectDoc, Timeline
from .actions import _map_active, _map_item
from .base import Command

# 填充词（cleanScript 用，可扩展）
FILLER_WORDS = frozenset({
    "um", "uh", "er", "呃", "嗯", "啊", "那个", "这个", "就是", "然后", "然后呢", "对吧",
})


@dataclass(frozen=True)
class SetItemTranscript(Command):
    item_id: str
    transcript: tuple[TranscriptWord, ...]
    generation_id: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            return replace(item, transcript=self.transcript,
                           transcriptGenerationId=self.generation_id,
                           transcriptStale=False)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetItemVariants(Command):
    item_id: str
    variants: tuple[TranscriptVariant, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_item(doc, self.item_id, lambda it: replace(it, variants=self.variants))


@dataclass(frozen=True)
class ToggleWord(Command):
    item_id: str
    idx: int

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            deleted = list(item.deletedWordIdx)
            if self.idx in deleted:
                deleted.remove(self.idx)
            else:
                deleted.append(self.idx)
            deleted.sort()
            return replace(item, deletedWordIdx=tuple(deleted))
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class DeleteWords(Command):
    item_id: str
    idxs: tuple[int, ...]

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            merged = sorted(set(item.deletedWordIdx) | set(self.idxs))
            return replace(item, deletedWordIdx=tuple(merged))
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class CleanScript(Command):
    """清理脚本：移除填充词 + 记录停顿压缩参数。

    简化说明：OpenChatCut 的 cleanScript 会真正重算词级时间轴（ms），
    这里只做「填充词加入 deletedWordIdx + 记录 silenceFrames/cutPadFrames」，
    时间轴重算由播放层（后续阶段）根据这些参数执行。
    """
    item_id: str
    remove_fillers: bool = True
    silence_frames: int | None = None
    cut_pad_frames: int | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            deleted = list(item.deletedWordIdx)
            if self.remove_fillers and item.transcript:
                for i, w in enumerate(item.transcript):
                    if w.text.strip().lower() in FILLER_WORDS and i not in deleted:
                        deleted.append(i)
            deleted.sort()
            return replace(
                item,
                deletedWordIdx=tuple(deleted),
                silenceFrames=self.silence_frames if self.silence_frames is not None else item.silenceFrames,
                cutPadFrames=self.cut_pad_frames if self.cut_pad_frames is not None else item.cutPadFrames,
            )
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetGapCap(Command):
    item_id: str
    after_word_idx: int
    max_ms: int | None      # None = 清除该 gap 的上限

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            caps = dict(item.gapCapsMs or {})
            key = str(self.after_word_idx)
            if self.max_ms is None:
                caps.pop(key, None)
            else:
                caps[key] = self.max_ms
            return replace(item, gapCapsMs=caps or None)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class SetTranscriptPlayOrder(Command):
    item_id: str
    play_order: tuple[int, ...] | None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        return _map_item(doc, self.item_id, lambda it: replace(it, transcriptPlayOrder=self.play_order))


@dataclass(frozen=True)
class ReorderTrackItems(Command):
    """按 orderedIds 重排某轨道上的 item（对齐源码，gap-aware 原子重排的简化版）。

    starts（可选）为指定 id pin 绝对帧；未列入 orderedIds 的 item 保持原相对顺序。
    """
    track: str
    ordered_ids: tuple[str, ...]
    starts: dict[str, int] | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(tl: Timeline) -> Timeline:
            result = list(tl.items)
            track_indices = [idx for idx, i in enumerate(result) if i.track == self.track]
            track_items = [result[idx] for idx in track_indices]
            id_to_item = {i.id: i for i in track_items}
            ordered = []
            for oid in self.ordered_ids:
                if oid in id_to_item:
                    it = id_to_item[oid]
                    if self.starts and oid in self.starts:
                        it = replace(it, startFrame=self.starts[oid])
                    ordered.append(it)
            for i in track_items:          # 未列入的保持原顺序
                if i.id not in self.ordered_ids:
                    ordered.append(i)
            for pos, it in zip(track_indices, ordered):
                result[pos] = it
            return replace(tl, items=tuple(result))
        return _map_active(doc, fn)


@dataclass(frozen=True)
class ClearEdits(Command):
    item_id: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            return replace(item, deletedWordIdx=(), gapCapsMs=None,
                           transcriptPlayOrder=None, variants=())
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class FixTranscriptWord(Command):
    item_id: str
    word_idx: int
    text: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            transcript = list(item.transcript or ())
            if self.word_idx < len(transcript):
                transcript[self.word_idx] = replace(transcript[self.word_idx], text=self.text)
            return replace(item, transcript=tuple(transcript))
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class RenameSpeaker(Command):
    item_id: str
    from_speaker: str
    to_speaker: str

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        def fn(item: TimelineItem) -> TimelineItem:
            transcript = tuple(
                replace(w, speaker=self.to_speaker) if w.speaker == self.from_speaker else w
                for w in (item.transcript or ())
            )
            return replace(item, transcript=transcript)
        return _map_item(doc, self.item_id, fn)


@dataclass(frozen=True)
class PoolSetTranscription(Command):
    asset_id: str
    transcript: tuple[TranscriptWord, ...]
    source_revision: str | None = None

    def apply(self, doc: ProjectDoc) -> ProjectDoc:
        assets = tuple(
            replace(a, transcript=self.transcript,
                    transcriptSourceRevision=self.source_revision or a.transcriptSourceRevision,
                    transcriptStale=False)
            if a.id == self.asset_id else a
            for a in doc.assets
        )
        return replace(doc, assets=assets)
