# ENE-C2-025 — Unit Tests: PostProcessNode dispatcher (real FunctionNode boundary)
#
# Requires the `framework`/`shared` packages (agenticstar-agentcore wheel).
# No secrets binding needed — this template declares requires.secrets: []
# (config/agent.yaml) and no code path under test calls ctx.secrets.require().

import json

import pytest
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel

from src.nodes.post_process_node import PostProcessNode


def _base_state(**overrides) -> dict:
    state = {
        "contract_period": "next_day",
        "exposure_mwh": 200.0,
        "exposure_value_jpy": 4000.0,
        "coverage_ratio": 0.83,
        "price_band_low": 15.0,
        "price_band_high": 25.0,
        "price_band_moving_average": 20.0,
        "strategy_options": json.dumps({"options": [{"option": "buy_now"}], "risk_appetite": "moderate"}),
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
    return PostProcessNode()


class TestPostProcessNodeExecute:
    def test_success_path(self, node):
        result = node.execute(_base_state())
        assert result["status"] == AgentStatus.SUCCESS.value
        assert "decision-support document" in result["executive_summary"]
        assert result["formatted_output"]["contract_period"] == "next_day"
        assert len(result["formatted_output"]["risk_table"]) == 1


class TestPostProcessNodeTrustGate:
    def test_blocks_anonymous_caller(self, node):
        state = _base_state(caller_trust_level=TrustLevel.ANONYMOUS.value)
        result = node(state)  # __call__ — S-1 boundary
        assert result["status"] == AgentStatus.ERROR.value


class TestPostProcessNodeS3Gate:
    def test_extra_gate_raises_when_disclaimer_missing(self, node):
        with pytest.raises(RuntimeError, match="disclaimer"):
            node._extra_security_gate_output({"executive_summary": "no disclaimer here", "formatted_output": {}})

    def test_extra_gate_raises_on_sensitive_detail_marker_in_summary(self, node):
        with pytest.raises(RuntimeError, match="sensitive trading-strategy detail"):
            node._extra_security_gate_output(
                {
                    "executive_summary": (
                        "This report is a decision-support document and does not "
                        "constitute investment advice under the Financial Instruments "
                        "and Exchange Act. internal_margin: 5%"
                    ),
                    "formatted_output": {},
                }
            )

    def test_extra_gate_raises_on_sensitive_detail_marker_in_risk_table_timing(self, node):
        # F-04: scan is scoped to executive_summary + risk_table[].recommended_timing,
        # not the entire formatted_output blob.
        with pytest.raises(RuntimeError, match="sensitive trading-strategy detail"):
            node._extra_security_gate_output(
                {
                    "executive_summary": (
                        "This report is a decision-support document and does not "
                        "constitute investment advice under the Financial Instruments "
                        "and Exchange Act."
                    ),
                    "formatted_output": {
                        "risk_table": [{"option": "buy_now", "recommended_timing": "trading_policy: aggressive"}]
                    },
                }
            )

    def test_extra_gate_does_not_scan_unrelated_formatted_output_fields(self, node):
        # F-04: a marker string appearing in a non-scanned field (e.g. a
        # numeric/enum field or any field other than executive_summary /
        # risk_table[].recommended_timing) must NOT trigger a false positive.
        result = node._extra_security_gate_output(
            {
                "executive_summary": (
                    "This report is a decision-support document and does not "
                    "constitute investment advice under the Financial Instruments "
                    "and Exchange Act."
                ),
                "formatted_output": {"contract_period": "cost_basis_2026"},
            }
        )
        assert "formatted_output" in result

    def test_extra_gate_passes_clean_output(self, node):
        result = node._extra_security_gate_output(
            {
                "executive_summary": (
                    "This report is a decision-support document and does not "
                    "constitute investment advice under the Financial Instruments "
                    "and Exchange Act."
                ),
                "formatted_output": {"risk_table": [{"option": "buy_now", "recommended_timing": "immediate"}]},
            }
        )
        assert "formatted_output" in result
