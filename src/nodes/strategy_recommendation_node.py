"""Procurement strategy ranking workflow node."""

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.forecast_strategy_service import StrategyRecommendationNode as StrategyService


class StrategyRecommendationNode(FunctionNode):
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self, risk_appetite: str = "moderate") -> None:
        super().__init__()
        self._risk_appetite = risk_appetite

    def execute(self, state: AgentState) -> dict[str, Any]:
        emit_trace_event("strategy_recommendation_started", {"risk_appetite": self._risk_appetite}, state)
        try:
            result = StrategyService().execute(
                float(state.get("exposure_mwh", 0.0) or 0.0),
                state.get("price_band_low"),
                state.get("price_band_high"),
                state.get("price_band_moving_average"),
                risk_appetite=self._risk_appetite,
            )
        except (TypeError, ValueError) as exc:
            return {"status": AgentStatus.ERROR.value, "error_log": [f"StrategyRecommendationNode: {exc}"]}
        emit_trace_event("strategy_recommendation_generated", {"risk_appetite": self._risk_appetite}, state)
        return {"strategy_options": result["strategy_options"], "status": AgentStatus.SUCCESS.value}
