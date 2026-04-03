from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ..models import TradeIntent, normalise_pair
from ..config import RiskRouterConfig

log = logging.getLogger(__name__)


@dataclass
class RiskVerdict:
    approved: bool
    reason: str


class RiskRouterClient:
    """Evaluates a TradeIntent against configured risk rules, then routes it."""

    def __init__(self, cfg: RiskRouterConfig):
        self.cfg = cfg
        self.address = cfg.risk_router_address
        log.info(
            "[RiskRouter] ready | contract=%s | max_position=$%.2f | markets=%s | routes=%s",
            self.address,
            self.cfg.max_position_usd,
            self.cfg.allowed_markets,
            self.cfg.whitelisted_routes,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_trade_intent(self, intent: TradeIntent) -> bool:
        """Evaluate risk and, if approved, submit via the first whitelisted route.

        Returns True if the intent was submitted, False if it was rejected.
        """
        verdict = self._evaluate_risk(intent)

        if not verdict.approved:
            log.warning(
                "[RiskRouter] REJECTED | pair=%s action=%s amount=$%.2f | reason: %s",
                intent.pair, intent.action, intent.amount_usd, verdict.reason,
            )
            return False

        log.info(
            "[RiskRouter] APPROVED | pair=%s action=%s amount=$%.2f",
            intent.pair, intent.action, intent.amount_usd,
        )

        if not self.cfg.whitelisted_routes:
            log.error("[RiskRouter] No whitelisted routes configured — cannot submit.")
            return False

        route = self.cfg.whitelisted_routes[0]
        self._submit_via_route(intent, route)
        return True

    # ------------------------------------------------------------------
    # Risk evaluation
    # ------------------------------------------------------------------

    def _evaluate_risk(self, intent: TradeIntent) -> RiskVerdict:
        """Run all risk checks in order. Returns on first failure."""

        # 1. Intent must be actionable (HOLD is never submitted on-chain)
        if not intent.is_actionable():
            return RiskVerdict(False, f"action is '{intent.action}' — only BUY/SELL are submittable")

        # 2. Deadline must be in the future
        now = int(time.time())
        if intent.deadline <= now:
            return RiskVerdict(False, f"intent has expired (deadline={intent.deadline}, now={now})")

        # 3. Market must be on the allowlist
        #    Normalise both sides so "BTC/USD" and "XBTUSD" compare correctly.
        allowed_normalised = {normalise_pair(m) for m in self.cfg.allowed_markets}
        if intent.pair not in allowed_normalised:
            return RiskVerdict(
                False,
                f"pair '{intent.pair}' is not in allowed_markets {self.cfg.allowed_markets}",
            )

        # 4. Position size must be within the per-trade cap
        if intent.amount_usd > self.cfg.max_position_usd:
            return RiskVerdict(
                False,
                f"position size ${intent.amount_usd:.2f} exceeds max_position_usd "
                f"${self.cfg.max_position_usd:.2f}",
            )

        # 5. Requested slippage must not exceed the absolute ceiling
        if intent.max_slippage_bps > self.cfg.max_slippage_bps:
            return RiskVerdict(
                False,
                f"requested slippage {intent.max_slippage_bps} bps exceeds "
                f"max_slippage_bps {self.cfg.max_slippage_bps}",
            )

        # 6. Leverage cap (TradeIntent is spot-only = 1x; checked against per-market cap)
        #    This check future-proofs the router for when margin is introduced.
        implied_leverage = 1  # all current intents are spot (no leverage field yet)
        cap = self.cfg.leverage_caps.get(intent.pair)
        if cap is not None and implied_leverage > cap:
            return RiskVerdict(
                False,
                f"implied leverage {implied_leverage}x exceeds cap of {cap}x for {intent.pair}",
            )

        return RiskVerdict(True, "all checks passed")

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------

    def _submit_via_route(self, intent: TradeIntent, route: str) -> None:
        """Submit the approved intent through the named whitelisted route.

        Each branch here is a placeholder for the real integration call.
        The structure is in place so you can swap in web3.py / REST calls
        without changing the public interface.
        """
        log.info(
            "[RiskRouter] submitting via route='%s' | %s",
            route, intent.to_json(),
        )

        if route == "kraken_spot":
            # TODO: call KrakenClient.buy() / .sell() with live credentials
            log.info("[RiskRouter] [kraken_spot] would call kraken live trade API")

        elif route == "uniswap_v3":
            # TODO: encode as Uniswap V3 exactInputSingle calldata via web3.py
            log.info("[RiskRouter] [uniswap_v3] would encode swap calldata and broadcast tx")

        elif route == "1inch_v5":
            # TODO: call 1inch /swap API then broadcast signed tx
            log.info("[RiskRouter] [1inch_v5] would call 1inch aggregation API")

        else:
            log.warning("[RiskRouter] unknown route '%s' — skipping submission", route)
