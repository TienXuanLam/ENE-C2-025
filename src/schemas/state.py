"""AgentCore Platform v1.0"""

# ADR-005: State must be a flat TypedDict — never Pydantic BaseModel.
# LangGraph checkpoints use msgpack serialization; Pydantic objects
# cause silent corruption.  Extend AgentState with agent-specific
# fields only.  Do NOT add credentials, secrets, or Pydantic models.
#
# Scalar analysis/recommendation outputs are stored as flat primitive fields
# (exposure_mwh, price_band_low, etc.) — not gathered into a nested JSON blob —
# per task #2. Only genuinely list/collection-shaped fields (demand_forecast_mwh,
# jepx_prices, strategy_options) are Optional[str] via json.dumps/json.loads
# (ADR-005), since a list of hourly points or ranked options is not
# flattenable into scalar fields. See docs/02_design.md "State Definition".

from typing import Optional

from framework.schemas.agent_state import AgentState


class State(AgentState):
    """Agent state for WholesaleElectricityProcurementStrategyAgent (ENE-C2-025).

    Populated across the 2+2+1 step-helper pipeline:
      pre_process  -> MarketDataIngestionNode, ProcurementPositionAnalysisNode
      main         -> PriceForecastNode, StrategyRecommendationNode
      post_process -> ReportGenerationNode

    Units: all volume fields are MWh (not kWh); all price fields are JPY/MWh.
    """

    # --- pre_process / step 1 (MarketDataIngestionNode) ---
    contracted_volume_mwh: Optional[float]
    contract_period: Optional[str]
    demand_forecast_mwh: Optional[str]
    jepx_prices: Optional[str]
    fuel_index: Optional[str]

    # --- pre_process / step 2 (ProcurementPositionAnalysisNode) ---
    exposure_mwh: Optional[float]
    exposure_value_jpy: Optional[float]
    coverage_ratio: Optional[float]

    # --- main / step 3 (PriceForecastNode) ---
    price_band_low: Optional[float]
    price_band_high: Optional[float]
    price_band_moving_average: Optional[float]
    price_band_method: Optional[str]

    # --- main / step 4 (StrategyRecommendationNode) ---
    strategy_options: Optional[str]

    # --- post_process / step 5 (ReportGenerationNode) ---
    executive_summary: Optional[str]
