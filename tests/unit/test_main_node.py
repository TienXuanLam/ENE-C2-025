# ENE-C2-025 — Unit Tests: MainNode dispatcher (real FunctionNode boundary)
#
# Requires the `framework`/`shared` packages (agenticstar-agentcore wheel).
# No secrets binding needed — this template declares requires.secrets: []
# (config/agent.yaml) and no code path under test calls ctx.secrets.require().

import json

import pytest
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.main_node import MainNode


def _base_state(**overrides) -> dict:
    state = {
        "contract_period": "next_day",
        "jepx_prices": json.dumps([20.0, 21.0, 19.0, 22.0, 20.0] * 5),
        "exposure_mwh": 20.0,
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
    return MainNode()


class TestMainNodeExecute:
    def test_success_path(self, node):
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["price_band_method"] == "moving_average_bollinger_bands"
        options = json.loads(result["strategy_options"])["options"]
        assert len(options) == 3

    def test_insufficient_price_data_still_succeeds(self, node):
        state = _base_state(jepx_prices=json.dumps([]))
        result = node.execute(state)
        assert result["status"] == AgentStatus.SUCCESS.value
        assert result["price_band_method"] == "insufficient_data"


class TestMainNodeConfig:
    def test_forecast_window_and_risk_appetite_are_applied(self):
        node = MainNode(forecast_window=3, risk_appetite="conservative")
        state = _base_state(jepx_prices=json.dumps([10.0, 20.0, 30.0, 40.0, 50.0]))
        result = node.execute(state)
        options = json.loads(result["strategy_options"])
        assert options["risk_appetite"] == "conservative"


class TestMainNodeTrustGate:
    def test_blocks_anonymous_caller(self, node):
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = node(state)  # __call__ — S-1 boundary
        assert result["status"] == AgentStatus.ERROR.value


class TestMainNodeContract:
    def test_execute_method_signature(self):
        """Node contract: Node must implement execute(state) not _invoke_impl.

        Canonical contract:
          - Override: execute(self, state: AgentState) -> dict
          - PROHIBITED: _invoke_impl(), process() override
        """
        import inspect

        assert hasattr(MainNode, "execute"), "MainNode must implement execute()"

        sig = inspect.signature(MainNode.execute)
        params = list(sig.parameters.keys())
        assert len(params) >= 2, f"execute() must accept (self, state), got params: {params}"
        assert params[1] == "state", f"Second parameter must be 'state', got '{params[1]}'"

        assert (
            "_invoke_impl" not in MainNode.__dict__
        ), "_invoke_impl() must not be defined in MainNode — use execute() instead"
