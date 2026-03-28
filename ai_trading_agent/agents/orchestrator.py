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
        """Pipeline: analyst -> trader -> risk check."""
        analysis = self.analyst.run(market_question)
        trade_action = self.trader.run(
            f"Based on this analysis, decide whether to trade:\n\n{analysis}"
        )
        risk_check = self.risk_mgr.run("Check current portfolio risk and report.")
        return {
            "analysis": analysis,
            "trade_action": trade_action,
            "risk_check": risk_check,
        }
