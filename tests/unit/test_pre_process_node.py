# ENE-C2-025 — Unit Tests: PreProcessNode dispatcher (real FunctionNode boundary)
#
# Requires the `framework`/`shared` packages (agenticstar-agentcore wheel).
# No secrets binding needed — this template declares requires.secrets: []
# (config/agent.yaml) and no code path under test calls ctx.secrets.require().

import pytest
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.pre_process_node import PreProcessNode


def _base_state(**overrides) -> dict:
    state = {
        "user_input": "analyze procurement position",
        "input_context": {
            "contracted_volume_mwh": 1.0,
            "contract_period": "next_day",
            "jepx_price_order": "oldest_first",
            "demand_forecast_mwh": [0.05] * 24,
            "jepx_prices": [20.0, 21.0, 22.0],
        },
        "correlation_id": "test-corr",
        "session_id": "test-session",
        "thread_id": "test-thread",
        "trace_id": "",
        "caller_trust_level": TrustLevel.VERIFIED_EXTERNAL.value,
        "caller_id": "",
        "hitl_allowed": True,
        "node_history": [],
        "error_log": [],
    }
    state.update(overrides)
    return state


@pytest.fixture
def node():
    return PreProcessNode()


class TestPreProcessNodeExecute:
    def test_success_path(self, node):
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["contracted_volume_mwh"] == 1.0
        assert result["contract_period"] == "next_day"
        assert "exposure_mwh" not in result

    def test_negative_contracted_volume_errors(self, node):
        state = _base_state(
            input_context={
                "contracted_volume_mwh": -1.0,
                "contract_period": "next_day",
                "demand_forecast_mwh": [0.05],
                "jepx_prices": [20.0],
            }
        )
        result = node.execute(state)
        assert result["status"] == AgentStatus.ERROR.value
        assert len(result["error_log"]) > 0


class TestPreProcessNodeTrustGate:
    def test_blocks_anonymous_caller(self, node):
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = node(state)  # __call__ — S-1 boundary
        assert result["status"] == AgentStatus.ERROR.value

    def test_allows_verified_external_caller(self, node):
        result = node(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value


class TestPreProcessNodeS2Gate:
    def test_extra_gate_rejects_negative_volume(self, node):
        state = _base_state(
            input_context={
                "contracted_volume_mwh": -0.5,
                "contract_period": "next_day",
                "demand_forecast_mwh": [0.05],
                "jepx_prices": [20.0],
            }
        )
        result = node(state)  # goes through _extra_security_gate_input
        assert result["status"] == AgentStatus.ERROR.value
