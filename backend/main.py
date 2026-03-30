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

    reply = agent.run(
        "What's the current BTC/USD price? "
        "If it looks interesting, buy a small amount with paper trading."
    )
    print("\n--- Agent response ---")
    print(reply)


def demo_multi_agent():
    cfg = AgentConfig()
    orchestrator = Orchestrator(cfg)
    results = orchestrator.run_analysis_then_trade(
        "Analyse BTC/USD and ETH/USD — any short-term opportunities?"
    )
    for role, output in results.items():
        print(f"\n=== {role.upper()} ===")
        print(output)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "single"
    {"single": demo_single_agent, "multi": demo_multi_agent}[mode]()
