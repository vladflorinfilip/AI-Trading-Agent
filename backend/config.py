from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv(override=True)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_config_yaml() -> dict[str, Any]:
    path = PROJECT_ROOT / "config.yaml"
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


_yaml = _load_config_yaml()


def _get(section: str, key: str, env_var: str | None = None, default: Any = None) -> Any:
    """Resolve a value: env var > config.yaml > default."""
    if env_var:
        env_val = os.environ.get(env_var)
        if env_val is not None:
            return env_val
    return _yaml.get(section, {}).get(key, default)


@dataclass
class KrakenConfig:
    cli_binary: str = field(default_factory=lambda: _get("kraken", "cli_binary", env_var="KRAKEN_CLI_BINARY", default="kraken"))
    api_key: str = field(default_factory=lambda: _get("kraken", "api_key", env_var="KRAKEN_API_KEY", default=""))
    api_secret: str = field(default_factory=lambda: _get("kraken", "api_secret", env_var="KRAKEN_API_SECRET", default=""))
    paper_mode: bool = field(default_factory=lambda: _get("kraken", "paper_mode", default=True))
    default_currency: str = field(default_factory=lambda: _get("kraken", "default_currency", default="USD"))
    paper_starting_balance: float = field(default_factory=lambda: float(_get("kraken", "paper_starting_balance", default=10_000.0)))


@dataclass
class GeminiConfig:
    model: str = field(default_factory=lambda: _get("gemini", "model", default="gemini-3.1-pro-preview"))
    api_key: str = field(default_factory=lambda: _get("gemini", "api_key", env_var="GOOGLE_CLOUD_API_KEY", default=""))
    use_vertex: bool = field(default_factory=lambda: _get("gemini", "use_vertex", default=True))
    temperature: float = field(default_factory=lambda: float(_get("gemini", "temperature", default=1.0)))
    max_output_tokens: int = field(default_factory=lambda: int(_get("gemini", "max_output_tokens", default=65535)))
    thinking_level: str | None = field(default_factory=lambda: _get("gemini", "thinking_level", default=None))


@dataclass
class AgentIdentityConfig:
    """On-chain identity of this agent — must match the AgentRegistry contract."""
    agent_id: int = field(default_factory=lambda: int(_get("identity", "agent_id", env_var="AGENT_ID", default=0)))
    agent_wallet: str = field(default_factory=lambda: _get("identity", "agent_wallet", env_var="WALLET_ADDRESS", default="0x0000000000000000000000000000000000000000"))
    chain: str = field(default_factory=lambda: _get("identity", "chain", default="sepolia"))
    registry_address: str = field(default_factory=lambda: _get("identity", "registry_address", env_var="AGENT_REGISTRY_ADDRESS", default="0x0000000000000000000000000000000000000000"))
    deadline_buffer_seconds: int = field(default_factory=lambda: int(_get("identity", "deadline_buffer_seconds", default=300)))
    default_max_slippage_bps: int = field(default_factory=lambda: int(_get("identity", "default_max_slippage_bps", default=50)))


@dataclass
class AgentConfig:
    kraken: KrakenConfig = field(default_factory=KrakenConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    identity: AgentIdentityConfig = field(default_factory=AgentIdentityConfig)
    max_agent_iterations: int = field(default_factory=lambda: int(_get("agent", "max_iterations", default=20)))
    log_level: str = field(default_factory=lambda: _get("agent", "log_level", default="INFO"))
    trading_pairs: list[str] = field(default_factory=lambda: _get("trading", "pairs", default=["BTC/USD", "ETH/USD"]))

@dataclass
class RiskRouterConfig:
    """Risk rules and routing config — enforced before any trade is submitted."""

    # On-chain address of the RiskRouter contract.
    risk_router_address: str = field(default_factory=lambda: _get(
        "risk_router", "address", env_var="RISK_ROUTER_ADDRESS",
        default="0x0000000000000000000000000000000000000000",
    ))

    # Maximum single-trade size in USD (unscaled).
    max_position_usd: float = field(default_factory=lambda: float(_get(
        "risk_router", "max_position_usd", default=1_000.0,
    )))

    # Pairs the router is allowed to trade (canonical Kraken format, e.g. XBTUSD).
    allowed_markets: list[str] = field(default_factory=lambda: _get(
        "risk_router", "allowed_markets", default=["XBTUSD", "ETHUSD"],
    ))

    # Maximum leverage multiplier per market (1 = spot only).
    leverage_caps: dict[str, int] = field(default_factory=lambda: _get(
        "risk_router", "leverage_caps", default={"XBTUSD": 1, "ETHUSD": 1},
    ))

    # Absolute ceiling on slippage an intent is allowed to request (bps).
    max_slippage_bps: int = field(default_factory=lambda: int(_get(
        "risk_router", "max_slippage_bps", default=200,
    )))

    # Ordered list of approved execution routes. First passing route is used.
    whitelisted_routes: list[str] = field(default_factory=lambda: _get(
        "risk_router", "whitelisted_routes",
        default=["kraken_spot", "uniswap_v3", "1inch_v5"],
    ))


@dataclass
class SmartContractConfig:
    """On-chain policy parameters (kept for reference / future contract reads)."""
    max_position_size: float = field(default_factory=lambda: float(_get("smart_contract", "max_position_size", default=10_000.0)))
    allowed_markets: list[str] = field(default_factory=lambda: _get("smart_contract", "allowed_markets", default=["BTC/USD", "ETH/USD"]))
    leverage_caps: dict[str, int] = field(default_factory=lambda: _get("smart_contract", "leverage_caps", default={"BTC/USD": 10, "ETH/USD": 10}))


