"""AgentCore Platform v1.0"""

# Step-helper class for the post_process slot (docs/02_design.md "2+2+1 split"):
#   step 5 - ReportGenerationNode
#
# Pure-Python business logic only — NOT a BaseNode subclass. Invoked by
# src/nodes/post_process_node.py (the real FunctionNode dispatcher), which
# applies the S-3 domain hook after this helper runs.
#
# Units: exposure/gap fields are MWh; price/cost fields are JPY (or JPY/MWh
# for price bands specifically).

from __future__ import annotations

import json
from typing import Any

# Mandatory disclaimer — proposal §11 Risk #4. The dispatcher's S-3 hook
# verifies this exact marker is present in the executive summary before
# output leaves the node boundary; do not alter the wording independently of
# docs/02_design.md and the S-3 hook check.
DECISION_SUPPORT_DISCLAIMER = (
    "This report is a decision-support document and does not constitute "
    "investment advice under the Financial Instruments and Exchange Act."
)


class ReportGenerationNode:
    """Step 5 — structured procurement strategy report: exec summary, risk table,
    forecast band, strategy options, recommendation."""

    def execute(
        self,
        contract_period: str,
        exposure_mwh: float | None,
        exposure_value_jpy: float | None,
        coverage_ratio: float | None,
        price_band_low: float | None,
        price_band_high: float | None,
        price_band_moving_average: float | None,
        strategy_options_json: str,
    ) -> dict[str, Any]:
        try:
            strategy = json.loads(strategy_options_json) if strategy_options_json else {}
        except (TypeError, ValueError):
            strategy = {}

        options = strategy.get("options", [])
        risk_appetite = strategy.get("risk_appetite")
        top_option = options[0] if options else None

        # F-03: exposure_mwh < 0 means the position is over-contracted
        # (contracted volume exceeds forecast demand) — the "cost" figures in
        # the risk table then represent potential resale value, not a
        # purchase cost, and "buy_now"/"defer" timings don't apply the same
        # way. Surface this explicitly rather than leaving a bare negative
        # number for the procurement manager to interpret.
        if exposure_mwh is None:
            position_status = None
        elif exposure_mwh > 0:
            position_status = "under_contracted"
        elif exposure_mwh < 0:
            position_status = "over_contracted"
        else:
            position_status = "balanced"

        summary_lines = [
            f"Analysis period: {contract_period}",
            f"Procurement exposure: {exposure_mwh} MWh" if exposure_mwh is not None else "Procurement exposure: N/A",
        ]
        if position_status == "over_contracted":
            summary_lines.append(
                "Position status: OVER-CONTRACTED — contracted volume exceeds forecast "
                "demand; the figures below represent potential resale value, not a "
                "purchase cost. The recommendation therefore uses sale-specific options."
            )
        summary_lines += [
            f"Coverage ratio: {coverage_ratio:.2%}" if coverage_ratio is not None else "Coverage ratio: N/A",
            f"Recommended option: {top_option['option']}" if top_option else "Recommended option: N/A",
            DECISION_SUPPORT_DISCLAIMER,
        ]
        executive_summary = "\n".join(summary_lines)

        # Risk table: one row per strategy option, exposing expected cost vs.
        # worst-case cost risk side-by-side for report consumers (task #7).
        risk_table = [
            {
                "option": o.get("option"),
                "expected_cost_jpy": o.get("expected_cost"),
                "max_cost_risk_jpy": o.get("max_cost_risk"),
                "recommended_timing": o.get("recommended_timing"),
            }
            for o in options
        ]

        package = {
            "contract_period": contract_period,
            "executive_summary": executive_summary,
            "exposure_mwh": exposure_mwh,
            "exposure_value_jpy": exposure_value_jpy,
            "position_status": position_status,
            "coverage_ratio": coverage_ratio,
            "price_band_low": price_band_low,
            "price_band_high": price_band_high,
            "price_band_moving_average": price_band_moving_average,
            "risk_table": risk_table,
            "strategy_options": options,
            "risk_appetite": risk_appetite,
            "recommendation": top_option,
            "disclaimer": DECISION_SUPPORT_DISCLAIMER,
        }

        return {
            "ok": True,
            "executive_summary": executive_summary,
            "formatted_output": package,
        }
