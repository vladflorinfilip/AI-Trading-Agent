from __future__ import annotations

import logging
import re
from typing import Any

from ..config import AgentConfig
from ..store import RunStore
from .market_analyst import MarketAnalyst
from .trader import Trader
from .risk_manager import RiskManager

log = logging.getLogger(__name__)

_TRADE_TOOL_NAMES = frozenset({"paper_buy", "paper_sell", "buy", "sell"})


def _extract_decision(trader_response: str) -> str:
    """Pull BUY/SELL/HOLD from the trader's response text."""
    upper = trader_response.upper()
    if re.search(r"\bBUY\b", upper) and not re.search(r"\bSELL\b", upper):
        return "BUY"
    if re.search(r"\bSELL\b", upper):
        return "SELL"
    return "HOLD"


def _extract_price(ticker: dict) -> float | None:
    """Get the last-trade price from a Kraken ticker response."""
    if "c" in ticker:
        c = ticker["c"]
        return float(c[0]) if isinstance(c, list) else float(c)
    for pair_data in ticker.values():
        if isinstance(pair_data, dict) and "c" in pair_data:
            c = pair_data["c"]
            return float(c[0]) if isinstance(c, list) else float(c)
    return None


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

        if decision in ("BUY", "SELL"):
            already_executed = any(
                tc["name"] in _TRADE_TOOL_NAMES
                for tc in trade.get("tool_calls", [])
            )
            if already_executed:
                log.info("[Orchestrator] trader already executed %s via tool call", decision)
            else:
                log.info("[Orchestrator] trader recommended %s but did not call tool — executing", decision)
                execution = self._execute_trade(trade["response"], decision)
                result["execution"] = execution

        if self.store:
            saved = self.store.save_run(query=query, stages=stages, decision=decision)
            result["id"] = saved["id"]
            result["timestamp"] = saved["timestamp"]

        return result

    def _execute_trade(self, trader_response: str, decision: str) -> dict:
        """Use the Trader's structured extraction to get trade params, then execute."""
        try:
            details = self.trader._extract_decision(trader_response)
        except Exception as e:
            log.warning("[Orchestrator] structured extraction failed: %s", e)
            return {"action": decision, "error": f"extraction failed: {e}"}

        action = details.get("action", "HOLD").upper()
        if action == "HOLD":
            return {"action": "HOLD", "skipped": True}

        pair = details.get("pair", "")
        amount_usd = float(details.get("amount_usd", 0))
        if not pair or amount_usd <= 0:
            log.warning("[Orchestrator] invalid trade params: pair=%s amount=%.2f", pair, amount_usd)
            return {"action": action, "pair": pair, "error": "invalid pair or amount"}

        try:
            ticker_data = self.trader.kraken.ticker(pair)
            price = _extract_price(ticker_data)
            if not price or price <= 0:
                return {"action": action, "pair": pair, "error": f"could not get price for {pair}"}

            volume = amount_usd / price
            if "BTC" in pair.upper() or "XBT" in pair.upper():
                volume_str = f"{volume:.5f}"
            else:
                volume_str = f"{volume:.3f}"

            if action == "BUY":
                trade_result = self.trader.kraken.paper_buy(pair=pair, volume=volume_str)
            else:
                trade_result = self.trader.kraken.paper_sell(pair=pair, volume=volume_str)

            log.info("[Orchestrator] paper %s %s %s @ $%.2f → %s",
                     action, volume_str, pair, price, trade_result)
            return {
                "action": action, "pair": pair, "volume": volume_str,
                "amount_usd": amount_usd, "price": price, "result": trade_result,
            }
        except Exception as e:
            log.error("[Orchestrator] trade execution failed: %s", e)
            return {"action": action, "pair": pair, "error": str(e)}

    def run_analysis_then_trade(self, market_question: str) -> dict[str, str]:
        """Legacy interface — returns plain text per stage."""
        result = self.run_pipeline(market_question)
        return {
            "analysis": result["stages"][0]["response"],
            "trade_action": result["stages"][1]["response"],
            "risk_check": result["stages"][2]["response"],
        }
