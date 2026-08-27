"""命令层测试：38 种命令的 apply + 撤销/重做。"""
import pytest

from app.commands.actions import (
    AddAsset, AddItem, AddMarker, AddTransition,
    ClearKeyframes, ClearTimeline, DuplicateItem, MoveItem,
    PoolCreateFolder, PoolMoveAssets, PoolRemoveAsset,
    RemoveItem, RemoveKeyframe, RemoveMarker, RemoveTransition,
    RetimeItem, Select, SelectAll, SelectMany,
    SetCaptions, SetCaptionsHidden, SetItemEffects, SetItemFade,
    SetItemFilters, SetItemSpeed, SetItemTransform, SetItemVolume,
    SetItemZoom, SetKeyframe, SetTransition, SplitItem,
    ToggleTrackFlag, TrackCreate, TrackDelete, TrackUpdate,
    UpdateCaptions, UpdateItemProps, UpdateMarker,
)
from app.commands.base import Executor
from app.domain.captions import CaptionCue, CaptionsData
from app.domain.item import ClipEffect, TimelineItem
from app.domain.marker import Marker
from app.domain.media import MediaAsset, MediaFolder
from app.domain.timeline import active_timeline, default_project
from app.domain.transition import TransitionItem


def make_item(item_id="i1", track="V1", start=0, dur=90, kind="video", name="A"):
    return TimelineItem(id=item_id, track=track, startFrame=start,
                        durationInFrames=dur, kind=kind, name=name)


@pytest.fixture
def ex():
    return Executor(default_project())


def _add(ex, item):
    ex.execute(AddItem(item))
    return item


def _tl(ex):
    return active_timeline(ex.state)


def _items(ex):
    return _tl(ex).items


def _find(ex, item_id):
    return next(i for i in _items(ex) if i.id == item_id)


# ── 轨道 ───────────────────────────────────────────────────────────────────

def test_track_create_and_update(ex):
    ex.execute(TrackCreate("A3", "audio", name="音效"))
    tl = _tl(ex)
    assert "A3" in tl.tracks
    assert tl.tracks["A3"].kind == "audio"

    ex.execute(TrackUpdate("A3", {"muted": True}))
    assert _tl(ex).tracks["A3"].muted is True


def test_track_toggle_and_delete(ex):
    ex.execute(TrackCreate("A3", "audio"))
    ex.execute(ToggleTrackFlag("A3", "hidden", True))
    assert _tl(ex).tracks["A3"].hidden is True

    ex.execute(TrackDelete("A3"))
    assert "A3" not in _tl(ex).tracks


# ── 片段基础 ───────────────────────────────────────────────────────────────

def test_add_and_remove_item(ex):
    _add(ex, make_item("i1"))
    assert len(_items(ex)) == 1
    ex.execute(RemoveItem("i1"))
    assert len(_items(ex)) == 0


def test_clear_timeline(ex):
    _add(ex, make_item("i1"))
    _add(ex, make_item("i2", start=90))
    ex.execute(ClearTimeline())
    assert len(_items(ex)) == 0


def test_duplicate_item(ex):
    _add(ex, make_item("i1", dur=90))
    ex.execute(DuplicateItem("i1", "i2"))
    assert len(_items(ex)) == 2
    dup = _find(ex, "i2")
    assert dup.startFrame == 90   # 紧跟在原片段之后


def test_split_item(ex):
    _add(ex, make_item("i1", dur=90))
    ex.execute(SplitItem("i1", at_frame=30, new_id="i2"))
    assert len(_items(ex)) == 2
    assert _find(ex, "i1").durationInFrames == 30
    assert _find(ex, "i2").startFrame == 30
    assert _find(ex, "i2").durationInFrames == 60


def test_move_and_retime_item(ex):
    _add(ex, make_item("i1", track="V1", start=0))
    ex.execute(MoveItem("i1", track="V2", startFrame=100))
    assert _find(ex, "i1").track == "V2"
    assert _find(ex, "i1").startFrame == 100

    ex.execute(RetimeItem("i1", durationInFrames=120, srcInFrame=10))
    assert _find(ex, "i1").durationInFrames == 120
    assert _find(ex, "i1").srcInFrame == 10


def test_update_item_props(ex):
    _add(ex, make_item("i1"))
    ex.execute(UpdateItemProps("i1", {"name": "改名", "volume": 0.5}))
    it = _find(ex, "i1")
    assert it.name == "改名"
    assert it.volume == 0.5


# ── 片段属性 ───────────────────────────────────────────────────────────────

def test_set_item_volume_and_fade(ex):
    _add(ex, make_item("i1"))
    ex.execute(SetItemVolume("i1", 0.3))
    assert _find(ex, "i1").volume == 0.3
    ex.execute(SetItemFade("i1", fadeInFrames=10, fadeOutFrames=20))
    assert _find(ex, "i1").fadeInFrames == 10
    assert _find(ex, "i1").fadeOutFrames == 20


