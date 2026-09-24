# ENE-C2-025 — Unit Tests: MarketDataIngestionNode + ProcurementPositionAnalysisNode step helpers
#
# Pure-Python step helpers — no framework/shared import needed.
# Units: volume fields are MWh; jepx_prices is JPY/MWh.

import json

import pytest

from src.services.market_position_service import (
    MarketDataIngestionNode,
    ProcurementPositionAnalysisNode,
)


class TestMarketDataIngestionNode:
    def setup_method(self):
        self.node = MarketDataIngestionNode()

    def test_success_path(self):
        result = self.node.execute(
            user_input="analyze procurement position",
            input_context={
                "contracted_volume_mwh": 1.0,
                "contract_period": "next_day",
                "jepx_price_order": "oldest_first",
                "demand_forecast_mwh": [0.05] * 24,
                "jepx_prices": [20.0, 21.0, 22.0],
            },
        )
        assert result["ok"] is True
        assert result["contracted_volume_mwh"] == 1.0
        assert result["contract_period"] == "next_day"
        assert json.loads(result["demand_forecast_mwh"]) == [0.05] * 24
        assert result["fuel_index"] is None

    def test_negative_contracted_volume_rejected(self):
        result = self.node.execute(
            user_input="x",
            input_context={
                "contracted_volume_mwh": -1.0,
                "contract_period": "next_day",
                "demand_forecast_mwh": [0.05],
                "jepx_prices": [20.0],
            },
        )
        assert result["ok"] is False
        assert "non-negative" in result["error"]

    def test_invalid_contract_period_rejected(self):
        result = self.node.execute(
            user_input="x",
            input_context={
                "contracted_volume_mwh": 1.0,
                "contract_period": "next_month",
                "demand_forecast_mwh": [0.05],
                "jepx_prices": [20.0],
            },
        )
        assert result["ok"] is False

    def test_empty_contract_period_string_rejected(self):
        # T-GAP-01: an empty string is not one of the 2 valid values and must
        # be rejected the same way as any other invalid value — not silently
        # accepted or defaulted.
        result = self.node.execute(
            user_input="x",
            input_context={
                "contracted_volume_mwh": 1.0,
                "contract_period": "",
                "demand_forecast_mwh": [0.05],
                "jepx_prices": [20.0],
            },
        )
        assert result["ok"] is False
        assert "contract_period" in result["error"]

    def test_missing_contract_period_key_rejected(self):
        # contract_period entirely absent from input_context (not just empty)
        # must also be rejected — defaults to "" internally, same path as above.
        result = self.node.execute(
            user_input="x",
            input_context={
                "contracted_volume_mwh": 1.0,
                "demand_forecast_mwh": [0.05],
                "jepx_prices": [20.0],
            },
        )
        assert result["ok"] is False
        assert "contract_period" in result["error"]
        assert "contract_period" in result["error"]

    def test_missing_demand_forecast_rejected(self):
        result = self.node.execute(
            user_input="x",
            input_context={
                "contracted_volume_mwh": 1.0,
                "contract_period": "next_day",
                "demand_forecast_mwh": [],
                "jepx_prices": [20.0],
            },
        )
        assert result["ok"] is False
        assert "demand_forecast_mwh" in result["error"]

    def test_optional_fuel_index_passthrough(self):
        result = self.node.execute(
            user_input="x",
            input_context={
                "contracted_volume_mwh": 1.0,
                "contract_period": "next_week",
                "jepx_price_order": "oldest_first",
                "demand_forecast_mwh": [0.05] * 168,
                "jepx_prices": [20.0],
                "fuel_index": {"lng": 12.5},
            },
        )
        assert result["ok"] is True
        assert json.loads(result["fuel_index"]) == {"lng": 12.5}

    def test_missing_explicit_price_order_rejected(self):
        result = self.node.execute(
            user_input="x",
            input_context={
                "contracted_volume_mwh": 1.0,
                "contract_period": "next_day",
                "demand_forecast_mwh": [0.05] * 24,
                "jepx_prices": [20.0],
            },
        )
        assert result["ok"] is False
        assert "jepx_price_order" in result["error"]


class TestProcurementPositionAnalysisNode:
    def setup_method(self):
        self.node = ProcurementPositionAnalysisNode()

    def test_gap_and_exposure_calculation(self):
        demand_forecast_mwh = json.dumps([0.05] * 24)  # total ~1.2 MWh
        jepx_prices = json.dumps([20.0, 21.0, 22.0])  # latest = 22.0
        result = self.node.execute(1.0, demand_forecast_mwh, jepx_prices)
        # sum([0.05] * 24) is not exactly 1.2 in binary floating point.
        assert result["exposure_mwh"] == pytest.approx(0.2)
        assert result["exposure_value_jpy"] == pytest.approx(0.2 * 22.0)

    def test_coverage_ratio_computed(self):
        demand_forecast_mwh = json.dumps([100.0])
        jepx_prices = json.dumps([10.0])
        result = self.node.execute(50.0, demand_forecast_mwh, jepx_prices)
        assert result["coverage_ratio"] == 0.5

    def test_zero_demand_coverage_ratio_none(self):
        result = self.node.execute(100.0, json.dumps([]), json.dumps([10.0]))
        assert result["coverage_ratio"] is None

    def test_zero_exposure_when_contracted_matches_demand_exactly(self):
        # Edge case per task #9: zero exposure — contracted volume exactly
        # covers total forecast demand.
        demand_forecast_mwh = json.dumps([10.0, 10.0])
        jepx_prices = json.dumps([25.0])
        result = self.node.execute(20.0, demand_forecast_mwh, jepx_prices)
        assert result["exposure_mwh"] == 0.0
        assert result["exposure_value_jpy"] == 0.0
