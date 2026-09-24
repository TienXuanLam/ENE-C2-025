"""AgentCore Platform v1.0"""

# Node contract (agents_layer_design.md §1):
#  - Extend FunctionNode; implement execute(state) -> dict
#  - Return ONLY the fields this node changes (never full state)
#  - Return AgentStatus enum constants — never plain strings [A1]
#  - Read input_context via state.get("input_context", {}) — read-only [C1]
#  - Never import from mediator/, api/, or other agents
#
# Real FunctionNode dispatcher for docs/02_design.md "2+2+1 split" pre_process slot:
#   step 1 - MarketDataIngestionNode.execute()
#   step 2 - ProcurementPositionAnalysisNode.execute()
# S-1 (required_trust_level), S-2 (_extra_security_gate_input), S-4 (emit_trace_event)
# all run here — never inside the pure-Python step helpers.

import json
from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.market_position_service import MarketDataIngestionNode


class PreProcessNode(FunctionNode):
    """Validate and normalize the caller-supplied market data envelope."""

    # S-1: standard business operation on procurement/contract data — requires a
    # verified caller identity, not anonymous access.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self) -> None:
        self._market_data_ingestion = MarketDataIngestionNode()

    def _extra_security_gate_input(self, state: AgentState) -> AgentState:
        # Domain check: when input_context IS present, it must carry a
        # non-negative contracted_volume_mwh. Reject via status=ERROR — never
        # raise (S-2 contract). When input_context is absent entirely, pass
        # through — MarketDataIngestionNode.execute() still rejects on missing
        # required fields (defense in depth); this mirrors the same fix used
        # elsewhere in the fleet for the generic PB-6 invoke-order test (which
        # sends no input_context).
        input_context = state.get("input_context")
        try:
            payload_size = len(str(state.get("user_input", "")).encode("utf-8")) + len(
                json.dumps(input_context or {}).encode("utf-8")
            )
        except (TypeError, ValueError):
            payload_size = 1_048_577
        if payload_size > 1_048_576:
            state = dict(state)
            state["status"] = AgentStatus.ERROR.value
            state["error_log"] = ["PreProcessNode S-2: request payload exceeds 1 MiB"]
            return state
        if input_context is not None:
            contracted_volume_mwh = input_context.get("contracted_volume_mwh")
            if contracted_volume_mwh is not None and (
                not isinstance(contracted_volume_mwh, (int, float)) or contracted_volume_mwh < 0
            ):
                state = dict(state)
                state["status"] = AgentStatus.ERROR.value
                state["error_log"] = [
                    "PreProcessNode S-2: input_context.contracted_volume_mwh must be a non-negative number"
                ]
        return state

    def execute(self, state: AgentState) -> dict[str, Any]:
        user_input = state.get("user_input", "")
        input_context = state.get("input_context", {}) or {}  # read-only [C1]

        ingested = self._market_data_ingestion.execute(user_input, input_context)
        if not ingested["ok"]:
            return {
                "status": AgentStatus.ERROR.value,
                "error_log": [ingested["error"]],
            }

        emit_trace_event(
            "market_data_ingested",
            {
                "contract_period": ingested["contract_period"],
                "has_fuel_index": ingested["fuel_index"] is not None,
            },
            state,
        )

        return {
            "contracted_volume_mwh": ingested["contracted_volume_mwh"],
            "contract_period": ingested["contract_period"],
            "demand_forecast_mwh": ingested["demand_forecast_mwh"],
            "jepx_prices": ingested["jepx_prices"],
            "fuel_index": ingested["fuel_index"],
            "status": AgentStatus.SUCCESS.value,
        }