def test_set_item_transform_filters_speed_zoom(ex):
    _add(ex, make_item("i1"))
    ex.execute(SetItemTransform("i1", {"scale": 2.0, "rotation": 45}))
    assert _find(ex, "i1").transform.scale == 2.0
    ex.execute(SetItemFilters("i1", {"brightness": 1.2}))
    assert _find(ex, "i1").filters.brightness == 1.2
    ex.execute(SetItemSpeed("i1", 2.0))
    assert _find(ex, "i1").playbackRate == 2.0
    ex.execute(SetItemZoom("i1", {"magnification": 1.5}))
    assert _find(ex, "i1").zoom.magnification == 1.5


def test_set_item_effects(ex):
    _add(ex, make_item("i1"))
    fx = ClipEffect(id="fx1", assetId="lut:film")
    ex.execute(SetItemEffects("i1", (fx,)))
    assert _find(ex, "i1").effects == (fx,)


# ── 转场 ───────────────────────────────────────────────────────────────────

def test_transition_lifecycle(ex):
    _add(ex, make_item("i1"))
    _add(ex, make_item("i2", start=90))
    tr = TransitionItem(id="t1", incomingItemId="i2", transType="crossfade", durationInFrames=15)
    ex.execute(AddTransition(tr))
    assert _tl(ex).transitions == (tr,)

    ex.execute(SetTransition("t1", {"durationInFrames": 30}))
    assert _tl(ex).transitions[0].durationInFrames == 30

    ex.execute(RemoveTransition("t1"))
    assert len(_tl(ex).transitions) == 0


# ── 字幕 ───────────────────────────────────────────────────────────────────

def test_captions(ex):
    cap = CaptionsData(items=(CaptionCue(0, 30, "你好"),))
    ex.execute(SetCaptions(cap))
    assert _tl(ex).captions.items[0].text == "你好"

    ex.execute(UpdateCaptions({"enabled": False}))
    assert _tl(ex).captions.enabled is False

    ex.execute(SetCaptionsHidden(True))
    assert _tl(ex).captionsHidden is True


# ── 关键帧 ─────────────────────────────────────────────────────────────────

def test_keyframes(ex):
    _add(ex, make_item("i1"))
    ex.execute(SetKeyframe("i1", "x", 0, 100.0))
    ex.execute(SetKeyframe("i1", "x", 50, 200.0))
    ex.execute(SetKeyframe("i1", "x", 50, 250.0))  # 同帧覆盖
    kfs = _find(ex, "i1").keyframes["x"]
    assert [k.frame for k in kfs] == [0, 50]
    assert kfs[1].value == 250.0

    ex.execute(RemoveKeyframe("i1", "x", 0))
    assert [k.frame for k in _find(ex, "i1").keyframes["x"]] == [50]

    ex.execute(ClearKeyframes("i1", "x"))
    assert _find(ex, "i1").keyframes is None


# ── 标记 ───────────────────────────────────────────────────────────────────

def test_markers(ex):
    m = Marker(id="m1", name="TODO", frame=10)
    ex.execute(AddMarker(m))
    assert _tl(ex).markers == (m,)

    ex.execute(UpdateMarker("m1", {"name": "改名"}))
    assert _tl(ex).markers[0].name == "改名"

    ex.execute(RemoveMarker("m1"))
    assert len(_tl(ex).markers) == 0


# ── 选择 ───────────────────────────────────────────────────────────────────

def test_selection(ex):
    _add(ex, make_item("i1"))
    _add(ex, make_item("i2", start=90))
    _add(ex, make_item("i3", start=180))

    ex.execute(Select("i1"))
    assert _tl(ex).selectedId == "i1"

    ex.execute(Select("i2", mode="add"))
    assert _tl(ex).selectedIds == ("i1", "i2")

    ex.execute(SelectMany(("i1", "i3")))
    assert _tl(ex).selectedIds == ("i1", "i3")

    ex.execute(SelectAll())
    assert _tl(ex).selectedIds == ("i1", "i2", "i3")


# ── 素材池 ─────────────────────────────────────────────────────────────────

def test_media_pool(ex):
    a = MediaAsset(id="a1", name="bgm.mp3", kind="audio")
    ex.execute(AddAsset(a))
    assert ex.state.assets == (a,)

    f = MediaFolder(id="f1", name="音乐")
    ex.execute(PoolCreateFolder(f))
    assert ex.state.mediaFolders == (f,)

    ex.execute(PoolMoveAssets(("a1",), folderId="f1"))
    assert ex.state.assets[0].folderId == "f1"

    ex.execute(PoolRemoveAsset("a1"))
    assert len(ex.state.assets) == 0


# ── 撤销/重做 ──────────────────────────────────────────────────────────────

def test_undo_redo(ex):
    _add(ex, make_item("i1"))
    _add(ex, make_item("i2", start=90))
    assert len(_items(ex)) == 2

    ex.undo()
    assert len(_items(ex)) == 1

    ex.undo()
    assert len(_items(ex)) == 0

    ex.redo()
    assert len(_items(ex)) == 1

    # 撤销栈空时安全 no-op
    ex2 = Executor(default_project())
    assert ex2.undo() is None
