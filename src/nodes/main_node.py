"""AgentCore Platform v1.0"""

# Real FunctionNode dispatcher for docs/02_design.md "2+2+1 split" main slot:
#   step 3 - PriceForecastNode.execute()   (numpy statistical, Primary method)
#   step 4 - StrategyRecommendationNode.execute()
# S-1 (required_trust_level), S-4 (emit_trace_event) run here — never inside
# the pure-Python step helpers. No domain S-3 hook on this node — output
# sanitization (commercially sensitive trading-strategy detail, mandatory
# disclaimer) is applied at post_process, the node closest to the caller
# boundary (see docs/02_design.md).

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.forecast_strategy_service import PriceForecastNode, StrategyRecommendationNode


class MainNode(FunctionNode):
    """Step 3-4: statistical price-band forecast, strategy recommendation."""

    # S-1: standard business operation on procurement/market data.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, forecast_window: int = 20, risk_appetite: str = "moderate") -> None:
        self._price_forecast = PriceForecastNode()
        self._strategy_recommendation = StrategyRecommendationNode()
        self._forecast_window = forecast_window
        self._risk_appetite = risk_appetite

    def execute(self, state: AgentState) -> dict[str, Any]:
        jepx_prices = state.get("jepx_prices", "")
        exposure_mwh = state.get("exposure_mwh", 0.0)

        forecast_result = self._price_forecast.execute(jepx_prices, window=self._forecast_window)

        emit_trace_event(
            "price_band_forecast_computed",
            {
                "contract_period": state.get("contract_period", ""),
                "forecast_window": self._forecast_window,
            },
            state,
        )

        strategy_result = self._strategy_recommendation.execute(
            exposure_mwh,
            forecast_result["price_band_low"],
            forecast_result["price_band_high"],
            forecast_result["price_band_moving_average"],
            risk_appetite=self._risk_appetite,
        )

        emit_trace_event(
            "strategy_recommendation_generated",
            {
                "contract_period": state.get("contract_period", ""),
                "risk_appetite": self._risk_appetite,
            },
            state,
        )

        return {
            "price_band_low": forecast_result["price_band_low"],
            "price_band_high": forecast_result["price_band_high"],
            "price_band_moving_average": forecast_result["price_band_moving_average"],
            "price_band_method": forecast_result["price_band_method"],
            "strategy_options": strategy_result["strategy_options"],
            "status": AgentStatus.SUCCESS.value,
        }
