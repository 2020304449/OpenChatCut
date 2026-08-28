"""A-3 B 类工程化测试：流式 / 验收 / 压缩 / 持久化。"""
import os

import pytest

from app.agent.loop import _compact, _estimate_tokens, run_agent
from app.commands import actions as A
from app.commands.base import Executor
from app.domain.captions import CaptionCue, CaptionsData
from app.domain.item import TimelineItem
from app.domain.timeline import active_timeline, default_project
from app.llm import MockLlm
from app.persist import load_project, project_from_dict, save_project


def test_mock_stream_chat_emits_tool_calls_and_text():
    llm = MockLlm()
    events = list(llm.stream_chat([{"role": "user", "content": "加两个片段"}], []))
    # 第一轮产出 tool_calls + done
    kinds = [e["type"] for e in events]
    assert "tool_calls" in kinds
    assert kinds[-1] == "done"


def test_run_agent_mock_full_flow():
    ex = Executor(default_project())
    events = list(run_agent("加两个片段和一个字幕", ex, MockLlm()))
    tool_names = [e["data"]["name"] for e in events if e["event"] == "tool_call"]
    assert "add_clip" in tool_names
    assert "edit_captions" in tool_names
    assert events[-1]["event"] == "done"
    assert len(active_timeline(ex.state).items) == 2


def test_estimate_and_compact():
    small = [{"role": "user", "content": "hi"}]
    assert _estimate_tokens(small) < 12000
    assert _compact(small) == small

    big = [{"role": "system", "content": "x" * 100}] + \
          [{"role": "user", "content": "y" * 2000} for _ in range(30)]
    assert _estimate_tokens(big) > 12000
    compacted = _compact(big)
    assert len(compacted) < len(big)
    assert compacted[0]["role"] == "system"          # 保留 system
    assert "已压缩" in compacted[1]["content"]        # 摘要标记


def test_persist_roundtrip(tmp_path):
    ex = Executor(default_project())
    ex.execute(A.AddItem(TimelineItem(id="i1", track="V1", startFrame=0,
                                      durationInFrames=90, name="A", kind="video", volume=0.5)))
    ex.execute(A.SetCaptions(CaptionsData(items=(CaptionCue(0, 90, "你好"),))))

    p = str(tmp_path / "project-store.sqlite3")
    save_project(ex.state, p)
    loaded = load_project(p)
    assert loaded is not None
    assert loaded.activeTimelineId == ex.state.activeTimelineId
    assert active_timeline(loaded).items[0].name == "A"
    assert active_timeline(loaded).items[0].volume == 0.5
    assert active_timeline(loaded).captions.items[0].text == "你好"


def test_project_from_dict_missing_fields_defaults():
    doc = project_from_dict({"timelines": [], "activeTimelineId": ""})
    assert doc.version == 1
    assert doc.assets == ()
    assert doc.timelines == ()
