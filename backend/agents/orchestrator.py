from __future__ import annotations

import json
import re
import time
from typing import Any

from ..config import AgentConfig
from ..kraken_client import KrakenClient
from ..store import RunStore
from .market_analyst import MarketAnalyst
from .trader import Trader
from .risk_manager import RiskManager

_TRADE_TOOL_NAMES = frozenset({"paper_buy", "paper_sell", "buy", "sell"})
MAX_TRADES_PER_PAIR = 10


def _format_age(ts) -> str:
    """Human-readable age string from a Unix timestamp."""
    try:
        delta = time.time() - float(ts)
        if delta < 3600:
            return f" ({int(delta / 60)}m ago)"
        if delta < 86400:
            return f" ({delta / 3600:.1f}h ago)"
        return f" ({delta / 86400:.1f}d ago)"
    except (ValueError, TypeError):
        return ""


def _format_trade_line(t: dict) -> str:
    side = (t.get("type") or t.get("side") or "?").upper()
    vol = t.get("vol") or t.get("volume") or "?"
    price = t.get("price", "?")
    cost = t.get("cost", "?")
    age = _format_age(t.get("time"))
    return f"  {side} vol={vol} @ ${price} cost=${cost}{age}"


def _pair_matches(trade_pair: str, target_pair: str) -> bool:
    """Fuzzy match a trade's pair field against a target pair name."""
    tp = trade_pair.upper().replace("/", "")
    tgt = target_pair.upper().replace("/", "")
    return tp == tgt or tp in tgt or tgt in tp


def _format_trade_summary(trades: list[dict], balance: dict | None, pairs: list[str]) -> str:
    """Build a portfolio summary grouped by asset with per-pair trade history."""
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

    by_pair: dict[str, list[dict]] = {p: [] for p in pairs}
    unmatched: list[dict] = []
    for t in trades:
        trade_pair = t.get("pair", "?")
        matched = False
        for p in pairs:
            if _pair_matches(trade_pair, p):
                if len(by_pair[p]) < MAX_TRADES_PER_PAIR:
                    by_pair[p].append(t)
                matched = True
                break
        if not matched:
            unmatched.append(t)

    for pair in pairs:
        pair_trades = by_pair[pair]
        if not pair_trades:
            lines.append(f"\n{pair}: no recent trades")
        else:
            lines.append(f"\n{pair} — last {len(pair_trades)} trades:")
            for t in pair_trades:
                lines.append(_format_trade_line(t))

    return "\n".join(lines)


