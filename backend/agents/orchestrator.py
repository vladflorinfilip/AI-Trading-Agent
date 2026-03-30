from __future__ import annotations

import re
from typing import Any

from ..config import AgentConfig
from ..store import RunStore
from .market_analyst import MarketAnalyst
from .trader import Trader
from .risk_manager import RiskManager


def _extract_decision(trader_response: str) -> str:
    """Pull BUY/SELL/HOLD from the trader's response text."""
    upper = trader_response.upper()
    for tc in trader_response.split():
        pass
    if re.search(r"\bBUY\b", upper):
        has_sell = bool(re.search(r"\bSELL\b", upper))
        if not has_sell:
            return "BUY"
    if re.search(r"\bSELL\b", upper):
        return "SELL"
    return "HOLD"


class Orchestrator:
    """Runs the full pipeline: analyst -> trader -> risk manager."""

    def __init__(self, cfg: AgentConfig, store: RunStore | None = None):
        self.cfg = cfg
        self.analyst = MarketAnalyst(cfg)
        self.trader = Trader(cfg)
        self.risk_mgr = RiskManager(cfg)
        self.store = store

    def run_pipeline(self, query: str) -> dict[str, Any]:
        """Full pipeline with traced output for each stage."""
        pairs = ", ".join(self.cfg.trading_pairs)

        analysis = self.analyst.run_traced(
            f"Analyse {pairs}. Provide a concise technical signal for each pair."
        )

        trade = self.trader.run_traced(
            f"Based on this market analysis, decide whether to trade:\n\n"
            f"{analysis['response']}"
        )

        risk = self.risk_mgr.run_traced(
            "Check current portfolio risk. Report concentration, "
            "unrealised PnL, and any concerns."
        )

        decision = _extract_decision(trade["response"])
        stages = [analysis, trade, risk]

        result = {
            "stages": stages,
            "decision": decision,
            "total_duration_ms": sum(s["duration_ms"] for s in stages),
        }

        if self.store:
            saved = self.store.save_run(query=query, stages=stages, decision=decision)
            result["id"] = saved["id"]
            result["timestamp"] = saved["timestamp"]

        return result

    def run_analysis_then_trade(self, market_question: str) -> dict[str, str]:
        """Legacy interface — returns plain text per stage."""
        result = self.run_pipeline(market_question)
        return {
            "analysis": result["stages"][0]["response"],
            "trade_action": result["stages"][1]["response"],
            "risk_check": result["stages"][2]["response"],
        }
