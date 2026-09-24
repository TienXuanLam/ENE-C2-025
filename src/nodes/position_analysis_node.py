"""Procurement position analysis workflow node."""

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event
from src.services.market_position_service import ProcurementPositionAnalysisNode as PositionAnalysisService


class PositionAnalysisNode(FunctionNode):
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def execute(self, state: AgentState) -> dict[str, Any]:
        emit_trace_event("procurement_position_analysis_started", {}, state)
        try:
            envelope = json.loads(str(state.get("user_input", "")))
            result = PositionAnalysisService().execute(
                float(envelope["contracted_volume_mwh"]),
                str(envelope["demand_forecast_mwh"]),
                str(envelope["jepx_prices"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return {"status": AgentStatus.ERROR.value, "error_log": [f"PositionAnalysisNode: {exc}"]}
        emit_trace_event("procurement_position_analyzed", {"exposure_mwh": result["exposure_mwh"]}, state)
        return {
            "exposure_mwh": result["exposure_mwh"],
            "exposure_value_jpy": result["exposure_value_jpy"],
            "coverage_ratio": result["coverage_ratio"],
            "status": AgentStatus.SUCCESS.value,
        }
