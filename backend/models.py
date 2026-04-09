from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Literal


# Canonical Kraken pair names used on-chain (no slash, Kraken native format).
_PAIR_ALIASES: dict[str, str] = {
    "BTC/USD":  "XBTUSD",
    "BTCUSD":   "XBTUSD",
    "ETH/USD":  "ETHUSD",
    "XBT/USD":  "XBTUSD",
    "SOL/USD":  "SOLUSD",
    "XRP/USD":  "XRPUSD",
    "BNB/USD":  "BNBUSD",
    "MATIC/USD": "MATICUSD",
    "DOT/USD":  "DOTUSD",
    "ADA/USD":  "ADAUSD",
}


def normalise_pair(pair: str) -> str:
    """Convert any common pair representation to the canonical Kraken form."""
    return _PAIR_ALIASES.get(pair.upper(), pair.upper().replace("/", ""))


@dataclass
class TradeIntent:
    """Python mirror of the on-chain TradeIntent struct."""

    agent_id: int
    agent_wallet: str
    pair: str
    action: Literal["BUY", "SELL", "HOLD"]
    amount_usd_scaled: int   # USD * 100
    max_slippage_bps: int
    nonce: int
    deadline: int            # Unix timestamp

    # takes python dict and serializes it to a json string that can be sent to the on chain contract (compatible with it)

    def to_onchain_dict(self) -> dict:
        """Return a dict whose keys exactly match the Solidity struct fields."""
        return {
            "agentId":          self.agent_id,
            "agentWallet":      self.agent_wallet,
            "pair":             self.pair,
            "action":           self.action,
            "amountUsdScaled":  self.amount_usd_scaled,
            "maxSlippageBps":   self.max_slippage_bps,
            "nonce":            self.nonce,
            "deadline":         self.deadline,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_onchain_dict(), indent=2)

    def is_actionable(self) -> bool:
        """HOLD intents should not be submitted on-chain."""
        return self.action in ("BUY", "SELL")

    @property
    def amount_usd(self) -> float:
        """Human-readable USD amount (unscaled)."""
        return self.amount_usd_scaled / 100.0
