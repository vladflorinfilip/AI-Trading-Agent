from __future__ import annotations

from ..config import AgentConfig
from ..tools import MARKET_TOOLS, PAPER_TRADE_TOOLS
from .base import TradingAgent


class RiskManager(TradingAgent):
    """Monitoring agent: checks positions and balances, flags risk."""

    def __init__(self, cfg: AgentConfig):
        read_only_trade_tools = [
            t for t in PAPER_TRADE_TOOLS
            if t.name in ("paper_balance", "paper_positions")
        ]
        super().__init__(
            cfg,
            tools=MARKET_TOOLS + read_only_trade_tools,
            prompt_name="risk_manager",
        )
