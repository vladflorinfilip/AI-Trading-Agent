from __future__ import annotations

import logging
import re
import time
from typing import Any

from ..config import AgentConfig
from ..kraken_client import KrakenClient
from ..store import RunStore
from .market_analyst import MarketAnalyst
from .trader import Trader
from .risk_manager import RiskManager

log = logging.getLogger(__name__)

_TRADE_TOOL_NAMES = frozenset({"paper_buy", "paper_sell", "buy", "sell"})
MAX_RECENT_TRADES = 10


def _format_trade_summary(trades: list[dict], balance: dict | None) -> str:
    """Build a concise text block of recent trades + current balance for prompt injection."""
    lines: list[str] = []

    if balance:
        parts = []
        for asset, amt in sorted(balance.items()):
            try:
                val = float(amt) if not isinstance(amt, (int, float)) else amt
            except (ValueError, TypeError):
                continue
            if val > 0:
                parts.append(f"{asset}: {val:,.6f}" if val < 1 else f"{asset}: {val:,.2f}")
        if parts:
            lines.append(f"Current balance: {', '.join(parts)}")

    if not trades:
        lines.append("Recent trades: none yet.")
        return "\n".join(lines)

    lines.append(f"Recent trades (last {len(trades)}):")
    for t in trades:
        side = (t.get("type") or t.get("side") or "?").upper()
        pair = t.get("pair", "?")
        vol = t.get("vol") or t.get("volume") or "?"
        price = t.get("price", "?")
        cost = t.get("cost", "?")
        ts = t.get("time")
        age = ""
        if ts:
            try:
                delta = time.time() - float(ts)
                if delta < 3600:
                    age = f" ({int(delta / 60)}m ago)"
                elif delta < 86400:
                    age = f" ({delta / 3600:.1f}h ago)"
                else:
                    age = f" ({delta / 86400:.1f}d ago)"
            except (ValueError, TypeError):
                pass
        lines.append(f"  {side} {pair} vol={vol} @ ${price} cost=${cost}{age}")

    return "\n".join(lines)


def _extract_decision(trader_response: str) -> str:
    """Pull BUY/SELL/HOLD from the trader's response text."""
    upper = trader_response.upper()
    tag = re.search(r"DECISION[:\-\s]+(BUY|SELL|HOLD)", upper)
    if tag:
        return tag.group(1)
    first_buy = upper.find("BUY")
    first_sell = upper.find("SELL")
    if first_buy >= 0 and (first_sell < 0 or first_buy < first_sell):
        return "BUY"
    if first_sell >= 0:
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


def _parse_risk_decision(risk_response: str) -> tuple[str, float | None]:
    """Parse RISK-APPROVE / RISK-RESIZE <amt> / RISK-VETO from the risk manager."""
    upper = risk_response.upper()
    resize = re.search(r"RISK[:\-\s]*RESIZE\s+\$?([\d]+\.?\d*)", upper)
    if resize:
        return "RESIZE", float(resize.group(1))
    if "RISK-VETO" in upper or "RISK VETO" in upper:
        return "VETO", None
    return "APPROVE", None


