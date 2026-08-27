"""Agent 循环端到端测试（mock 模式，无 Key 可跑）。"""
from app.agent.loop import run_agent
from app.commands.base import Executor
from app.domain.timeline import active_timeline, default_project
from app.llm import MockLlm


def _tool_names(events):
    return [ev["data"]["name"] for ev in events if ev["event"] == "tool_call"]


def test_mock_loop_full_workflow():
    ex = Executor(default_project())
    events = list(run_agent("加两个片段、一个转场和一个字幕", ex, MockLlm()))

    names = _tool_names(events)
    assert "add_clip" in names
    assert "add_transition" in names
    assert "edit_captions" in names

    tl = active_timeline(ex.state)
    assert len(tl.items) == 2
    assert len(tl.transitions) == 1
    assert tl.captions is not None
    assert not any(ev["event"] == "error" for ev in events)
    assert events[-1]["event"] == "done"


def test_mock_loop_no_caption_when_not_asked():
    ex = Executor(default_project())
    events = list(run_agent("加两个片段", ex, MockLlm()))
    names = _tool_names(events)
    assert "edit_captions" not in names
    assert "add_transition" not in names
    assert len(active_timeline(ex.state).items) == 2


def test_undo_after_loop():
    ex = Executor(default_project())
    list(run_agent("加两个片段", ex, MockLlm()))
    assert len(active_timeline(ex.state).items) == 2
    ex.undo()
    assert len(active_timeline(ex.state).items) == 1
