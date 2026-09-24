# Template Design Specification

## Position in AgentCore Architecture

- **Agent Class**: `WholesaleElectricityProcurementStrategyAgent`
- **L1 Base**: `AgentBaseGraph`
- **Category**: Cat 2 fixed domain workflow
- **State**: flat `AgentState` extension; arrays are JSON strings

## Current Scaffold Topology

```text
Outer: initialize -> pre_process -> main(GraphNode) -> post_process -> finalize
Inner: START -> position_analysis -> price_forecast -> strategy_recommendation -> END
```

`PreProcessNode` validates and normalizes the external market-data envelope.
`ProcurementStrategyWorkflowGraphNode` occupies the outer `main` slot and wraps
the inner `ProcurementStrategyWorkflowGraph` at the scaffold-mandated
`src/graph/domain_workflow_graph.py` location. The outer graph does not override
its framework-owned edges. `PostProcessNode` converts the workflow result into
a decision-support report and applies the domain output gate.

## Workflow Responsibilities

| Component | Responsibility |
|---|---|
| `PreProcessNode` | Enforce request-size, volume, period, hourly-series and explicit ordering contracts; normalize primitives |
| `PositionAnalysisNode` | Calculate demand gap, marked-to-latest-price exposure and coverage ratio |
| `PriceForecastNode` | Calculate a moving-average/Bollinger price band using deterministic standard-library statistics |
| `StrategyRecommendationNode` | Rank buy/defer/hedge options for short positions, sale options for surplus positions, or no-action for balanced positions |
| `PostProcessNode` | Build executive summary, risk table, recommendation and mandatory disclaimer |

## Input Contract

`input_context` requires:

- `contracted_volume_mwh`: finite non-negative number;
- `contract_period`: `next_day` or `next_week`;
- `demand_forecast_mwh`: respectively 24 or 168 finite non-negative hourly values;
- `jepx_prices`: non-empty finite numeric series;
- `jepx_price_order`: literal `oldest_first`, so the latest-price calculation
  never silently assumes an unconfirmed ordering;
- optional `fuel_index`, retained as JSON without affecting deterministic price
  calculations.

The combined text and context payload may not exceed 1 MiB.

## Configuration Contract

`forecast_window` must be a positive integer. `risk_appetite` must be one of
`conservative`, `moderate`, or `aggressive`. Invalid deployment configuration
raises `ConfigError` during graph construction; it is never silently changed.

## Position-Aware Recommendations

- Positive exposure (`under_contracted`) produces `buy_now`, `defer`, and
  `partial_hedge` options.
- Negative exposure (`over_contracted`) produces `sell_now`, `defer_sale`, and
  `staggered_sale` options and reports values as potential resale value.
- Zero exposure (`balanced`) produces a single `hold_balanced_position` action.

This prevents purchase recommendations from being presented for a surplus
position. Statistical outputs are deterministic and no LLM computes numeric
forecast or cost values.

## State Fields

The pre-process boundary writes normalized contract and series fields. The
inner graph writes `exposure_mwh`, `exposure_value_jpy`, `coverage_ratio`,
`price_band_low/high/moving_average`, `price_band_method`, and the JSON-encoded
`strategy_options`. The post-process boundary writes `executive_summary` and
`formatted_output`. Credentials, clients and arbitrary objects never enter
state.

## Security and Failure Handling

- Every executable node and the `GraphNode` boundary require
  `VERIFIED_EXTERNAL`.
- `PreProcessNode` extends the final framework S-2 input gate;
  `PostProcessNode` extends the final S-3 output gate.
- Every executable node emits domain trace events.
- The output gate enforces the decision-support disclaimer and blocks internal
  trading-policy markers in caller-visible free text.
- Inner subgraph infrastructure errors propagate instead of being reported as
  successful strategy output.

## Import Isolation

The implementation imports only `framework.*`, `shared.*`, standard-library
modules and its own `src.*` modules. No direct platform SDK, mediator, L2-agent
or sibling-agent import is present.
