# ENE-C2-025 — Unit Tests: ReportGenerationNode step helper

import json

from src.services.report_generation_service import DECISION_SUPPORT_DISCLAIMER, ReportGenerationNode


class TestReportGenerationNode:
    def setup_method(self):
        self.node = ReportGenerationNode()

    def test_disclaimer_present_in_summary_and_package(self):
        result = self.node.execute(
            contract_period="next_day",
            exposure_mwh=100.0,
            exposure_value_jpy=2000.0,
            coverage_ratio=0.9,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
            strategy_options_json=json.dumps({"options": [{"option": "buy_now"}], "risk_appetite": "moderate"}),
        )
        assert DECISION_SUPPORT_DISCLAIMER in result["executive_summary"]
        assert result["formatted_output"]["disclaimer"] == DECISION_SUPPORT_DISCLAIMER

    def test_recommended_option_reflects_top_ranked_strategy(self):
        result = self.node.execute(
            contract_period="next_week",
            exposure_mwh=50.0,
            exposure_value_jpy=1000.0,
            coverage_ratio=0.5,
            price_band_low=18.0,
            price_band_high=22.0,
            price_band_moving_average=20.0,
            strategy_options_json=json.dumps(
                {"options": [{"option": "defer"}, {"option": "buy_now"}], "risk_appetite": "moderate"}
            ),
        )
        assert "Recommended option: defer" in result["executive_summary"]
        assert result["formatted_output"]["recommendation"]["option"] == "defer"

    def test_missing_exposure_reports_na(self):
        result = self.node.execute(
            contract_period="next_day",
            exposure_mwh=None,
            exposure_value_jpy=None,
            coverage_ratio=None,
            price_band_low=None,
            price_band_high=None,
            price_band_moving_average=None,
            strategy_options_json=json.dumps({"options": []}),
        )
        assert "Procurement exposure: N/A" in result["executive_summary"]
        assert "Recommended option: N/A" in result["executive_summary"]

    def test_over_contracted_position_flagged_in_summary_and_package(self):
        # F-03: negative exposure means over-contracted — must be explicitly
        # surfaced, not left as a bare negative number.
        result = self.node.execute(
            contract_period="next_day",
            exposure_mwh=-50.0,
            exposure_value_jpy=-1000.0,
            coverage_ratio=1.5,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
            strategy_options_json=json.dumps({"options": [{"option": "buy_now"}], "risk_appetite": "moderate"}),
        )
        assert "OVER-CONTRACTED" in result["executive_summary"]
        assert result["formatted_output"]["position_status"] == "over_contracted"

    def test_under_contracted_position_status(self):
        result = self.node.execute(
            contract_period="next_day",
            exposure_mwh=50.0,
            exposure_value_jpy=1000.0,
            coverage_ratio=0.5,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
            strategy_options_json=json.dumps({"options": [{"option": "buy_now"}], "risk_appetite": "moderate"}),
        )
        assert "OVER-CONTRACTED" not in result["executive_summary"]
        assert result["formatted_output"]["position_status"] == "under_contracted"

    def test_balanced_position_status_when_exposure_zero(self):
        result = self.node.execute(
            contract_period="next_day",
            exposure_mwh=0.0,
            exposure_value_jpy=0.0,
            coverage_ratio=1.0,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
            strategy_options_json=json.dumps({"options": [{"option": "buy_now"}], "risk_appetite": "moderate"}),
        )
        assert result["formatted_output"]["position_status"] == "balanced"

    def test_risk_table_has_one_row_per_option(self):
        result = self.node.execute(
            contract_period="next_day",
            exposure_mwh=100.0,
            exposure_value_jpy=2000.0,
            coverage_ratio=0.9,
            price_band_low=15.0,
            price_band_high=25.0,
            price_band_moving_average=20.0,
            strategy_options_json=json.dumps(
                {
                    "options": [
                        {
                            "option": "buy_now",
                            "expected_cost": 2000.0,
                            "max_cost_risk": 2500.0,
                            "recommended_timing": "immediate",
                        },
                        {
                            "option": "defer",
                            "expected_cost": 1500.0,
                            "max_cost_risk": 2500.0,
                            "recommended_timing": "next_price_dip",
                        },
                        {
                            "option": "partial_hedge",
                            "expected_cost": 1000.0,
                            "max_cost_risk": 1250.0,
                            "recommended_timing": "split_over_period",
                        },
                    ],
                    "risk_appetite": "moderate",
                }
            ),
        )
        risk_table = result["formatted_output"]["risk_table"]
        assert len(risk_table) == 3
        assert {row["option"] for row in risk_table} == {"buy_now", "defer", "partial_hedge"}
        assert risk_table[0]["expected_cost_jpy"] == 2000.0
