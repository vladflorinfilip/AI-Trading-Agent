from __future__ import annotations

import re
from dataclasses import dataclass

_PAIR_ALIASES = {
    "BTC": "XBT",
}
_PAIR_PATTERN = re.compile(r"[^A-Za-z0-9]")


def normalise_pair(raw: str) -> str:
    """Normalise a trading pair to Kraken's canonical format (e.g. XBTUSD)."""
    stripped = _PAIR_PATTERN.sub("", raw).upper()
    for alias, canonical in _PAIR_ALIASES.items():
        stripped = stripped.replace(alias, canonical)
    return stripped


@dataclass
class TradeIntent:
    agent_id: int
    agent_wallet: str
    pair: str
    action: str
    amount_usd_scaled: int
    max_slippage_bps: int
    nonce: int
    deadline: int

    @property
    def amount_usd(self) -> float:
        return self.amount_usd_scaled / 100.0
