# ENE-C2-025 — Unit Tests: PriceForecastNode + StrategyRecommendationNode step helpers

import json

import pytest

from src.services.forecast_strategy_service import PriceForecastNode, StrategyRecommendationNode


class TestPriceForecastNode:
    def setup_method(self):
        self.node = PriceForecastNode()

    def test_moving_average_bollinger_bands_with_sufficient_history(self):
        prices = [20.0, 21.0, 19.0, 22.0, 20.0] * 5  # 25 points
        result = self.node.execute(json.dumps(prices))
        assert result["price_band_method"] == "moving_average_bollinger_bands"
        assert result["price_band_low"] < result["price_band_moving_average"] < result["price_band_high"]

    def test_insufficient_data_when_prices_empty(self):
        result = self.node.execute(json.dumps([]))
        assert result["price_band_method"] == "insufficient_data"
        assert result["price_band_moving_average"] is None
        assert result["price_band_low"] is None
        assert result["price_band_high"] is None

    def test_malformed_json_treated_as_no_data(self):
        result = self.node.execute("not-json")
        assert result["price_band_method"] == "insufficient_data"

    def test_single_price_point(self):
        # Edge case per task #9: a single price point — std=0, so low/high
        # bands collapse to the moving average itself. Must not crash.
        result = self.node.execute(json.dumps([20.0]))
        assert result["price_band_method"] == "moving_average_bollinger_bands"
        assert result["price_band_moving_average"] == 20.0
        assert result["price_band_low"] == 20.0
        assert result["price_band_high"] == 20.0

    def test_window_smaller_than_history_uses_full_history(self):
        prices = [10.0, 20.0, 30.0]
        result = self.node.execute(json.dumps(prices), window=20)
        # window isn't part of the flat output anymore; verify via the band
        # spread reflecting all 3 points rather than crashing/truncating.
        assert result["price_band_method"] == "moving_average_bollinger_bands"
        assert result["price_band_moving_average"] == 20.0


class TestStrategyRecommendationNode:
    def setup_method(self):
        self.node = StrategyRecommendationNode()

    def test_three_options_always_computed(self):
        result = self.node.execute(
            exposure_mwh=100.0,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
        )
        options = json.loads(result["strategy_options"])["options"]
        assert len(options) == 3
        option_names = {o["option"] for o in options}
        assert option_names == {"buy_now", "defer", "partial_hedge"}

    def test_conservative_ranks_by_min_worst_case_risk(self):
        result = self.node.execute(
            exposure_mwh=100.0,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
            risk_appetite="conservative",
        )
        options = json.loads(result["strategy_options"])["options"]
        risks = [o["max_cost_risk"] for o in options]
        assert risks == sorted(risks)
        # partial_hedge always has the lowest max_cost_risk (half exposure)
        assert options[0]["option"] == "partial_hedge"

    def test_aggressive_ranks_by_min_expected_cost(self):
        result = self.node.execute(
            exposure_mwh=100.0,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
            risk_appetite="aggressive",
        )
        options = json.loads(result["strategy_options"])["options"]
        costs = [o["expected_cost"] for o in options]
        assert costs == sorted(costs)

    def test_moderate_is_the_default_when_appetite_omitted(self):
        result = self.node.execute(
            exposure_mwh=100.0,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
        )
        assert json.loads(result["strategy_options"])["risk_appetite"] == "moderate"

    def test_invalid_risk_appetite_fails_closed(self):
        with pytest.raises(ValueError):
            self.node.execute(
                exposure_mwh=100.0,
                price_band_low=15.0,
                price_band_high=25.0,
                price_band_moving_average=20.0,
                risk_appetite="yolo",
            )

    def test_insufficient_forecast_data_returns_placeholder(self):
        result = self.node.execute(
            exposure_mwh=100.0,
            price_band_low=None,
            price_band_high=None,
            price_band_moving_average=None,
        )
        options = json.loads(result["strategy_options"])["options"]
        assert len(options) == 1
        assert options[0]["option"] == "insufficient_data"

    def test_zero_exposure_yields_zero_cost_options(self):
        # Edge case per task #9: zero exposure — all options should compute
        # to zero cost/risk without dividing by zero or crashing.
        result = self.node.execute(
            exposure_mwh=0.0,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
        )
        options = json.loads(result["strategy_options"])["options"]
        assert options == [
            {
                "option": "hold_balanced_position",
                "expected_cost": 0.0,
                "max_cost_risk": 0.0,
                "recommended_timing": "no_action",
            }
        ]

    def test_over_contracted_position_uses_sale_options(self):
        result = self.node.execute(-100.0, 15.0, 25.0, 20.0)
        names = {option["option"] for option in json.loads(result["strategy_options"])["options"]}
        assert names == {"sell_now", "defer_sale", "staggered_sale"}

    def test_partial_hedge_is_half_of_buy_now_cost(self):
        result = self.node.execute(
            exposure_mwh=100.0,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
        )
        options = {o["option"]: o for o in json.loads(result["strategy_options"])["options"]}
        assert options["partial_hedge"]["expected_cost"] == options["buy_now"]["expected_cost"] / 2
