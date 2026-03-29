from __future__ import annotations

from ..config import AgentConfig
from ..tools import MARKET_TOOLS, PAPER_TRADE_TOOLS, LIVE_TRADE_TOOLS
from .base import TradingAgent


class Trader(TradingAgent):
    """Execution agent: picks paper or live tools based on config."""

    def __init__(self, cfg: AgentConfig):
        trade_tools = PAPER_TRADE_TOOLS if cfg.kraken.paper_mode else LIVE_TRADE_TOOLS
        super().__init__(
            cfg,
            tools=MARKET_TOOLS + trade_tools,
            prompt_name="trader",
        )
