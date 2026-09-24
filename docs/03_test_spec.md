# Test Specification

## Test Strategy
- Coverage target: every node covers success path + error/edge path;
  domain gate branches (S-2 `contracted_volume_mwh` reject, S-3 disclaimer/sensitive-detail
  block) each covered explicitly; numpy-based `PriceForecastNode` covered with sufficient,
  insufficient, and single-point price-history inputs; `StrategyRecommendationNode`
  covered across all 3 `risk_appetite` branches (conservative/moderate/aggressive) and
  the zero-exposure edge case.
- Test types: Unit (`tests/unit/`) / Integration (`tests/integration/`) /
  Proof-of-Boundary (`tests/proof_of_boundary/`)

## Framework Compliance Tests (Mandatory — 6 TC)

| TC-ID | Test | Expected Result | Result |
|-------|------|----------------|--------|
| TC-01 | State contract: `State` (src/schemas/state.py) is a flat TypedDict, all fields primitives/`Optional[str]` JSON | Type check pass, no Pydantic/dataclass | |
| TC-02 | `required_trust_level` enforced on all 3 real dispatchers | `PreProcessNode`/`MainNode`/`PostProcessNode` called via `__call__()` with `caller_trust_level=ANONYMOUS` → `status=error`, `execute()` not invoked | |
| TC-03 | S-2: `_extra_security_gate_input()` on `PreProcessNode` rejects invalid `contracted_volume_mwh` | `status=error`, `error_log` contains "must be a non-negative number"; hook does not raise | |
| TC-04 | S-3: `_extra_security_gate_output()` on `PostProcessNode` blocks output missing the mandatory decision-support disclaimer | `RuntimeError` raised, `__call__()` converts to `status=error` | |
| TC-05 | S-4: domain `emit_trace_event()` called at least once inside every real dispatcher's `execute()` (no duplicate `node_start`/`node_complete`/`node_error`) | ≥1 domain event per node; 0 duplicate lifecycle events in `execute()` body | |
| TC-06 | Import isolation: no `agenticstar` SDK import anywhere under `src/` (numpy is a permitted third-party statistical dependency, not Level 0) | AST scan: 0 violations | |

## Business Logic / Domain Tests

| TC-ID | Test | Input | Expected Result | Result |
|-------|------|-------|----------------|--------|
| BL-01 | `MarketDataIngestionNode` — valid input | `contracted_volume_mwh`, `contract_period`, `demand_forecast_mwh`, `jepx_prices` all present and valid | `ok=True`, all fields normalized | |
| BL-02 | `MarketDataIngestionNode` — negative contracted volume | `contracted_volume_mwh=-1.0` | `ok=False`, error mentions "non-negative" | |
| BL-03 | `ProcurementPositionAnalysisNode` — gap and exposure calculation | demand sum > `contracted_volume_mwh`, known `jepx_prices` | `exposure_mwh > 0`, `exposure_value_jpy = exposure_mwh * latest jepx price` | |
| BL-04 | `ProcurementPositionAnalysisNode` — **zero exposure edge case** | `contracted_volume_mwh` exactly equals total forecast demand | `exposure_mwh == 0.0`, `exposure_value_jpy == 0.0` (no div-by-zero, no crash) | |
| BL-05 | `PriceForecastNode` — moving average + Bollinger Bands with sufficient history | ≥20 price points | `price_band_method="moving_average_bollinger_bands"`, `price_band_low < price_band_moving_average < price_band_high` | |
| BL-06 | `PriceForecastNode` — no price data | `jepx_prices=[]` | `price_band_method="insufficient_data"`, all band fields `None` | |
| BL-07 | `PriceForecastNode` — **single price point edge case** | `jepx_prices=[20.0]` | `price_band_method="moving_average_bollinger_bands"`; `price_band_low == price_band_high == price_band_moving_average == 20.0` (std=0, no crash) | |
| BL-08 | `StrategyRecommendationNode` — **conservative** risk appetite | valid `exposure_mwh` + price band | 3 options always computed; ranked ascending by `max_cost_risk` (worst-case cost minimized first) | |
| BL-09 | `StrategyRecommendationNode` — **aggressive** risk appetite | valid `exposure_mwh` + price band | 3 options always computed; ranked ascending by `expected_cost` | |
| BL-10 | `StrategyRecommendationNode` — **moderate** risk appetite (default) | valid `exposure_mwh` + price band | 3 options always computed; ranked by `max_cost_risk + expected_cost` | |
| BL-11 | `StrategyRecommendationNode` — **zero exposure edge case** | `exposure_mwh=0.0` | All 3 options compute to `expected_cost=0.0`, `max_cost_risk=0.0` (no crash) | |
| BL-12 | `StrategyRecommendationNode` — invalid `risk_appetite` string | `risk_appetite="yolo"` | Falls back to `"moderate"`, does not raise | |
| BL-13 | `ReportGenerationNode` — disclaimer presence | any valid exposure/forecast/strategy input | `executive_summary` and `formatted_output.disclaimer` contain the exact `DECISION_SUPPORT_DISCLAIMER` string | |
| BL-14 | `ReportGenerationNode` — risk table structure | strategy options with 3 entries | `formatted_output.risk_table` has one row per option with `expected_cost_jpy`/`max_cost_risk_jpy`/`recommended_timing` | |
| BL-15 | `PostProcessNode` S-3 — sensitive detail marker blocked | `formatted_output` containing a `_SENSITIVE_DETAIL_MARKERS` term (e.g. `"internal_margin"`) | `RuntimeError` raised before output leaves node boundary | |
| BL-16 | `MarketDataIngestionNode` — **empty/missing `contract_period` edge case** (T-GAP-01) | `contract_period=""` or key entirely absent from `input_context` | `ok=False`, error mentions "contract_period" — rejected the same way as any other invalid value, not silently accepted or defaulted | |

## Proof-of-Boundary Tests (Mandatory — 2 domain PB + scaffold defaults, this revision)

| PB-ID | Boundary | Test | Expected Result | Result |
|-------|----------|------|----------------|--------|
| PB-01 | S-1 trust gate | Invoke `PreProcessNode`/`MainNode`/`PostProcessNode` via `__call__()` with `caller_trust_level=ANONYMOUS` (below `VERIFIED_EXTERNAL`) | `execute()` never runs; `status=error` returned by the framework before business logic | |
| PB-02 | S-3 output content gate | `PostProcessNode` result missing the mandatory disclaimer, or containing a sensitive-detail marker | `_extra_security_gate_output()` raises `RuntimeError`; sensitive content never reaches the caller | |
| — | Import isolation (`test_import_isolation.py`) | AST scan of `src/` for `agenticstar`/Level-0 imports | 0 violations | |
| — | Invoke execution order (`test_pb_invoke_order.py`) | `__call__()`: S-1 → S-4 `node_start` → S-2 → `execute()` → S-3 → S-4 `node_complete` for every discovered `BaseNode` subclass | Order verified for `PreProcessNode`/`MainNode`/`PostProcessNode` | |
| — | State safety (`test_state_safety.py`) | Scan `src/schemas/state.py` for credential-like field names / prohibited types | 0 violations | |

## Test Execution Summary
- Execution date: _pending first CI run on `feature/implement-core-pipeline`_
- Total tests: _see tests/unit, tests/integration, tests/proof_of_boundary_
- Pass: / Fail: / Skip:
- Coverage: _pending `pytest --cov`_
