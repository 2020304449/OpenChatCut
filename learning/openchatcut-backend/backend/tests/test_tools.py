"""工具层测试：工具覆盖、execute 正确性、schema 导出、非法参数容错。"""
from app.agent.registry import ToolContext, build_registry
from app.commands.base import Executor
from app.domain.timeline import active_timeline, default_project


def test_core_tools_present():
    names = [t.name for t in build_registry().list()]
    for n in [
        "read_timeline", "read_project", "edit_track", "add_clip", "remove_clip",
        "clear_timeline", "duplicate_clip", "split_clip", "move_clip",
        "set_clip_timing", "update_clip_props", "set_clip_volume", "set_clip_fade",
        "set_clip_transform", "set_clip_filters", "set_clip_speed", "set_clip_zoom",
        "set_clip_effects", "add_transition", "edit_transition", "edit_captions",
        "set_keyframe", "remove_keyframe", "clear_keyframes", "manage_markers",
        "select_clips", "manage_media_pool", "undo_last_change", "redo_last_change",
    ]:
        assert n in names, f"missing tool {n}"


def test_add_clip_via_registry():
    ex = Executor(default_project())
    ctx = ToolContext(ex)
    r = build_registry().execute(
        "add_clip",
        {"label": "A", "track": "V1", "startFrame": 0, "durationInFrames": 90, "kind": "video"},
        ctx,
    )
    assert r["ok"] is True
    assert len(active_timeline(ex.state).items) == 1


def test_edit_captions_via_registry():
    ex = Executor(default_project())
    ctx = ToolContext(ex)
    r = build_registry().execute(
        "edit_captions", {"action": "set", "enabled": True, "texts": ["你好", "世界"]}, ctx
    )
    assert r["ok"] is True
    assert len(active_timeline(ex.state).captions.items) == 2


def test_invalid_args_returns_error():
    ex = Executor(default_project())
    ctx = ToolContext(ex)
    r = build_registry().execute("add_clip", {"label": "A"}, ctx)  # 缺 startFrame/durationInFrames
    assert r["ok"] is False
    assert "error" in r


def test_missing_item_returns_error():
    ex = Executor(default_project())
    ctx = ToolContext(ex)
    for name, args in [
        ("remove_clip", {"itemId": "nope"}),
        ("move_clip", {"itemId": "nope", "startFrame": 0}),
        ("set_clip_volume", {"itemId": "nope", "volume": 0.5}),
        ("set_keyframe", {"itemId": "nope", "prop": "x", "frame": 0, "value": 1.0}),
    ]:
        r = build_registry().execute(name, args, ctx)
        assert r["ok"] is False, f"{name} 应返回 ok:False"
        assert "not found" in r["error"]


def test_unknown_tool_returns_error():
    ex = Executor(default_project())
    ctx = ToolContext(ex)
    r = build_registry().execute("no_such_tool", {}, ctx)
    assert r["ok"] is False


def test_tool_schemas_export():
    reg = build_registry()
    schemas = reg.schemas()
    assert len(schemas) == len(reg.list())
    first = schemas[0]
    assert first["type"] == "function"
    assert "name" in first["function"]
    assert "parameters" in first["function"]


def test_clean_script_via_registry():
    from app.commands.actions import AddItem
    from app.domain.item import TimelineItem
    from app.domain.transcript import TranscriptWord
    ex = Executor(default_project())
    words = (TranscriptWord(text="呃", startMs=0, endMs=200),
             TranscriptWord(text="大家好", startMs=200, endMs=800))
    ex.execute(AddItem(TimelineItem(id="i1", track="V1", startFrame=0,
                                    durationInFrames=90, name="A", kind="video", transcript=words)))
    ctx = ToolContext(ex)
    r = build_registry().execute("clean_script", {"itemId": "i1", "removeFillers": True}, ctx)
    assert r["ok"] is True
    item = next(i for i in active_timeline(ex.state).items if i.id == "i1")
    assert item.deletedWordIdx == (0,)


def test_manage_timelines_via_registry():
    ex = Executor(default_project())
    ctx = ToolContext(ex)
    r = build_registry().execute("manage_timelines", {"action": "create", "name": "新时间线"}, ctx)
    assert r["ok"] is True
    assert len(ex.state.timelines) == 2
