"""agent-runs 健壮性测试：tool-policy 分类 + 审批流。"""
import asyncio

from app.agent_runs.executor import execute_run
from app.agent_runs.policy import classify, requires_approval
from app.agent_runs.store import (
    RunStore,
    ServerRun,
    approve_tool_request,
    claim_tool_request,
    settle_tool_result,
)
from app.domain.timeline import default_project, project_to_dict
from app.llm import MockLlm, ToolCall


def _state():
    return project_to_dict(default_project())


def test_policy_classify():
    assert classify("read_timeline") == "read"
    assert classify("read_project") == "read"
    assert classify("add_clip") == "edit"
    assert classify("submit_image") == "high-risk"
    assert classify("submit_export") == "high-risk"
    # 服务/只读类不算 high-risk
    assert requires_approval("submit_image") is True
    assert requires_approval("submit_export") is True
    assert requires_approval("add_clip") is False
    assert requires_approval("read_timeline") is False
    assert requires_approval("transcribe_track") is False


def test_approval_flow_approve():
    async def scenario():
        run = ServerRun(id="r1", message="生成一张图片", initial_state=_state())
        events = []
        async for ev in execute_run(run, "生成一张图片", MockLlm(), _state()):
            events.append(ev)
            if ev["event"] == "approval_request":
                d = ev["data"]
                assert approve_tool_request(run, d["toolCallId"], "approved")["ok"] is True
            elif ev["event"] == "tool_request":
                d = ev["data"]
                claim_tool_request(run, d["toolCallId"], "claim-1")
                settle_tool_result(run, d["toolCallId"], "claim-1", d["argsDigest"], {"ok": True})

        assert any(e["event"] == "approval_request" for e in events)
        # approve 后 submit_image 仍产生 tool_request
        assert any(e["event"] == "tool_request" and e["data"]["name"] == "submit_image" for e in events)
        assert events[-1]["event"] == "done"
    asyncio.run(scenario())


def test_approval_flow_reject_skips_tool():
    async def scenario():
        run = ServerRun(id="r1", message="生成一张图片", initial_state=_state())
        events = []
        async for ev in execute_run(run, "生成一张图片", MockLlm(), _state()):
            events.append(ev)
            if ev["event"] == "approval_request":
                d = ev["data"]
                approve_tool_request(run, d["toolCallId"], "rejected")
            elif ev["event"] == "tool_request":
                d = ev["data"]
                claim_tool_request(run, d["toolCallId"], "claim-1")
                settle_tool_result(run, d["toolCallId"], "claim-1", d["argsDigest"], {"ok": True})

        # reject 后 submit_image 不产生 tool_request，而是 rejected 的 tool_result
        assert not any(e["event"] == "tool_request" and e["data"]["name"] == "submit_image" for e in events)
        rejected = [e for e in events if e["event"] == "tool_result" and e["data"].get("rejected")]
        assert len(rejected) == 1
        assert events[-1]["event"] == "done"
    asyncio.run(scenario())


def test_approval_wrong_state_rejected():
    """非 pending_approval 态不可审批。"""
    async def scenario():
        from app.agent_runs.store import register_tool_request
        run = ServerRun(id="r1", message="x", initial_state=_state())
        req = register_tool_request(run, "tc1", "add_clip", {"track": "V1"})  # 普通态 pending
        assert approve_tool_request(run, "tc1", "approved")["ok"] is False
        assert req.status == "pending"
    asyncio.run(scenario())


class VerifyMockLlm:
    """模拟 acceptance-loop：加片段 → 触发验收 → 修正再加 → 再次验收 → 通过。"""

    def __init__(self):
        self._steps = [
            [ToolCall("t1", "add_clip", {"track": "V1"})],   # 第 1 轮：加片段
            [],                                              # 第 2 轮：触发验收
            [ToolCall("t2", "add_clip", {"track": "V1"})],   # 第 3 轮：验收后修正
            [],                                              # 第 4 轮：再次触发验收
            [],                                              # 第 5 轮：验收通过
        ]
        self._idx = 0

    def stream_chat(self, messages, tools):
        calls = self._steps[self._idx] if self._idx < len(self._steps) else []
        self._idx += 1
        if calls:
            yield {"type": "tool_calls", "calls": calls}
        else:
            yield {"type": "text", "delta": "已验收"}
        yield {"type": "done"}


def test_acceptance_loop_retry_after_verification():
    """工具执行后进入验收，LLM 判定未达标会继续修正，最终通过。"""
    async def scenario():
        run = ServerRun(id="r1", message="加片段", initial_state=_state())
        events = []
        async for ev in execute_run(run, "加片段", VerifyMockLlm(), _state()):
            events.append(ev)
            if ev["event"] == "tool_request":
                d = ev["data"]
                claim_tool_request(run, d["toolCallId"], "claim-1")
                settle_tool_result(run, d["toolCallId"], "claim-1", d["argsDigest"], {"ok": True})

        requests = [e for e in events if e["event"] == "tool_request"]
        assert len(requests) == 2          # 初次 + 修正
        assert events[-1]["event"] == "done"
    asyncio.run(scenario())


def test_recovery_persist_and_load(tmp_path):
    """run 持久化到 SQLite，新 store 能恢复快照。"""
    db = str(tmp_path / "runs.sqlite3")
    store = RunStore(db)
    run = store.create("加片段", _state())
    store.persist(run)

    store2 = RunStore(db)   # 模拟重启：新 store 从同一 DB load
    loaded = store2.load()
    assert len(loaded) == 1
    assert loaded[0].id == run.id
    assert loaded[0].message == "加片段"
    assert loaded[0].state == "pending"


def test_metrics_recorded():
    """跑完 run 后 metrics 记录迭代/工具调用/耗时。"""
    async def scenario():
        run = ServerRun(id="r1", message="加两个片段", initial_state=_state())
        async for ev in execute_run(run, "加两个片段", MockLlm(), _state()):
            if ev["event"] == "tool_request":
                d = ev["data"]
                claim_tool_request(run, d["toolCallId"], "claim-1")
                settle_tool_result(run, d["toolCallId"], "claim-1", d["argsDigest"], {"ok": True})

        m = run.metrics
        assert m.tool_calls >= 2          # add_clip x2
        assert m.iterations > 0
        assert m.duration_ms is not None
    asyncio.run(scenario())


class CaptureLlm:
    """捕获 system prompt，用于验证能力协商裁剪工具面。"""

    def __init__(self):
        self.system_prompt = ""

    def stream_chat(self, messages, tools):
        self.system_prompt = messages[0]["content"]
        yield {"type": "done"}


def test_capability_filters_tool_face():
    """传 supported_tools 子集时，system prompt 只含子集工具。"""
    async def scenario():
        run = ServerRun(id="r1", message="加片段", initial_state=_state(), supported_tools=["add_clip"])
        llm = CaptureLlm()
        async for _ in execute_run(run, "加片段", llm, _state()):
            pass
        assert "add_clip" in llm.system_prompt
        assert "read_timeline" not in llm.system_prompt
    asyncio.run(scenario())
