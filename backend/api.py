"""FastAPI backend — exposes Kraken data, agent actions, and pipeline history."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import AgentConfig
from .kraken_client import KrakenClient, KrakenCLIError
from .agents import Trader, Orchestrator
from .store import RunStore

log = logging.getLogger(__name__)

cfg = AgentConfig()
kraken = KrakenClient(cfg.kraken)
store = RunStore()
trader: Trader | None = None
orchestrator: Orchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global trader, orchestrator
    trader = Trader(cfg)
    orchestrator = Orchestrator(cfg, store=store)
    try:
        kraken.paper_init(
            balance=cfg.kraken.paper_starting_balance,
            currency=cfg.kraken.default_currency,
        )
    except KrakenCLIError:
        pass
    log.info("API ready | redis=%s", store.connected)
    yield


app = FastAPI(title="AI Trading Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


def _kraken_call(fn, *args, **kwargs) -> Any:
    try:
        return fn(*args, **kwargs)
    except KrakenCLIError as e:
        raise HTTPException(status_code=502, detail=str(e))


# -- Market data --------------------------------------------------------------

@app.get("/api/status")
def get_status():
    return _kraken_call(kraken.status)


@app.get("/api/ticker/{pair:path}")
def get_ticker(pair: str):
    data = _kraken_call(kraken.ticker, pair)
    for key in data:
        return data[key]
    return data


@app.get("/api/ohlc/{pair:path}")
def get_ohlc(pair: str, interval: int = 60):
    return _kraken_call(kraken.ohlc, pair, interval)


# -- Paper trading -------------------------------------------------------------

@app.get("/api/paper/balance")
def get_paper_balance():
    data = _kraken_call(kraken.paper_balance)
    return data.get("balances", data)


@app.get("/api/paper/positions")
def get_paper_positions():
    return _kraken_call(kraken.paper_positions)


@app.get("/api/paper/status")
def get_paper_status():
    return _kraken_call(kraken.paper_status)


@app.get("/api/paper/history")
def get_paper_history():
    return _kraken_call(kraken.paper_history)


# -- Agent ---------------------------------------------------------------------

class AgentRequest(BaseModel):
    message: str = "Analyse BTC/USD and trade if you see an opportunity."


@app.post("/api/agent/run")
def run_agent(req: AgentRequest):
    if trader is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    try:
        result = trader.run_traced(req.message)
        return result
    except Exception as e:
        log.exception("Agent run failed")
        raise HTTPException(status_code=500, detail=str(e))


# -- Pipeline ------------------------------------------------------------------

class PipelineRequest(BaseModel):
    query: str = "Analyse the market and trade if you see an opportunity."


@app.post("/api/pipeline/run")
def run_pipeline(req: PipelineRequest):
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")
    try:
        return orchestrator.run_pipeline(req.query)
    except Exception as e:
        log.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(e))


# -- History -------------------------------------------------------------------

@app.get("/api/history")
def get_history(limit: int = 50):
    return store.list_runs(limit=limit)


@app.get("/api/history/{run_id}")
def get_history_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
