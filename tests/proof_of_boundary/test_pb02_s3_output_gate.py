# PB-02: S-3 Output Content Gate Boundary
#
# Verifies that _extra_security_gate_output() on PostProcessNode blocks output
# that is missing the mandatory decision-support disclaimer (proposal §11
# Risk #4) or that contains a commercially sensitive trading-strategy detail
# marker (proposal §2-3 point 2) — content never reaches the caller in either
# case.
#
# Requires `framework`/`shared` (agenticstar-agentcore wheel).

import pytest

from src.nodes.post_process_node import PostProcessNode
from src.services.report_generation_service import DECISION_SUPPORT_DISCLAIMER


class TestPB02PostProcessNodeContentGate:
    def test_missing_disclaimer_blocks_output(self):
        node = PostProcessNode()
        with pytest.raises(RuntimeError, match="disclaimer"):
            node._extra_security_gate_output({"executive_summary": "Status: analyzed", "formatted_output": {}})

    def test_sensitive_detail_marker_in_summary_blocks_output(self):
        node = PostProcessNode()
        with pytest.raises(RuntimeError, match="sensitive trading-strategy detail"):
            node._extra_security_gate_output(
                {
                    "executive_summary": DECISION_SUPPORT_DISCLAIMER + " trading_policy: aggressive",
                    "formatted_output": {},
                }
            )

    def test_sensitive_detail_marker_in_risk_table_timing_blocks_output(self):
        # F-04: scan is scoped to executive_summary + risk_table[].recommended_timing.
        node = PostProcessNode()
        with pytest.raises(RuntimeError, match="sensitive trading-strategy detail"):
            node._extra_security_gate_output(
                {
                    "executive_summary": DECISION_SUPPORT_DISCLAIMER,
                    "formatted_output": {
                        "risk_table": [{"option": "buy_now", "recommended_timing": "trading_policy: aggressive"}]
                    },
                }
            )

    def test_present_disclaimer_and_clean_content_passes_through(self):
        node = PostProcessNode()
        payload = {
            "executive_summary": DECISION_SUPPORT_DISCLAIMER,
            "formatted_output": {"risk_table": [{"option": "buy_now", "recommended_timing": "immediate"}]},
        }
        result = node._extra_security_gate_output(payload)
        assert result == payload