def _parse_usd(raw: str | None) -> float:
    if not raw:
        return 0.0
    try:
        return float(str(raw).replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def _extract_decisions(trader_response: str) -> list[dict]:
    """Parse per-pair decisions from JSON or legacy DECISIONS: lines."""
    text = (trader_response or "").strip()
    if text.startswith("{") or text.startswith("```"):
        try:
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
                text = re.sub(r"\s*```\s*$", "", text)
            data = json.loads(text)
            decs = data.get("decisions", [])
            return [
                {
                    "pair": d.get("pair", ""),
                    "action": str(d.get("action", "HOLD")).upper(),
                    "amount_usd": float(d.get("amount_usd", 0)),
                    "max_slippage_bps": int(d.get("max_slippage_bps", 50)),
                    "rationale": d.get("rationale", ""),
                }
                for d in decs
                if isinstance(d, dict)
            ]
        except (json.JSONDecodeError, TypeError, ValueError, KeyError):
            pass

    results: list[dict] = []
    pattern = re.compile(
        r"([A-Z]{3,10}USD)\s*:\s*(BUY|SELL|HOLD)\s*(\$[\d,.]+)?",
        re.IGNORECASE,
    )
    for m in pattern.finditer(trader_response):
        results.append(
            {
                "pair": m.group(1).upper(),
                "action": m.group(2).upper(),
                "amount_usd": _parse_usd(m.group(3)),
                "max_slippage_bps": 50,
                "rationale": "",
            }
        )
    if results:
        return results

    upper = trader_response.upper()
    tag = re.search(r"DECISION[:\-\s]+(BUY|SELL|HOLD)", upper)
    if tag:
        return [{"pair": "", "action": tag.group(1), "amount_usd": 0.0, "max_slippage_bps": 50, "rationale": ""}]
    first_buy = upper.find("BUY")
    first_sell = upper.find("SELL")
    if first_buy >= 0 and (first_sell < 0 or first_buy < first_sell):
        return [{"pair": "", "action": "BUY", "amount_usd": 0.0, "max_slippage_bps": 50, "rationale": ""}]
    if first_sell >= 0:
        return [{"pair": "", "action": "SELL", "amount_usd": 0.0, "max_slippage_bps": 50, "rationale": ""}]
    return [{"pair": "", "action": "HOLD", "amount_usd": 0.0, "max_slippage_bps": 50, "rationale": ""}]


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


def _extract_total_balance(entry: Any) -> float:
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, dict):
        try:
            return float(entry.get("total", 0))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _candidate_asset_symbols(pair: str) -> list[str]:
    base = pair.upper().replace("/", "")
    if base.endswith("USD"):
        base = base[:-3]
    out = [base]
    if base == "BTC":
        out.append("XBT")
    elif base == "XBT":
        out.append("BTC")
    elif base == "POL":
        out.append("MATIC")
    elif base == "MATIC":
        out.append("POL")
    return out


