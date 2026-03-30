from __future__ import annotations

from ..config import AgentConfig
from ..tools import MARKET_TOOLS
from .base import TradingAgent


class MarketAnalyst(TradingAgent):
    """Read-only agent: analyses market data, produces signals, never trades."""

    def __init__(self, cfg: AgentConfig):
        super().__init__(cfg, tools=MARKET_TOOLS, prompt_name="market_analyst")
