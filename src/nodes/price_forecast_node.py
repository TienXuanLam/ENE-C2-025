"""Statistical price-band workflow node."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.forecast_strategy_service import PriceForecastNode as PriceForecastService


class PriceForecastNode(FunctionNode):
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, window: int = 20) -> None:
        super().__init__()
        self._window = window

    def execute(self, state: AgentState) -> dict[str, Any]:
        emit_trace_event("price_band_forecast_started", {"window": self._window}, state)
        try:
            envelope = json.loads(str(state.get("user_input", "")))
            result = PriceForecastService().execute(str(envelope["jepx_prices"]), window=self._window)
        except (KeyError, TypeError, ValueError) as exc:
            return {"status": AgentStatus.ERROR.value, "error_log": [f"PriceForecastNode: {exc}"]}
        emit_trace_event("price_band_forecast_computed", {"method": result["price_band_method"]}, state)
        return {
            "price_band_low": result["price_band_low"],
            "price_band_high": result["price_band_high"],
            "price_band_moving_average": result["price_band_moving_average"],
            "price_band_method": result["price_band_method"],
            "status": AgentStatus.SUCCESS.value,
        }