def _parse_risk_decisions(risk_response: str) -> dict[str, tuple[str, float | None]]:
    """Parse per-pair risk verdicts from the risk manager's response.

    Returns a dict mapping pair -> (verdict, resize_amount).
    Verdict is one of: "APPROVE", "RESIZE", "VETO".
    """
    results: dict[str, tuple[str, float | None]] = {}
    pattern = re.compile(
        r"([A-Z]{3,10}USD)\s*:\s*RISK[:\-\s]*(APPROVE|VETO|RESIZE)\s*(\$?[\d,.]+)?",
        re.IGNORECASE,
    )
    for m in pattern.finditer(risk_response):
        pair = m.group(1).upper()
        verdict = m.group(2).upper()
        amt: float | None = None
        if verdict == "RESIZE" and m.group(3):
            try:
                amt = float(m.group(3).replace("$", "").replace(",", ""))
            except ValueError:
                pass
        results[pair] = (verdict, amt)

    if results:
        return results

    # Fallback: parse a blanket verdict and apply to all pairs
    upper = risk_response.upper()
    resize = re.search(r"RISK[:\-\s]*RESIZE\s+\$?([\d]+\.?\d*)", upper)
    if resize:
        return {"__ALL__": ("RESIZE", float(resize.group(1)))}
    if "RISK-VETO" in upper or "RISK VETO" in upper:
        return {"__ALL__": ("VETO", None)}
    return {"__ALL__": ("APPROVE", None)}


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
        """Pre-fetch balance + recent trades grouped by pair, return formatted text."""
        balance = None
        trades: list[dict] = []
        try:
            balance = self.kraken.paper_balance()
        except Exception:
            pass
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
        except Exception:
            pass

        return _format_trade_summary(trades, balance, self.cfg.trading_pairs)

    def run_pipeline(self, query: str) -> dict[str, Any]:
        """Full pipeline with traced output for each stage."""
        pairs = ", ".join(self.cfg.trading_pairs)

        portfolio_ctx = self._fetch_portfolio_context()

        # Stage 1: Market analysis
        analysis = self.analyst.run_traced(
            f"Analyse {pairs}. Call technical_signals for each pair, then provide "
            f"your structured report per pair."
        )

        # Stage 2: Trader proposes per-pair decisions
        trade = self.trader.run_traced(
            f"## Your Current Portfolio\n{portfolio_ctx}\n\n"
            f"## Market Analysis\n{analysis['response']}\n\n"
            f"Based on this portfolio state and market analysis, propose one trade "
            f"decision per configured pair. The pipeline will ask you for structured JSON."
        )

        raw_decisions = trade.get("parsed_decisions")
        if not raw_decisions:
            raw_decisions = _extract_decisions(trade["response"])
            try:
                structured = self.trader._extract_decisions(trade["response"])
                if structured:
                    raw_decisions = [
                        {
                            "pair": d.get("pair", ""),
                            "action": d.get("action", "HOLD").upper(),
                            "amount_usd": float(d.get("amount_usd", 0)),
                            "max_slippage_bps": int(d.get("max_slippage_bps", 50)),
                            "rationale": d.get("rationale", ""),
                        }
                        for d in structured
                    ]
            except Exception:
                pass

        actionable = [d for d in raw_decisions if d.get("action") in ("BUY", "SELL")]
        has_trades = len(actionable) > 0

        # Keep only one high-confidence actionable decision to improve intent quality.
        if has_trades:
            ranked = sorted(
                actionable,
                key=lambda d: (
                    float(d.get("confidence", 0.0)),
                    float(d.get("amount_usd", 0.0)),
                ),
                reverse=True,
            )
            best = ranked[0]
            best_key = (best.get("pair", ""), best.get("action", ""))
            for d in raw_decisions:
                key = (d.get("pair", ""), d.get("action", ""))
                if d.get("action") in ("BUY", "SELL") and key != best_key:
                    d["dropped_by_selector"] = True
                    d["original_action"] = d["action"]
                    d["action"] = "HOLD"
                    d["amount_usd"] = 0.0
                    d["rationale"] = (
                        f"{d.get('rationale', '')} "
                        "[downgraded to HOLD: lower confidence than top trade]"
                    ).strip()
            actionable = [d for d in raw_decisions if d.get("action") in ("BUY", "SELL")]
            has_trades = len(actionable) > 0

        # Stage 3: Risk manager evaluates each proposed trade individually
        if has_trades:
            trade_lines = "\n".join(
                f"  {d.get('pair', '?')}: {d['action']} ${d.get('amount_usd', '?')}"
                for d in actionable
            )
            risk = self.risk_mgr.run_traced(
                f"## Proposed Trades\n{trade_lines}\n\n"
                f"## Portfolio State\n{portfolio_ctx}\n\n"
                f"## Market Context\n{analysis['response'][:800]}\n\n"
                f"Review EACH trade individually. Output a RISK DECISIONS block "
                f"with one verdict per trade (RISK-APPROVE, RISK-RESIZE $amount, or RISK-VETO)."
            )
            risk_verdicts = _parse_risk_decisions(risk["response"])

            # Apply per-pair risk verdicts to decisions
            for d in raw_decisions:
                if d.get("action") not in ("BUY", "SELL"):
                    continue
                pair = d.get("pair", "").upper()
                verdict, resize_amt = risk_verdicts.get(
                    pair, risk_verdicts.get("__ALL__", ("APPROVE", None))
                )
                d["risk_verdict"] = verdict
                if verdict == "VETO":
                    d["original_action"] = d["action"]
                    d["action"] = "HOLD"
                    d["vetoed"] = True
                elif verdict == "RESIZE" and resize_amt is not None:
                    d["original_amount_usd"] = d.get("amount_usd")
                    d["amount_usd"] = resize_amt

            trade["response"] += f"\n\n[RISK MANAGER]: {risk['response']}"
        else:
            risk = self.risk_mgr.run_traced(
                f"## Portfolio State\n{portfolio_ctx}\n\n"
                f"No trades proposed. Check current portfolio risk. "
                f"Report concentration and any concerns briefly."
            )

        stages = [analysis, trade, risk]
        atr = self._extract_atr(analysis)

        # Determine the summary decision for backward compatibility
        actions = [d.get("action", "HOLD") for d in raw_decisions]
        unique_actions = set(actions) - {"HOLD"}
        if not unique_actions:
            summary_decision = "HOLD"
        elif unique_actions == {"BUY"}:
            summary_decision = "BUY"
        elif unique_actions == {"SELL"}:
            summary_decision = "SELL"
        else:
            summary_decision = "MULTI"

        result: dict[str, Any] = {
            "stages": stages,
            "decision": summary_decision,
            "decisions": raw_decisions,
            "total_duration_ms": sum(s["duration_ms"] for s in stages),
        }
        if atr is not None:
            result["atr"] = atr

        # Execute only trades that passed risk review
        executions: list[dict] = []
        for d in raw_decisions:
            if d.get("action") not in ("BUY", "SELL"):
                continue
            if d.get("vetoed"):
                continue
            pair = d.get("pair", "")
            amount_usd = float(d.get("amount_usd", 0))
            if not pair or amount_usd <= 0:
                continue
            execution = self._execute_trade_for_pair(pair, d["action"], amount_usd)
            executions.append(execution)

        if executions:
            result["executions"] = executions

        if self.store:
            saved = self.store.save_run(query=query, stages=stages, decision=summary_decision)
            result["id"] = saved["id"]
            result["timestamp"] = saved["timestamp"]
            for s in stages:
                provider = s.get("provider", "unknown")
                self.store.record_llm_call(provider, s.get("agent", ""), fallback=s.get("fallback", False))

        return result

    def _execute_trade_for_pair(self, pair: str, action: str, amount_usd: float) -> dict:
        """Execute a single trade for a given pair."""
        if not pair or amount_usd <= 0:
            return {"action": action, "pair": pair, "error": "invalid pair or amount"}

        if amount_usd < self.cfg.min_trade_usd:
            return {
                "action": action,
                "pair": pair,
                "error": f"amount ${amount_usd:.2f} below min_trade_usd ${self.cfg.min_trade_usd:.2f}",
            }

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

            # Pre-execution guard: ensure balance/position can support the intent.
            try:
                bal_raw = self.trader.kraken.paper_balance()
                balances = bal_raw.get("balances", bal_raw) if isinstance(bal_raw, dict) else {}
            except Exception:
                balances = {}

            usd_available = _extract_total_balance(
                (balances or {}).get("USD") or (balances or {}).get("ZUSD")
            )
            if action == "BUY" and usd_available + 1e-9 < amount_usd:
                return {
                    "action": action,
                    "pair": pair,
                    "error": f"insufficient USD balance (${usd_available:.2f}) for ${amount_usd:.2f} buy",
                }

            if action == "SELL":
                sell_available = 0.0
                for sym in _candidate_asset_symbols(pair):
                    sell_available = max(sell_available, _extract_total_balance((balances or {}).get(sym)))
                if sell_available + 1e-9 < volume:
                    return {
                        "action": action,
                        "pair": pair,
                        "error": (
                            f"insufficient {pair} base balance ({sell_available:.8f}) "
                            f"for volume {volume:.8f}"
                        ),
                    }

            if action == "BUY":
                trade_result = self.trader.kraken.paper_buy(pair=pair, volume=volume_str)
            else:
                trade_result = self.trader.kraken.paper_sell(pair=pair, volume=volume_str)

            return {
                "action": action, "pair": pair, "volume": volume_str,
                "amount_usd": amount_usd, "price": price, "result": trade_result,
            }
        except Exception as e:
            return {"action": action, "pair": pair, "error": str(e)}

    def _execute_trade(self, trader_response: str, decision: str) -> dict:
        """Legacy wrapper: extract single trade from response and execute."""
        try:
            details = self.trader._extract_decision(trader_response)
        except Exception as e:
            return {"action": decision, "error": f"extraction failed: {e}"}

        action = details.get("action", "HOLD").upper()
        if action == "HOLD":
            return {"action": "HOLD", "skipped": True}

        return self._execute_trade_for_pair(
            details.get("pair", ""),
            action,
            float(details.get("amount_usd", 0)),
        )
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
