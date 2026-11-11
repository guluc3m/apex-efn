"""Simulation web UI (D5-11): a fake marketplace and the AI buyers working it.

The page is a single HTML file served by this tiny FastAPI app. It runs the scenario through
:func:`apex.negotiation.sim.pipeline.run_scenario` and renders the report: the catalogue the fake
marketplace exposes, and one panel per AI buyer with its offer ladder, its conversation and how it ended.

Nothing here is a product surface. It exists so the loop can be watched end to end without a real
marketplace, a real LLM vendor, a database or Docker.

Run it with the marketplace and the LLM stub up::

    LLM stub:        cd apps/llm-stub && uv run python -m llm_stub        # :8001
    Fake market:     cd apps/mock-marketplace && pnpm dev                  # :8002 (MOCK_* env)
    This UI:         cd apps/orchestrator && uv run python -m apex.negotiation.sim.server   # :8003
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from apex.common.clock import SystemClock
from apex.negotiation.sim.market import HttpMarketplace
from apex.negotiation.sim.models import BuyerProfile, ScenarioConfig
from apex.negotiation.sim.pipeline import SimContext, default_engine_factory, run_scenario
from apex.negotiation.sim.session import SimSession
from apex.negotiation.sim.stub_llm import build_gateway

DEFAULT_MARKETPLACE_URL = "http://127.0.0.1:8002"
DEFAULT_LLM_URL = "http://127.0.0.1:8001"
DEFAULT_QUANTITY = 5000
DEFAULT_PORT = 8003

UI_FILE = Path(__file__).with_name("ui") / "index.html"

#: Demo buyers. Scenario inputs, not product defaults: three budgets so the gate and the agreement both appear.
DEFAULT_BUYERS: tuple[BuyerProfile, ...] = (
    BuyerProfile(
        id="buyer-a",
        name="Ana (clinic chain, tight margin)",
        quantity=5000,
        currency="EUR",
        target_discount_bp=1200,
        max_discount_bp=1500,
        account_id="acct-buyer-a",
    ),
    BuyerProfile(
        id="buyer-b",
        name="Bruno (packaging reseller)",
        quantity=2000,
        currency="EUR",
        target_discount_bp=200,
        max_discount_bp=1200,
        account_id="acct-buyer-b",
    ),
    BuyerProfile(
        id="buyer-c",
        name="Chen (import desk, CNY)",
        quantity=20000,
        currency="CNY",
        target_discount_bp=600,
        max_discount_bp=1400,
        account_id="acct-buyer-c",
    ),
)


class ScenarioRequest(BaseModel):
    """What the page may override. Everything else comes from the demo configuration above."""

    model_config = ConfigDict(extra="forbid")

    marketplace_url: str | None = None
    llm_url: str | None = None
    llm_api_key: str | None = Field(default=None, repr=False)
    llm_model: str | None = None
    quantity: int | None = Field(default=None, gt=0)
    buyer_count: int | None = Field(default=None, ge=1, le=len(DEFAULT_BUYERS))


def default_config(
    *,
    marketplace_url: str | None = None,
    llm_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
    quantity: int | None = None,
    buyer_count: int | None = None,
) -> ScenarioConfig:
    """The scenario the page runs: the request first, then the environment, then the demo defaults."""
    market = marketplace_url or os.environ.get("SIM_MARKETPLACE_URL") or DEFAULT_MARKETPLACE_URL
    llm = llm_url or os.environ.get("SIM_LLM_URL") or DEFAULT_LLM_URL
    key = llm_api_key or os.environ.get("SIM_LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
    model = llm_model or os.environ.get("SIM_LLM_MODEL")
    selected = list(DEFAULT_BUYERS)[: buyer_count or len(DEFAULT_BUYERS)]
    return ScenarioConfig(
        marketplace_url=market,
        llm_url=llm,
        llm_api_key=key,
        llm_model=model,
        quantity=quantity or DEFAULT_QUANTITY,
        buyers=selected,
    )


class StepRequest(BaseModel):
    """Which chat to advance. Omitted: advance every chat by one message (one round)."""

    model_config = ConfigDict(extra="forbid")

    buyer_id: str | None = None


app = FastAPI(title="APEX-EFN simulation", docs_url=None, redoc_url=None)

#: Live runs, keyed by run id. One demo at a time: starting a new one closes the previous.
_sessions: dict[str, SimSession] = {}


async def _close_sessions() -> None:
    for session in list(_sessions.values()):
        await session.close()
    _sessions.clear()


def _session(run_id: str) -> SimSession:
    session = _sessions.get(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown run")
    return session


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(UI_FILE.read_text(encoding="utf-8"))


@app.get("/api/config")
async def config() -> dict[str, Any]:
    """What the page needs to show before the first run."""
    scenario = default_config()
    return {
        "marketplace_url": scenario.marketplace_url,
        "llm_url": scenario.llm_url,
        "quantity": scenario.quantity,
        "buyers": [profile.model_dump() for profile in scenario.buyers],
    }


@app.post("/api/session")
async def start_session(request: ScenarioRequest | None = None) -> JSONResponse:
    """Open the threads and draft the opening message of every buyer, nothing more."""
    body = request or ScenarioRequest()
    scenario = default_config(
        marketplace_url=body.marketplace_url,
        llm_url=body.llm_url,
        llm_api_key=body.llm_api_key,
        llm_model=body.llm_model,
        quantity=body.quantity,
        buyer_count=body.buyer_count,
    )
    await _close_sessions()
    marketplace = HttpMarketplace(
        scenario.marketplace_url,
        llm_url=scenario.llm_url,
        llm_api_key=scenario.llm_api_key,
        llm_model=scenario.llm_model,
    )
    run_id = uuid4().hex[:8]
    ctx = SimContext(
        market=marketplace,
        gateway=build_gateway(
            scenario.llm_url, api_key=scenario.llm_api_key, model=scenario.llm_model
        ),
        clock=SystemClock(),
        config=scenario,
        run_id=run_id,
    )
    session = SimSession(
        scenario,
        marketplace,
        ctx,
        default_engine_factory,
        run_id,
        owns_marketplace=True,
    )
    try:
        await session.start()
    except Exception:
        await session.close()
        raise
    _sessions[run_id] = session
    return JSONResponse(await session.view())


@app.post("/api/session/{run_id}/step")
async def step_session(run_id: str, body: StepRequest | None = None) -> JSONResponse:
    """Advance one chat (or all of them) by one exchange. This is where the model is called."""
    session = _session(run_id)
    await session.step(body.buyer_id if body else None)
    return JSONResponse(await session.view())


@app.post("/api/session/{run_id}/all")
async def finish_session(run_id: str) -> JSONResponse:
    """Run every chat to its end at once, for when nobody wants to click."""
    session = _session(run_id)
    await session.run_all()
    return JSONResponse(await session.view())


@app.get("/api/session/{run_id}")
async def read_session(run_id: str) -> JSONResponse:
    return JSONResponse(await _session(run_id).view())


@app.delete("/api/session/{run_id}")
async def close_session(run_id: str) -> dict[str, bool]:
    session = _sessions.pop(run_id, None)
    if session is not None:
        await session.close()
    return {"closed": session is not None}


@app.post("/api/scenario")
async def run(request: ScenarioRequest | None = None) -> JSONResponse:
    body = request or ScenarioRequest()
    scenario = default_config(
        marketplace_url=body.marketplace_url,
        llm_url=body.llm_url,
        llm_api_key=body.llm_api_key,
        llm_model=body.llm_model,
        quantity=body.quantity,
        buyer_count=body.buyer_count,
    )
    report = await run_scenario(scenario)
    return JSONResponse(report.model_dump(mode="json"))


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run(
        "apex.negotiation.sim.server:app",
        host=os.environ.get("SIM_HOST", "127.0.0.1"),
        port=int(os.environ.get("SIM_PORT", str(DEFAULT_PORT))),
        log_level=os.environ.get("SIM_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":  # pragma: no cover
    main()