class Orchestrator:
    """Runs the full pipeline: analyst -> trader -> risk gate -> decide."""

    def __init__(self, cfg: AgentConfig, store: RunStore | None = None):
        self.cfg = cfg
        self.kraken = KrakenClient(cfg.kraken)
        self.analyst = MarketAnalyst(cfg)
        self.trader = Trader(cfg)
        self.risk_mgr = RiskManager(cfg)
        self.store = store

    def _fetch_portfolio_context(self) -> str:
        """Pre-fetch balance + recent trades, filter to last N, return formatted text."""
        balance = None
        trades: list[dict] = []
        try:
            balance = self.kraken.paper_balance()
        except Exception as e:
            log.warning("[Orchestrator] failed to pre-fetch balance: %s", e)
        try:
            raw = self.kraken.paper_history()
            if isinstance(raw, dict):
                trades = raw.get("trades", raw.get("history", raw.get("orders", [])))
            elif isinstance(raw, list):
                trades = raw
            if isinstance(trades, dict):
                trades = list(trades.values())
            trades = [t for t in trades if isinstance(t, dict)]
            trades.sort(key=lambda t: float(t.get("time", 0)), reverse=True)
            trades = trades[:MAX_RECENT_TRADES]
        except Exception as e:
            log.warning("[Orchestrator] failed to pre-fetch history: %s", e)

        return _format_trade_summary(trades, balance)

    def run_pipeline(self, query: str) -> dict[str, Any]:
        """Full pipeline with traced output for each stage."""
        pairs = ", ".join(self.cfg.trading_pairs)

        # Pre-fetch portfolio context (balance + last N trades) once
        portfolio_ctx = self._fetch_portfolio_context()
        log.info("[Orchestrator] Portfolio context:\n%s", portfolio_ctx)

        # Stage 1: Market analysis with computed technical indicators
        analysis = self.analyst.run_traced(
            f"Analyse {pairs}. Call technical_signals for each pair, then provide your verdict."
        )

        # Stage 2: Trader proposes a trade based on analysis + portfolio context
        trade = self.trader.run_traced(
            f"## Your Current Portfolio\n{portfolio_ctx}\n\n"
            f"## Market Analysis\n{analysis['response']}\n\n"
            f"Based on this portfolio state and market analysis, decide whether to trade."
        )

        raw_decision = _extract_decision(trade["response"])

        # Stage 3: Structured extraction for reliable decision + amount
        amount_usd: float | None = None
        try:
            structured = self.trader._extract_decision(trade["response"])
            raw_decision = structured.get("action", raw_decision).upper()
            amount_usd = float(structured.get("amount_usd", 0))
            log.info("[Orchestrator] Structured extraction: %s $%.2f", raw_decision, amount_usd or 0)
        except Exception as e:
            log.warning("[Orchestrator] Structured extraction failed, using regex: %s", e)

        # Stage 4: Risk manager gates the trade (only for actionable trades)
        decision = raw_decision
        if decision in ("BUY", "SELL"):
            amt_str = f"${amount_usd:.2f}" if amount_usd else "unspecified amount"
            risk = self.risk_mgr.run_traced(
                f"## Proposed Trade\n{decision} {amt_str} of {pairs}.\n\n"
                f"## Portfolio State\n{portfolio_ctx}\n\n"
                f"## Market Context\n{analysis['response'][:500]}\n\n"
                f"Review this trade. Respond with RISK-APPROVE, RISK-RESIZE <amount>, or RISK-VETO."
            )
            risk_verdict, resize_amt = _parse_risk_decision(risk["response"])
            log.info("[Orchestrator] Risk verdict: %s (resize=%s)", risk_verdict, resize_amt)

            if risk_verdict == "VETO":
                decision = "HOLD"
                trade["response"] += f"\n\n[RISK MANAGER VETO]: {risk['response']}"
            elif risk_verdict == "RESIZE" and resize_amt is not None:
                amount_usd = resize_amt
                trade["response"] += f"\n\n[RISK MANAGER RESIZED to ${resize_amt:.2f}]: {risk['response']}"
        else:
            risk = self.risk_mgr.run_traced(
                f"## Portfolio State\n{portfolio_ctx}\n\n"
                f"No trade proposed. Check current portfolio risk. "
                f"Report concentration and any concerns briefly."
            )

        stages = [analysis, trade, risk]

        # Extract ATR from analyst tool calls for volatility-adjusted sizing
        atr = self._extract_atr(analysis)

        result: dict[str, Any] = {
            "stages": stages,
            "decision": decision,
            "total_duration_ms": sum(s["duration_ms"] for s in stages),
        }
        if amount_usd is not None:
            result["amount_usd"] = amount_usd
        if atr is not None:
            result["atr"] = atr

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
    @staticmethod
    def _extract_atr(analysis_stage: dict[str, Any]) -> float | None:
        """Pull ATR value from the analyst's tool call results."""
        for tc in analysis_stage.get("tool_calls", []):
            result = tc.get("result", {})
            if isinstance(result, dict) and "atr_14" in result:
                try:
                    return float(result["atr_14"])
                except (ValueError, TypeError):
                    pass
        # Fallback: parse from response text
        match = re.search(r"ATR\(?14\)?[:\s]*\$?([\d,]+\.?\d*)", analysis_stage.get("response", ""))
        if match:
            return float(match.group(1).replace(",", ""))
        return None

    def run_analysis_then_trade(self, market_question: str) -> dict[str, str]:
        """Legacy interface — returns plain text per stage."""
        result = self.run_pipeline(market_question)
        return {
            "analysis": result["stages"][0]["response"],
            "trade_action": result["stages"][1]["response"],
            "risk_check": result["stages"][2]["response"],
        }
