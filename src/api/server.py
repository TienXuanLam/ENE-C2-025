"""Standalone HTTP adapter for ENE-C2-025."""

import os
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel, Field

from framework.schemas.invocation_context import InvocationContext
from framework.schemas.trust_level import TrustLevel
from framework.secrets.context import bound_secrets
from framework.utils.config_loader import load_config
from shared.secrets import factory as secrets_factory
from src.graph.graph import WholesaleElectricityProcurementStrategyAgent

app = FastAPI(title="ENE-C2-025")
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"
_config = load_config(str(_CONFIG_PATH)) if _CONFIG_PATH.exists() else {}
_provider = secrets_factory(namespace="ENE", agent_name="WholesaleElectricityProcurementStrategyAgent")
agent = WholesaleElectricityProcurementStrategyAgent(config=_config)
_hitl_enabled = agent.config.get("hitl", {}).get("enabled", False)
_needs_checkpointer = agent.config.get("memory_enabled") or _hitl_enabled
agent.compile(checkpointer=MemorySaver() if _needs_checkpointer else None)
agent.provision_secrets(_provider)


class InvokeRequest(BaseModel):
    input: str
    session_id: str = ""
    input_context: dict[str, Any] = Field(default_factory=dict)


def _bearer_matches(supplied: str, expected: str) -> bool:
    return secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode())


def _resolve_trust(
    current: TrustLevel,
    authorization: str,
    external_token: str | None,
    internal_token: str | None,
) -> TrustLevel:
    if current is not TrustLevel.ANONYMOUS:
        return current
    if internal_token and _bearer_matches(authorization, internal_token):
        return TrustLevel.INTERNAL
    if external_token and _bearer_matches(authorization, external_token):
        return TrustLevel.VERIFIED_EXTERNAL
    if external_token or internal_token:
        raise HTTPException(status_code=401, detail="Token is invalid or expired.")
    return TrustLevel.ANONYMOUS


@app.post("/invoke")
async def invoke(req: InvokeRequest, request: Request) -> Any:
    trust = _resolve_trust(
        getattr(request.state, "trust_level", TrustLevel.ANONYMOUS),
        request.headers.get("authorization", ""),
        os.environ.get("INVOKE_AUTH_TOKEN"),
        os.environ.get("STG_INTERNAL_RUNNER_TOKEN"),
    )
    with bound_secrets(agent._secrets_provider):
        ctx = InvocationContext(
            session_id=req.session_id or str(uuid4()),
            caller_trust_level=trust,
            caller_id=getattr(request.state, "caller_id", ""),
        )
        return agent.invoke(req.input, ctx=ctx, input_context=req.input_context)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "agent": "WholesaleElectricityProcurementStrategyAgent"}
