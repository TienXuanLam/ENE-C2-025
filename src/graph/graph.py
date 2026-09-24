"""ENE-C2-025 outer graph aligned with the current Cat 2 scaffold."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

from framework.errors import ConfigError
from framework.graph.agent_base_graph import AgentBaseGraph
from framework.nodes.graph_node import GraphNode
from framework.schemas.agent_state import AgentState
from framework.schemas.trust_level import TrustLevel
from src.nodes.post_process_node import PostProcessNode
from src.nodes.pre_process_node import PreProcessNode
from src.schemas.state import State

if TYPE_CHECKING:
    from src.graph.domain_workflow_graph import ProcurementStrategyWorkflowGraph

_RISK_APPETITES = {"conservative", "moderate", "aggressive"}


class ProcurementStrategyWorkflowGraphNode(GraphNode):
    required_trust_level: ClassVar[TrustLevel] = TrustLevel.VERIFIED_EXTERNAL
    error_strategy: ClassVar[str] = "propagate"
    propagate_hitl: ClassVar[bool] = False

    def __init__(self, forecast_window: int, risk_appetite: str) -> None:
        super().__init__()
        self._config = {"forecast_window": forecast_window, "risk_appetite": risk_appetite}

    def get_subgraph(self) -> "ProcurementStrategyWorkflowGraph":
        from src.graph.domain_workflow_graph import ProcurementStrategyWorkflowGraph

        return ProcurementStrategyWorkflowGraph(config=self._config)

    def extract_input(self, state: AgentState) -> str:
        return json.dumps(
            {
                "contracted_volume_mwh": state.get("contracted_volume_mwh"),
                "contract_period": state.get("contract_period"),
                "demand_forecast_mwh": state.get("demand_forecast_mwh"),
                "jepx_prices": state.get("jepx_prices"),
            }
        )

    def merge_output(self, state: AgentState, sub_result: dict[str, Any]) -> dict[str, Any]:
        output = sub_result.get("output", {}) or {}
        if not isinstance(output, dict):
            output = {}
        return {**output, "status": sub_result.get("status")}


class WholesaleElectricityProcurementStrategyAgent(AgentBaseGraph):
    @property
    def name(self) -> str:
        return "WholesaleElectricityProcurementStrategyAgent"

    @property
    def state_schema(self) -> type:
        return State

    def _validate_config(self) -> None:
        super()._validate_config()
        window = self.config.get("forecast_window", 20)
        appetite = self.config.get("risk_appetite", "moderate")
        if isinstance(window, bool) or not isinstance(window, int) or window < 1:
            raise ConfigError("forecast_window must be a positive integer")
        if appetite not in _RISK_APPETITES:
            raise ConfigError(f"risk_appetite must be one of {sorted(_RISK_APPETITES)}")

    def register_nodes(self) -> None:
        super().register_nodes()
        self._nodes["pre_process"] = PreProcessNode()
        self._nodes["main"] = ProcurementStrategyWorkflowGraphNode(
            forecast_window=int(self.config.get("forecast_window", 20)),
            risk_appetite=str(self.config.get("risk_appetite", "moderate")),
        )
        self._nodes["post_process"] = PostProcessNode()
