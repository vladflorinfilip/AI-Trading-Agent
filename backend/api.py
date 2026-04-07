"""FastAPI backend — exposes Kraken data, agent actions, and pipeline history."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
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
    data = _kraken_call(kraken.paper_history)
    if isinstance(data, dict):
        trades = data.get("trades", data.get("history", data.get("orders", [])))
    else:
        trades = data if isinstance(data, list) else []
    if isinstance(trades, dict):
        trades = list(trades.values())
    if not isinstance(trades, list):
        trades = []
    return trades


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
def get_history(limit: int = 200, from_ts: float | None = None, to_ts: float | None = None):
    return store.list_runs(limit=limit, from_ts=from_ts, to_ts=to_ts)


@app.get("/api/history/{run_id}")
def get_history_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


# -- Metrics -------------------------------------------------------------------

@app.get("/api/metrics/portfolio")
def get_portfolio_metrics():
    """Live portfolio summary: value, PnL, trade stats, and time series."""
    starting_balance = cfg.kraken.paper_starting_balance

    try:
        raw = kraken.paper_balance()
        balances = raw.get("balances", raw)
    except KrakenCLIError:
        balances = {}

    btc_price = 0.0
    try:
        td = kraken.ticker("BTC/USD")
        for v in td.values():
            btc_price = float(v.get("c", [0])[0])
            break
    except KrakenCLIError:
        pass

    usd = float((balances.get("USD") or {}).get("total", 0))
    btc = float(
        (balances.get("XBT") or balances.get("BTC") or {}).get("total", 0)
    )
    eth = float((balances.get("ETH") or {}).get("total", 0))

    eth_price = 0.0
    try:
        td = kraken.ticker("ETH/USD")
        for v in td.values():
            eth_price = float(v.get("c", [0])[0])
            break
    except KrakenCLIError:
        pass

    total = usd + btc * btc_price + eth * eth_price
    pnl = total - starting_balance
    pnl_pct = (pnl / starting_balance * 100) if starting_balance else 0

    try:
        trades = kraken.paper_history()
        if isinstance(trades, dict):
            trades = trades.get("trades", trades.get("history", []))
        if not isinstance(trades, list):
            trades = []
    except KrakenCLIError:
        trades = []

    buys = sum(
        1 for t in trades
        if str(t.get("side", t.get("type", ""))).lower() == "buy"
    )
    sells = len(trades) - buys

    store.save_pnl_snapshot(total)
    pnl_series = store.get_pnl_snapshots()
    if not pnl_series:
        now = datetime.now(timezone.utc).timestamp()
        pnl_series = [{"ts": round(now), "value": round(total, 2)}]

    return {
        "starting_balance": starting_balance,
        "total_value": round(total, 2),
        "usd_balance": round(usd, 2),
        "btc_balance": btc,
        "btc_price": round(btc_price, 2),
        "eth_balance": eth,
        "eth_price": round(eth_price, 2),
        "pnl": round(pnl, 2),
        "pnl_pct": round(pnl_pct, 2),
        "trade_count": len(trades),
        "buy_count": buys,
        "sell_count": sells,
        "pnl_series": pnl_series,
    }


@app.get("/api/metrics/performance")
def get_performance_metrics():
    """Decision distribution + pipeline stats from run history."""
    runs = store.list_runs(limit=200)
    total = len(runs)
    if total == 0:
        return {
            "total_runs": 0,
            "decisions": {"BUY": 0, "SELL": 0, "HOLD": 0},
            "avg_duration_ms": 0,
            "error_count": 0,
            "last_run": None,
        }

    decisions: dict[str, int] = {"BUY": 0, "SELL": 0, "HOLD": 0}
    total_duration = 0
    error_count = 0
    for r in runs:
        d = (r.get("decision") or "HOLD").upper()
        decisions[d] = decisions.get(d, 0) + 1
        total_duration += r.get("total_duration_ms", 0)
        if r.get("error"):
            error_count += 1

    return {
        "total_runs": total,
        "decisions": decisions,
        "avg_duration_ms": round(total_duration / total) if total else 0,
        "error_count": error_count,
        "last_run": runs[0].get("timestamp") if runs else None,
    }


# -- On-chain metrics (pushed by the TS agent) ---------------------------------

@app.post("/api/metrics/onchain")
def post_onchain_metrics(data: dict):
    """Receive on-chain metrics from the erc8004 TS agent."""
    store.save_onchain_metrics(data)
    return {"ok": True}


@app.get("/api/metrics/onchain")
def get_onchain_metrics():
    """Return the latest on-chain metrics cached by the TS agent."""
    metrics = store.get_onchain_metrics()
    if not metrics:
        return {
            "agentId": 0,
            "attestationCount": 0,
            "validationScore": 0,
            "reputationScore": 0,
            "tradesThisHour": 0,
            "tradeWindowStart": 0,
            "maxTradesPerHour": 10,
            "maxPositionUsd": 500,
            "timestamp": 0,
        }
    return metrics


# -- LLM provider metrics -----------------------------------------------------

@app.get("/api/metrics/llm")
def get_llm_metrics():
    """Return Gemini vs Mistral call counts and fallback stats."""
    raw = store.get_llm_stats()
    return {
        "gemini_calls": raw.get("gemini:calls", 0),
        "mistral_calls": raw.get("mistral:calls", 0),
        "fallbacks": raw.get("fallbacks", 0),
        "by_agent": {
            "gemini": {k.split(":", 1)[1]: v for k, v in raw.items() if k.startswith("gemini:") and k != "gemini:calls"},
            "mistral": {k.split(":", 1)[1]: v for k, v in raw.items() if k.startswith("mistral:") and k != "mistral:calls"},
        },
    }
