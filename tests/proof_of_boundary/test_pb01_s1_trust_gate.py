# PB-01: S-1 Trust Gate Boundary
#
# Verifies that BaseNode.__call__() enforces required_trust_level BEFORE
# execute() runs, for all 3 real FunctionNode dispatchers in this template.
# execute() must never be reached when the caller's trust level is insufficient.
#
# Requires `framework`/`shared` (agenticstar-agentcore wheel). No secrets
# binding needed — this template declares requires.secrets: [] (config/agent.yaml)
# and no code path under test calls ctx.secrets.require().

from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.pre_process_node import PreProcessNode
from src.nodes.main_node import MainNode
from src.nodes.post_process_node import PostProcessNode


_DISPATCHERS = [PreProcessNode, MainNode, PostProcessNode]


def _anonymous_state() -> dict:
    return {
        "caller_trust_level": TrustLevel.ANONYMOUS.value,
        "correlation_id": "pb01-test",
        "session_id": "pb01-test",
        "thread_id": "pb01-test",
        "trace_id": "",
        "caller_id": "",
        "hitl_allowed": True,
        "node_history": [],
        "error_log": [],
        "input_context": {},
    }


class TestPB01TrustGateBoundary:
    """All 3 real dispatchers declare required_trust_level=VERIFIED_EXTERNAL."""

    def test_all_dispatchers_require_verified_external(self):
        for cls in _DISPATCHERS:
            assert cls.required_trust_level == TrustLevel.VERIFIED_EXTERNAL, (
                f"{cls.__name__} must declare required_trust_level=VERIFIED_EXTERNAL "
                "(this template performs standard business operations on procurement/"
                "market data, not anonymous public access)"
            )

    def test_anonymous_caller_blocked_before_execute(self, monkeypatch):
        for cls in _DISPATCHERS:
            node = cls()
            execute_called = {"value": False}

            def spy_execute(self, state, _flag=execute_called):
                _flag["value"] = True
                return {"status": AgentStatus.SUCCESS.value}

            monkeypatch.setattr(cls, "execute", spy_execute)

            result = node(_anonymous_state())  # __call__ — S-1 boundary

            assert result["status"] == AgentStatus.ERROR.value, f"{cls.__name__}: ANONYMOUS caller must be denied"
            assert (
                execute_called["value"] is False
            ), f"{cls.__name__}: execute() must NOT run when S-1 denies the caller"
