"""Thin wrapper around kraken CLI subprocess calls.

Every method returns parsed JSON (dict/list). Errors raise ``KrakenCLIError``.
The class is intentionally stateless — all state lives in your Kraken account
or the paper-trading sandbox managed by the CLI itself.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from typing import Any

from .config import KrakenConfig

log = logging.getLogger(__name__)


class KrakenCLIError(Exception):
    def __init__(self, message: str, raw: str | None = None):
        super().__init__(message)
        self.raw = raw


class KrakenClient:
    def __init__(self, cfg: KrakenConfig | None = None):
        self.cfg = cfg or KrakenConfig()

    def _run(self, *args: str, timeout: int = 30) -> Any:
        """Execute ``kraken <args> -o json`` and return parsed output."""
        cmd = [self.cfg.cli_binary, *args, "-o", "json"]
        env = None
        if self.cfg.api_key:
            import os
            env = {**os.environ, "KRAKEN_API_KEY": self.cfg.api_key,
                   "KRAKEN_API_SECRET": self.cfg.api_secret}

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
        )

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            data = None

        if result.returncode != 0:
            msg = (data or {}).get("message") or result.stderr.strip() or result.stdout.strip()
            raise KrakenCLIError(f"kraken exited {result.returncode}: {msg}", raw=result.stdout)

        return data if data is not None else {"raw": result.stdout.strip()}

    # -- Market data (no auth) ------------------------------------------------

    def ticker(self, pair: str) -> dict:
        return self._run("ticker", pair)

    def ohlc(self, pair: str, interval: int = 60) -> dict:
        return self._run("ohlc", pair, "--interval", str(interval))

    def orderbook(self, pair: str, count: int = 10) -> dict:
        return self._run("orderbook", pair, "--count", str(count))

    def status(self) -> dict:
        return self._run("status")

    # -- Paper trading (no auth) -----------------------------------------------

    def paper_init(self, balance: float | None = None, currency: str | None = None) -> dict:
        args = ["paper", "init"]
        if balance is not None:
            args += ["--balance", str(balance)]
        if currency is not None:
            args += ["--currency", currency]
        return self._run(*args)

    def paper_balance(self) -> dict:
        return self._run("paper", "balance")

    def paper_buy(self, pair: str, volume: str, **kwargs: str) -> dict:
        return self._build_order("paper", "buy", pair=pair, volume=volume, **kwargs)

    def paper_sell(self, pair: str, volume: str, **kwargs: str) -> dict:
        return self._build_order("paper", "sell", pair=pair, volume=volume, **kwargs)

    def paper_positions(self) -> dict:
        return self._run("paper", "orders")

    def paper_status(self) -> dict:
        return self._run("paper", "status")

    def paper_history(self) -> dict:
        return self._run("paper", "history")

    # -- Live trading (auth required) ------------------------------------------

    def balance(self) -> dict:
        return self._run("balance")

    def buy(self, pair: str, volume: str, **kwargs: str) -> dict:
        return self._build_order("trade", "buy", pair=pair, volume=volume, **kwargs)

    def sell(self, pair: str, volume: str, **kwargs: str) -> dict:
        return self._build_order("trade", "sell", pair=pair, volume=volume, **kwargs)

    def open_orders(self) -> dict:
        return self._run("open-orders")

    def cancel(self, txid: str) -> dict:
        return self._run("cancel", txid)

    # -- Helpers ---------------------------------------------------------------

    def _build_order(self, *prefix: str, pair: str, volume: str, **kwargs: str) -> dict:
        args = [*prefix, pair, volume]
        for flag, val in kwargs.items():
            args += [f"--{flag.replace('_', '-')}", val]
        return self._run(*args)
