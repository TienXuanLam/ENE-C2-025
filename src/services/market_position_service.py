"""AgentCore Platform v1.0"""

# Step-helper classes for the pre_process slot (docs/02_design.md "2+2+1 split"):
#   step 1 - MarketDataIngestionNode
#   step 2 - ProcurementPositionAnalysisNode
#
# Pure-Python business logic only — NOT BaseNode subclasses. S-1/S-2/S-4 run
# exclusively inside src/nodes/pre_process_node.py (the real FunctionNode
# dispatcher) via BaseNode.__call__(). These classes are plain helpers invoked
# sequentially by that dispatcher's execute().
#
# Units: all volume fields are MWh; jepx_prices is JPY/MWh.

from __future__ import annotations

import json
import math
from typing import Any

_VALID_CONTRACT_PERIODS = {"next_day", "next_week"}


class MarketDataIngestionNode:
    """Step 1 — ingest JEPX spot/forward prices, demand forecast, optional fuel index."""

    def execute(
        self,
        user_input: str,
        input_context: dict[str, Any],
    ) -> dict[str, Any]:
        contracted_volume_mwh = input_context.get("contracted_volume_mwh")
        contract_period = str(input_context.get("contract_period", "")).strip()
        demand_forecast_mwh = input_context.get("demand_forecast_mwh")
        jepx_prices = input_context.get("jepx_prices")
        jepx_price_order = input_context.get("jepx_price_order")
        fuel_index = input_context.get("fuel_index")  # optional, proposal §4 Note

        if (
            contracted_volume_mwh is None
            or isinstance(contracted_volume_mwh, bool)
            or not isinstance(contracted_volume_mwh, (int, float))
            or not math.isfinite(contracted_volume_mwh)
        ):
            return {
                "ok": False,
                "error": "MarketDataIngestionNode: contracted_volume_mwh is required and must be numeric",
            }
        if contracted_volume_mwh < 0:
            return {
                "ok": False,
                "error": "MarketDataIngestionNode: contracted_volume_mwh must be non-negative",
            }
        if contract_period not in _VALID_CONTRACT_PERIODS:
            return {
                "ok": False,
                "error": (
                    f"MarketDataIngestionNode: invalid contract_period ({contract_period!r}); "
                    f"expected one of {sorted(_VALID_CONTRACT_PERIODS)}"
                ),
            }
        if not demand_forecast_mwh or not isinstance(demand_forecast_mwh, list):
            return {
                "ok": False,
                "error": "MarketDataIngestionNode: demand_forecast_mwh must be a non-empty hourly MWh array",
            }
        if not jepx_prices or not isinstance(jepx_prices, list):
            return {
                "ok": False,
                "error": "MarketDataIngestionNode: jepx_prices must be a non-empty price time series",
            }
        if jepx_price_order != "oldest_first":
            return {
                "ok": False,
                "error": "MarketDataIngestionNode: jepx_price_order must explicitly be 'oldest_first'",
            }
        expected_hours = 24 if contract_period == "next_day" else 168
        if len(demand_forecast_mwh) != expected_hours:
            return {
                "ok": False,
                "error": f"MarketDataIngestionNode: demand_forecast_mwh must contain {expected_hours} hourly values",
            }
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
            for value in demand_forecast_mwh
        ):
            return {
                "ok": False,
                "error": "MarketDataIngestionNode: demand forecast values must be finite and non-negative",
            }
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in jepx_prices
        ):
            return {"ok": False, "error": "MarketDataIngestionNode: JEPX prices must be finite numeric values"}

        normalized_fuel_index = json.dumps(fuel_index) if fuel_index is not None else None

        return {
            "ok": True,
            "contracted_volume_mwh": float(contracted_volume_mwh),
            "contract_period": contract_period,
            "demand_forecast_mwh": json.dumps([float(value) for value in demand_forecast_mwh], allow_nan=False),
            "jepx_prices": json.dumps([float(value) for value in jepx_prices], allow_nan=False),
            "fuel_index": normalized_fuel_index,
        }


class ProcurementPositionAnalysisNode:
    """Step 2 — contracted-volume vs. demand-gap and spot-price exposure calculation."""

    def execute(
        self,
        contracted_volume_mwh: float,
        demand_forecast_mwh_json: str,
        jepx_prices_json: str,
    ) -> dict[str, Any]:
        try:
            demand_forecast: list[float] = json.loads(demand_forecast_mwh_json) if demand_forecast_mwh_json else []
        except (TypeError, ValueError):
            demand_forecast = []
        try:
            jepx_prices: list[float] = json.loads(jepx_prices_json) if jepx_prices_json else []
        except (TypeError, ValueError):
            jepx_prices = []

        total_demand_mwh = sum(demand_forecast)
        exposure_mwh = total_demand_mwh - contracted_volume_mwh

        # jepx_prices MUST be ordered oldest-first / newest-last — the last
        # element is read as the current spot price (F-02). A caller supplying
        # newest-first ordering silently gets a stale/forward price used as
        # spot instead, with no error raised. See docs/02_design.md "State
        # Definition" and docs/07_operation_guide.md for the caller contract.
        latest_spot_price = jepx_prices[-1] if jepx_prices else 0.0
        # exposure_value_jpy is the JPY cost/benefit of the uncovered (or
        # over-contracted) gap at the latest observed spot price (JPY/MWh). A
        # positive exposure means additional procurement is needed at spot
        # price; a negative exposure means the position is over-contracted
        # relative to demand.
        exposure_value_jpy = exposure_mwh * latest_spot_price

        coverage_ratio = (contracted_volume_mwh / total_demand_mwh) if total_demand_mwh > 0 else None

        return {
            "ok": True,
            "exposure_mwh": exposure_mwh,
            "exposure_value_jpy": exposure_value_jpy,
            "coverage_ratio": coverage_ratio,
        }
