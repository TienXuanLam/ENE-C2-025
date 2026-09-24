"""AgentCore Platform v1.0"""

# Step-helper classes for the main slot (docs/02_design.md "2+2+1 split"):
#   step 3 - PriceForecastNode
#   step 4 - StrategyRecommendationNode
#
# Pure-Python business logic only — NOT BaseNode subclasses. Invoked
# sequentially by src/nodes/main_node.py (the real FunctionNode dispatcher).
#
# PriceForecastNode uses numpy for statistical price-band estimation (moving
# average + Bollinger Bands) as the Primary forecasting method — proposal §11
# Risk #1: LLM-only time-series forecasting is not acceptance-tested for
# accuracy. No LLM call happens in this module.
#
# Units: gap/exposure fields are MWh; jepx_prices / price bands are JPY/MWh.

from __future__ import annotations

import json
import math
import statistics
from typing import Any

_DEFAULT_WINDOW = 20
_DEFAULT_NUM_STD = 2.0

# Risk appetite ranking weights (config/config.yaml: risk_appetite) — proposal
# task #6 "configurable risk appetite". Determines which cost/risk criterion
# is prioritized when ranking the 3 fixed strategy options.
_VALID_RISK_APPETITES = ("conservative", "moderate", "aggressive")
_DEFAULT_RISK_APPETITE = "moderate"


class PriceForecastNode:
    """Step 3 — statistical price-band estimation (moving average + Bollinger Bands)."""

    def execute(
        self,
        jepx_prices_json: str,
        window: int = _DEFAULT_WINDOW,
        num_std: float = _DEFAULT_NUM_STD,
    ) -> dict[str, Any]:
        try:
            prices = json.loads(jepx_prices_json) if jepx_prices_json else []
        except (TypeError, ValueError):
            prices = []

        if not prices:
            return {
                "ok": True,
                "price_band_method": "insufficient_data",
                "price_band_moving_average": None,
                "price_band_low": None,
                "price_band_high": None,
            }

        if window < 1 or isinstance(window, bool):
            raise ValueError("forecast window must be a positive integer")
        numeric_prices = [float(value) for value in prices]
        if not all(math.isfinite(value) for value in numeric_prices):
            raise ValueError("JEPX prices must be finite")
        recent = numeric_prices[-min(window, len(numeric_prices)) :]
        moving_average = statistics.fmean(recent)
        std = statistics.pstdev(recent)
        low_band = moving_average - num_std * std
        high_band = moving_average + num_std * std

        # num_std=2 approximates a ~95% confidence interval under a normal
        # distribution assumption — documented approximation, not a
        # statistically-derived confidence level from the actual price
        # distribution (see docs/02_design.md and operation guide caveats).
        return {
            "ok": True,
            "price_band_method": "moving_average_bollinger_bands",
            "price_band_moving_average": moving_average,
            "price_band_low": low_band,
            "price_band_high": high_band,
        }


class StrategyRecommendationNode:
    """Step 4 — buy-now/defer/hedge-ratio option ranking by cost + risk, configurable risk appetite."""

    def execute(
        self,
        exposure_mwh: float,
        price_band_low: float | None,
        price_band_high: float | None,
        price_band_moving_average: float | None,
        risk_appetite: str = _DEFAULT_RISK_APPETITE,
    ) -> dict[str, Any]:
        if risk_appetite not in _VALID_RISK_APPETITES:
            raise ValueError(f"risk_appetite must be one of {_VALID_RISK_APPETITES}")

        options: list[dict[str, Any]] = []
        if price_band_moving_average is not None and price_band_low is not None and price_band_high is not None:
            if exposure_mwh == 0:
                options.append(
                    {
                        "option": "hold_balanced_position",
                        "expected_cost": 0.0,
                        "max_cost_risk": 0.0,
                        "recommended_timing": "no_action",
                    }
                )
                return {
                    "ok": True,
                    "strategy_options": json.dumps({"options": options, "risk_appetite": risk_appetite}),
                }
            selling = exposure_mwh < 0
            volume = abs(exposure_mwh)
            options.append(
                {
                    "option": "sell_now" if selling else "buy_now",
                    "expected_cost": volume * price_band_moving_average,
                    "max_cost_risk": volume * price_band_high,
                    "recommended_timing": "immediate",
                }
            )
            options.append(
                {
                    "option": "defer_sale" if selling else "defer",
                    "expected_cost": volume * price_band_low,
                    "max_cost_risk": volume * price_band_high,
                    "recommended_timing": "next_price_dip",
                }
            )
            options.append(
                {
                    "option": "staggered_sale" if selling else "partial_hedge",
                    "expected_cost": volume * 0.5 * price_band_moving_average,
                    "max_cost_risk": volume * 0.5 * price_band_high,
                    "recommended_timing": "split_over_period",
                }
            )

            # risk_appetite determines which criterion drives the ranking
            # (the first option in the sorted list is the "recommended" one):
            #   conservative -> minimize worst-case cost (max_cost_risk)
            #   aggressive   -> minimize expected cost, accepting more risk
            #   moderate     -> balance both criteria equally
            if risk_appetite == "conservative":
                options.sort(key=lambda o: float(o["max_cost_risk"]))
            elif risk_appetite == "aggressive":
                options.sort(key=lambda o: float(o["expected_cost"]))
            else:  # moderate
                options.sort(key=lambda o: float(o["max_cost_risk"]) + float(o["expected_cost"]))
        else:
            options.append(
                {
                    "option": "insufficient_data",
                    "expected_cost": None,
                    "max_cost_risk": None,
                    "recommended_timing": None,
                }
            )

        return {"ok": True, "strategy_options": json.dumps({"options": options, "risk_appetite": risk_appetite})}
