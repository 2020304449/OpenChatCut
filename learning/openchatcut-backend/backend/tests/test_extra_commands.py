"""片段属性补充（8）+ 项目级（16）命令测试。"""
import pytest

from app.commands import actions as A
from app.commands import project_actions as P
from app.commands.base import Executor
from app.domain.item import TimelineItem
from app.domain.media import MediaAsset, MediaFolder
from app.domain.timeline import Timeline, active_timeline, default_project


def make_item(item_id="i1", track="V1", start=0, dur=90):
    return TimelineItem(id=item_id, track=track, startFrame=start,
                        durationInFrames=dur, name="A", kind="video")


@pytest.fixture
def ex():
    e = Executor(default_project())
    e.execute(A.AddItem(make_item()))
    return e


def _find(ex, item_id="i1"):
    return next(i for i in active_timeline(ex.state).items if i.id == item_id)


# ── 片段属性补充 ───────────────────────────────────────────────────────────

def test_slip_item(ex):
    _find(ex)
    ex.execute(A.RetimeItem("i1", srcInFrame=10))
    ex.execute(A.SlipItem("i1", 5))
    assert _find(ex).srcInFrame == 15


def test_set_background_fill(ex):
    ex.execute(A.SetBackgroundFill("i1", True, 80))
    assert _find(ex).backgroundFill is True
    assert _find(ex).backgroundFillStrength == 80


def test_replace_media_and_relink(ex):
    ex.execute(A.ReplaceMedia("i1", "new.mp4"))
    assert _find(ex).src == "new.mp4"
    ex.execute(A.RelinkTimelineItem("i1", source_asset_id="a9", source_revision="r2"))
    it = _find(ex)
    assert it.sourceAssetId == "a9"
    assert it.sourceRevision == "r2"


def test_update_watermark(ex):
    ex.execute(A.UpdateWatermark(enabled=True, text="brand", opacity=0.5))
    wm = active_timeline(ex.state).watermark
    assert wm.enabled is True
    assert wm.text == "brand"
    assert wm.opacity == 0.5


def test_set_item_denoise(ex):
    ex.execute(A.SetItemDenoise("i1", "denoised.wav", 90))
    assert _find(ex).denoisedSrc == "denoised.wav"
    assert _find(ex).denoiseStrength == 90


def test_reframe_keyframes(ex):
    ex.execute(A.SetReframeKeyframe("i1", 0, 0.5, 0.5, 1.5))
    ex.execute(A.SetReframeKeyframe("i1", 50, 0.6, 0.4, 2.0))
    kfs = _find(ex).reframeKeyframes
    assert [k.frame for k in kfs] == [0, 50]
    ex.execute(A.RemoveReframeKeyframe("i1", 0))
    assert [k.frame for k in _find(ex).reframeKeyframes] == [50]


# ── 项目级 ─────────────────────────────────────────────────────────────────

def test_timeline_crud(ex):
    tl = Timeline(id="tl2", name="第二时间线", order=1)
    ex.execute(P.TimelineCreate(tl))
    assert len(ex.state.timelines) == 2

    ex.execute(P.TimelineSwitch("tl2"))
    assert ex.state.activeTimelineId == "tl2"

    ex.execute(P.TimelineRename("tl2", "改名"))
    assert next(t for t in ex.state.timelines if t.id == "tl2").name == "改名"

    ex.execute(P.TimelineDelete("tl2"))
    assert len(ex.state.timelines) == 1
    assert ex.state.activeTimelineId == "tl1"   # 删除激活时间线后回退


def test_timeline_duplicate_and_retarget_and_hidden(ex):
    ex.execute(P.TimelineDuplicate("tl1", "tl2", "副本"))
    assert len(ex.state.timelines) == 2

    ex.execute(P.TimelineRetarget("tl2", 1080, 1920))
    t = next(t for t in ex.state.timelines if t.id == "tl2")
    assert t.width == 1080 and t.height == 1920

    ex.execute(P.TimelineSetHidden("tl2", True))
    assert next(t for t in ex.state.timelines if t.id == "tl2").hidden is True


def test_pool_folder_and_asset(ex):
    e = Executor(default_project())
    e.execute(A.AddAsset(MediaAsset(id="a1", name="x.mp4", kind="video")))
    e.execute(A.PoolCreateFolder(MediaFolder(id="f1", name="音乐")))

    e.execute(P.PoolRenameFolder("f1", "背景音乐"))
    assert e.state.mediaFolders[0].name == "背景音乐"

    e.execute(P.PoolUpdateAsset("a1", {"favorite": True}))
    assert e.state.assets[0].favorite is True

    e.execute(P.PoolRelinkAsset("a1", "new_src.mp4"))
    assert e.state.assets[0].src == "new_src.mp4"

    e.execute(P.PoolDeleteFolder("f1"))
    assert len(e.state.mediaFolders) == 0


def test_pool_canonicalize_asset(ex):
    ex.execute(A.AddAsset(MediaAsset(id="dup", name="dup.mp4", kind="video")))
    ex.execute(A.AddAsset(MediaAsset(id="canon", name="canon.mp4", kind="video")))
    ex.execute(A.RelinkTimelineItem("i1", source_asset_id="dup"))
    ex.execute(P.PoolCanonicalizeAsset("dup", "canon"))
    assert _find(ex).sourceAssetId == "canon"
    assert all(a.id != "dup" for a in ex.state.assets)


def test_design_style_and_full_state(ex):
    ex.execute(P.SetDesignStyle({"brand": "acme"}))
    assert ex.state.designStyle == {"brand": "acme"}
    ex.execute(P.PatchDesignStyle({"color": "red"}))
    assert ex.state.designStyle == {"brand": "acme", "color": "red"}

    ex.execute(P.SetFullState({"fps": 25, "width": 720}))
    tl = active_timeline(ex.state)
    assert tl.fps == 25 and tl.width == 720
