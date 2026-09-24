"""Inner procurement analysis, price forecast and strategy workflow."""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START
from framework.errors import ConfigError
from framework.graph.base_graph import BaseGraph
from framework.schemas.agent_state import AgentState
from framework.schemas.agent_status import AgentStatus
from src.nodes.position_analysis_node import PositionAnalysisNode
from src.nodes.price_forecast_node import PriceForecastNode
from src.nodes.strategy_recommendation_node import StrategyRecommendationNode
from src.schemas.state import State


class ProcurementStrategyWorkflowGraph(BaseGraph):
    @property
    def name(self) -> str:
        return "wholesale_electricity_procurement_strategy_workflow"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        if "forecast_window" not in self.config or "risk_appetite" not in self.config:
            raise ConfigError("inner workflow requires forecast_window and risk_appetite")

    def register_nodes(self) -> None:
        self._nodes["position_analysis"] = PositionAnalysisNode()
        self._nodes["price_forecast"] = PriceForecastNode(window=int(self.config["forecast_window"]))
        self._nodes["strategy_recommendation"] = StrategyRecommendationNode(
            risk_appetite=str(self.config["risk_appetite"])
        )

    def add_edges(self) -> None:
        self._sg.add_edge(START, "position_analysis")
        self._sg.add_conditional_edges("position_analysis", self.route_after_position)
        self._sg.add_conditional_edges("price_forecast", self.route)
        self._sg.add_edge("strategy_recommendation", END)

    def route(self, state: AgentState) -> str:
        return END if state.get("status") == AgentStatus.ERROR.value else "strategy_recommendation"

    def route_after_position(self, state: AgentState) -> str:
        return END if state.get("status") == AgentStatus.ERROR.value else "price_forecast"

    def get_output(self, state: AgentState) -> dict[str, Any]:
        keys = (
            "exposure_mwh",
            "exposure_value_jpy",
            "coverage_ratio",
            "price_band_low",
            "price_band_high",
            "price_band_moving_average",
            "price_band_method",
            "strategy_options",
        )
        return {
            "output": {key: state.get(key) for key in keys},
            "status": state.get("status", AgentStatus.ERROR.value),
            "trace_id": state.get("trace_id"),
            "correlation_id": state.get("correlation_id"),
            "node_history": state.get("node_history", []),
        }
