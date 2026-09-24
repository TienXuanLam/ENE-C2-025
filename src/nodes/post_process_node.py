"""AgentCore Platform v1.0"""

# Real FunctionNode dispatcher for docs/02_design.md "2+2+1 split" post_process slot:
#   step 5 - ReportGenerationNode.execute()
# S-1 (required_trust_level), S-3 (_extra_security_gate_output), S-4
# (emit_trace_event) all run here — never inside the pure-Python step helper.

from typing import Any, ClassVar

from framework.nodes.function_node import FunctionNode
from framework.schemas.agent_status import AgentStatus
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from shared.utils.audit_logger import emit_trace_event

from src.services.report_generation_service import DECISION_SUPPORT_DISCLAIMER, ReportGenerationNode

# Commercially sensitive trading-strategy detail that must never appear in the
# final report (proposal §2-3 point 2 — margins, internal trading policy).
_SENSITIVE_DETAIL_MARKERS: tuple[str, ...] = (
    "internal_margin",
    "trading_policy",
    "cost_basis",
)


class PostProcessNode(FunctionNode):
    """Step 5: structured procurement strategy report + executive summary."""

    # S-1: standard business operation on procurement/market data.
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL

    def __init__(self) -> None:
        self._report_generation = ReportGenerationNode()

    def _extra_security_gate_output(self, result: dict[str, Any]) -> dict[str, Any]:
        # S-3 domain hook: mandatory disclaimer check + sensitive
        # trading-strategy detail content filter. May raise.
        summary = result.get("executive_summary", "")
        if summary and DECISION_SUPPORT_DISCLAIMER not in summary:
            raise RuntimeError(
                "PostProcessNode S-3: mandatory decision-support disclaimer missing from executive_summary"
            )

        # F-04: scan only the free-text field (executive_summary) plus the
        # option "recommended_timing" labels — not the entire formatted_output
        # blob. Scanning the whole package would false-positive on a common
        # financial term like "cost_basis" appearing legitimately in a
        # caller-supplied field unrelated to leaked internal detail. Numeric
        # fields (exposure_mwh, price_band_*, expected_cost_jpy, etc.) cannot
        # meaningfully contain these text markers and are excluded.
        formatted_output = result.get("formatted_output", {}) or {}
        scannable_text = (
            summary
            + " "
            + " ".join(str(row.get("recommended_timing", "")) for row in formatted_output.get("risk_table", []) or [])
        )
        scannable_text_lower = scannable_text.lower()
        for marker in _SENSITIVE_DETAIL_MARKERS:
            if marker in scannable_text_lower:
                raise RuntimeError(
                    f"PostProcessNode S-3: sensitive trading-strategy detail marker '{marker}' "
                    "detected in output — blocked"
                )
        return result

    def execute(self, state: AgentState) -> dict[str, Any]:
        generated = self._report_generation.execute(
            contract_period=state.get("contract_period", ""),
            exposure_mwh=state.get("exposure_mwh"),
            exposure_value_jpy=state.get("exposure_value_jpy"),
            coverage_ratio=state.get("coverage_ratio"),
            price_band_low=state.get("price_band_low"),
            price_band_high=state.get("price_band_high"),
            price_band_moving_average=state.get("price_band_moving_average"),
            strategy_options_json=state.get("strategy_options", ""),
        )

        emit_trace_event(
            "report_generated",
            {"contract_period": state.get("contract_period", "")},
            state,
        )

        return {
            "executive_summary": generated["executive_summary"],
            "formatted_output": generated["formatted_output"],
            "status": AgentStatus.SUCCESS.value,
        }
