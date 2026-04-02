"""Entry point — quick demonstration of the agent scaffolding."""

from __future__ import annotations

import logging
import sys

from .config import AgentConfig
from .agents import Trader, Orchestrator
from .kraken_client import KrakenCLIError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)


PAIRS = ["BTC/USD", "ETH/USD"]

SINGLE_AGENT_PROMPT = (
    "Follow your decision process for the following pairs: {pairs}. "
    "Start by checking your paper balance, then fetch 1-hour OHLC candles for each pair. "
    "Compute short MA (last 5 closes) and long MA (last 20 closes), identify support and "
    "resistance levels, check the orderbook for bid/ask imbalance, and decide whether to "
    "BUY, SELL, or HOLD. Execute any trades in paper-trading mode and end with a summary."
).format(pairs=", ".join(PAIRS))

ANALYST_PROMPT = (
    "Perform a full OHLC-based technical analysis for the following pairs: {pairs}. "
    "For each pair, fetch 1-hour candles, compute short MA (last 5 closes) and long MA "
    "(last 20 closes), identify support and resistance, check the orderbook imbalance ratio, "
    "and output a structured signal report (STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL)."
).format(pairs=", ".join(PAIRS))


def demo_single_agent():
    cfg = AgentConfig()
    agent = Trader(cfg)

    try:
        agent.kraken.paper_init(
            balance=cfg.kraken.paper_starting_balance,
            currency=cfg.kraken.default_currency,
        )
    except KrakenCLIError:
        pass  # already initialized

    reply = agent.run(SINGLE_AGENT_PROMPT)
    print("\n--- Agent response ---")
    print(reply)


def demo_multi_agent():
    cfg = AgentConfig()
    orchestrator = Orchestrator(cfg)
    results = orchestrator.run_analysis_then_trade(ANALYST_PROMPT)
    for role, output in results.items():
        print(f"\n=== {role.upper()} ===")
        print(output)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    {"single": demo_single_agent, "multi": demo_multi_agent}[mode]()
