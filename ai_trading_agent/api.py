"""FastAPI backend — exposes Kraken data and agent actions as REST endpoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import AgentConfig
from .kraken_client import KrakenClient, KrakenCLIError
from .agents import Trader

log = logging.getLogger(__name__)

cfg = AgentConfig()
kraken = KrakenClient(cfg.kraken)
trader: Trader | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global trader
    trader = Trader(cfg)
    try:
        kraken.paper_init(
            balance=cfg.kraken.paper_starting_balance,
            currency=cfg.kraken.default_currency,
        )
    except KrakenCLIError:
        pass
    log.info("API ready")
    yield


app = FastAPI(title="AI Trading Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
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
        response = trader.run(req.message)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
