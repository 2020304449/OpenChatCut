"""agent-runs claim/settle 协议端到端测试。"""
import asyncio

from app.agent_runs.executor import execute_run
from app.agent_runs.store import (
    ServerRun,
    claim_tool_request,
    register_tool_request,
    settle_tool_result,
)
from app.domain.timeline import default_project, project_to_dict
from app.llm import MockLlm


def _state():
    return project_to_dict(default_project())


def test_claim_settle_full_flow():
    async def scenario():
        run = ServerRun(id="r1", message="加两个片段", initial_state=_state())
        events = []
        async for ev in execute_run(run, "加两个片段", MockLlm(), _state()):
            events.append(ev)
            if ev["event"] == "tool_request":
                d = ev["data"]
                assert claim_tool_request(run, d["toolCallId"], "claim-1")["ok"] is True
                r = settle_tool_result(run, d["toolCallId"], "claim-1", d["argsDigest"],
                                       {"ok": True, "applied": True})
                assert r["ok"] is True

        assert events[-1]["event"] == "done"
        requests = [e for e in events if e["event"] == "tool_request"]
        results = [e for e in events if e["event"] == "tool_result"]
        assert len(requests) >= 1
        assert len(results) == len(requests)  # 每个 request 都得到结算
    asyncio.run(scenario())


def test_settle_claim_mismatch_rejected():
    async def scenario():
        run = ServerRun(id="r1", message="x", initial_state=_state())
        req = register_tool_request(run, "tc1", "add_clip", {"track": "V1"})
        claim_tool_request(run, "tc1", "claim-1")
        # 错误 claimId → 拒绝
        assert settle_tool_result(run, "tc1", "wrong-claim", req.args_digest, {"ok": True})["ok"] is False
        # 正确 claimId → 通过
        assert settle_tool_result(run, "tc1", "claim-1", req.args_digest, {"ok": True})["ok"] is True
        assert await req.future == {"ok": True}
    asyncio.run(scenario())


def test_settle_args_digest_mismatch_rejected():
    async def scenario():
        run = ServerRun(id="r1", message="x", initial_state=_state())
        register_tool_request(run, "tc1", "add_clip", {"track": "V1"})
        claim_tool_request(run, "tc1", "claim-1")
        assert settle_tool_result(run, "tc1", "claim-1", "wrong-digest", {"ok": True})["ok"] is False
    asyncio.run(scenario())
