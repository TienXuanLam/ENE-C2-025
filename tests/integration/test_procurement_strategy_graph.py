# ENE-C2-025 — Integration Tests: full graph compile + invoke
#
# Requires the `framework`/`shared` packages (agenticstar-agentcore wheel).
# No secrets binding needed — this template declares requires.secrets: []
# (config/agent.yaml) and no code path under test calls ctx.secrets.require().

import pytest
from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel

from src.graph.graph import WholesaleElectricityProcurementStrategyAgent


@pytest.fixture
def agent():
    a = WholesaleElectricityProcurementStrategyAgent(
        config={"max_retry": 1, "forecast_window": 20, "risk_appetite": "moderate"}
    )
    a.compile()
    return a


def _ctx() -> InvocationContext:
    return InvocationContext(
        session_id="integration-test-session",
        caller_trust_level=TrustLevel.VERIFIED_EXTERNAL,
    )


def test_full_pipeline_success(agent):
    result = agent.invoke(
        "Analyze my procurement position for next-day electricity purchasing.",
        ctx=_ctx(),
        input_context={
            "contracted_volume_mwh": 1.0,
            "contract_period": "next_day",
            "jepx_price_order": "oldest_first",
            "demand_forecast_mwh": [0.05] * 24,
            "jepx_prices": [20.0, 21.0, 19.0, 22.0, 20.0] * 5,
        },
    )

    assert result["status"] == "success"
    assert result["output"] is not None
    assert "InitializeNode" in result["node_history"]
    assert "FinalizeNode" in result["node_history"]


def test_full_pipeline_error_on_negative_contracted_volume(agent):
    result = agent.invoke(
        "Analyze my procurement position.",
        ctx=_ctx(),
        input_context={
            "contracted_volume_mwh": -1.0,
            "contract_period": "next_day",
            "jepx_price_order": "oldest_first",
            "demand_forecast_mwh": [0.05],
            "jepx_prices": [20.0],
        },
    )

    assert result["status"] == "error"


def test_full_pipeline_blocks_anonymous_caller(agent):
    anonymous_ctx = InvocationContext(
        session_id="integration-test-session-anon",
        caller_trust_level=TrustLevel.ANONYMOUS,
    )
    result = agent.invoke(
        "Analyze my procurement position.",
        ctx=anonymous_ctx,
        input_context={
            "contracted_volume_mwh": 1.0,
            "contract_period": "next_day",
            "jepx_price_order": "oldest_first",
            "demand_forecast_mwh": [0.05] * 24,
            "jepx_prices": [20.0, 21.0, 22.0],
        },
    )

    assert result["status"] == "error"


def test_full_pipeline_with_conservative_risk_appetite():
    conservative_agent = WholesaleElectricityProcurementStrategyAgent(
        config={"max_retry": 1, "risk_appetite": "conservative"}
    )
    conservative_agent.compile()

    result = conservative_agent.invoke(
        "Analyze my procurement position.",
        ctx=_ctx(),
        input_context={
            "contracted_volume_mwh": 1.0,
            "contract_period": "next_week",
            "jepx_price_order": "oldest_first",
            "demand_forecast_mwh": [0.05] * 168,
            "jepx_prices": [20.0, 21.0, 19.0, 22.0, 20.0] * 5,
        },
    )

    assert result["status"] == "success"
