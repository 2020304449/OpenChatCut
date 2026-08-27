"""数据模型序列化与默认工程测试。"""
from dataclasses import asdict

from app.domain.item import ClipTransform, TimelineItem
from app.domain.timeline import (
    active_timeline,
    default_project,
    project_to_dict,
)


def test_default_project():
    doc = default_project()
    assert doc.activeTimelineId == "tl1"
    assert len(doc.timelines) == 1
    tl = active_timeline(doc)
    assert tl.fps == 30
    assert tl.width == 1920 and tl.height == 1080


def test_timeline_item_serialization():
    item = TimelineItem(id="i1", track="V1", startFrame=0, durationInFrames=90,
                        name="A", kind="video", volume=1.0)
    d = asdict(item)
    assert d["id"] == "i1"
    assert d["startFrame"] == 0
    assert d["durationInFrames"] == 90
    assert d["kind"] == "video"
    assert d["volume"] == 1.0


def test_nested_serialization_roundtrip():
    item = TimelineItem(id="i1", track="V1", startFrame=0, durationInFrames=90,
                        name="A", kind="video",
                        transform=ClipTransform(scale=1.5, rotation=30))
    d = asdict(item)
    assert d["transform"]["scale"] == 1.5
    assert d["transform"]["rotation"] == 30


def test_project_to_dict_nested():
    doc = default_project()
    d = project_to_dict(doc)
    assert d["activeTimelineId"] == "tl1"
    assert isinstance(d["timelines"], list)
    assert d["timelines"][0]["id"] == "tl1"
    assert d["timelines"][0]["fps"] == 30
