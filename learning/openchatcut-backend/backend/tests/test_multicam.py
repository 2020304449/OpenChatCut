"""A-3 边角命令测试：轨道收紧 / 画布 / 多机位 / 联动组。"""
import pytest

from app.agent.registry import ToolContext, build_registry
from app.commands import actions as A
from app.commands import multicam_actions as MA
from app.commands.base import Executor
from app.domain.item import TimelineItem
from app.domain.multicam import MulticamAngle, MulticamGroup, TimelineLinkGroup
from app.domain.timeline import active_timeline, default_project


def make_item(item_id, start, dur):
    return TimelineItem(id=item_id, track="V1", startFrame=start, durationInFrames=dur,
                        name=item_id, kind="video")


@pytest.fixture
def ex():
    e = Executor(default_project())
    e.execute(A.AddItem(make_item("i1", 0, 90)))
    e.execute(A.AddItem(make_item("i2", 150, 90)))   # 有 60 帧空隙
    return e


def test_track_tighten(ex):
    ex.execute(MA.TrackTighten("V1"))
    items = sorted((i for i in active_timeline(ex.state).items if i.track == "V1"),
                   key=lambda i: i.startFrame)
    assert [i.startFrame for i in items] == [0, 90]   # i2 从 150 收紧到 90


def test_set_canvas(ex):
    ex.execute(MA.SetCanvas(1080, 1920, "cover"))
    tl = active_timeline(ex.state)
    assert tl.width == 1080 and tl.height == 1920 and tl.fit == "cover"


def test_multicam_groups_and_decision(ex):
    group = MulticamGroup(
        id="mc1", referenceAngleId="a1", masterAngleId="a1",
        angles=(MulticamAngle(id="a1", itemId="i1", label="机位A"),
                MulticamAngle(id="a2", itemId="i2", label="机位B")),
    )
    ex.execute(MA.SetMulticamGroups((group,)))
    assert len(active_timeline(ex.state).multicamGroups) == 1

    ex.execute(MA.AddMulticamDecision("mc1", 30, 60, "a2"))
    decisions = active_timeline(ex.state).multicamGroups[0].decisions
    assert len(decisions) == 1 and decisions[0].angleId == "a2"


def test_link_groups(ex):
    grp = TimelineLinkGroup(id="lg1", itemIds=("i1", "i2"), anchorItemId="i1", mode="linked")
    ex.execute(MA.AddLinkGroup(grp))
    assert len(active_timeline(ex.state).linkGroups) == 1

    ex.execute(MA.SetLinkGroups(()))
    assert len(active_timeline(ex.state).linkGroups) == 0


def test_aspect_ratio_and_change_cam_tools(ex):
    reg = build_registry()
    ctx = ToolContext(ex)
    r = reg.execute("set_aspect_ratio", {"width": 720, "height": 1280}, ctx)
    assert r["ok"] is True
    assert active_timeline(ex.state).width == 720

    r = reg.execute("change_cam", {"action": "set_groups", "groups": [
        {"id": "mc1", "referenceAngleId": "a1", "masterAngleId": "a1",
         "angles": [{"id": "a1", "itemId": "i1", "label": "A"}]}
    ]}, ctx)
    assert r["ok"] is True


def test_manage_link_group_tool(ex):
    reg = build_registry()
    ctx = ToolContext(ex)
    r = reg.execute("manage_link_group", {"action": "add",
                                          "group": {"itemIds": ["i1", "i2"], "anchorItemId": "i1", "mode": "linked"}}, ctx)
    assert r["ok"] is True
    assert len(active_timeline(ex.state).linkGroups) == 1
