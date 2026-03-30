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
    cli_binary: str = field(default_factory=lambda: _get("kraken", "cli_binary", default="kraken"))
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
class AgentConfig:
    kraken: KrakenConfig = field(default_factory=KrakenConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    max_agent_iterations: int = field(default_factory=lambda: int(_get("agent", "max_iterations", default=20)))
    log_level: str = field(default_factory=lambda: _get("agent", "log_level", default="INFO"))
