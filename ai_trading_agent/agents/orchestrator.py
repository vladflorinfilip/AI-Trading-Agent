from __future__ import annotations

from ..config import AgentConfig
from .market_analyst import MarketAnalyst
from .trader import Trader
from .risk_manager import RiskManager


class Orchestrator:
    """Coordinates multiple agents. Placeholder for multi-agent flows."""

    def __init__(self, cfg: AgentConfig):
        self.cfg = cfg
        self.analyst = MarketAnalyst(cfg)
        self.trader = Trader(cfg)
        self.risk_mgr = RiskManager(cfg)

    def run_analysis_then_trade(self, market_question: str) -> dict[str, str]:
        """Pipeline: analyst produces OHLC signals → trader acts on them → risk check."""
        analysis = self.analyst.run(market_question)
        trade_action = self.trader.run(
            "The market analyst has produced the following OHLC-based signal report:\n\n"
            f"{analysis}\n\n"
            "Follow your decision process: check your paper balance, then use the analyst's "
            "signals (MA trend, support/resistance, orderbook imbalance) to decide whether "
            "to BUY, SELL, or HOLD for each pair. If you trade, justify the volume calculation. "
            "End with a one-paragraph summary of your actions."
        )
        risk_check = self.risk_mgr.run(
            "Review current paper portfolio. Check balances and open positions. "
            "Report unrealised PnL, any single-asset concentration above 30%, "
            "and any drawdown concerns."
        )
        return {
            "analysis": analysis,
            "trade_action": trade_action,
            "risk_check": risk_check,
        }
