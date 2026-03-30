from __future__ import annotations

from ..config import AgentConfig
from ..tools import MARKET_TOOLS, PAPER_TRADE_TOOLS
from .base import TradingAgent


class Trader(TradingAgent):
    """Execution agent: can read market data AND place paper trades."""

    def __init__(self, cfg: AgentConfig):
        super().__init__(
            cfg,
            tools=MARKET_TOOLS + PAPER_TRADE_TOOLS,
            prompt_name="trader",
        )
