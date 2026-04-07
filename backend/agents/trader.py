from __future__ import annotations

import json
import logging
import time

from google.genai import types

from ..config import AgentConfig
from ..models import TradeIntent, normalise_pair
from ..tools import MARKET_TOOLS, PAPER_TRADE_TOOLS, LIVE_TRADE_TOOLS
from .base import TradingAgent

log = logging.getLogger(__name__)

# Schema for the fields only the LLM can decide.
# System-level fields (agentId, agentWallet, nonce, deadline) are filled in 
_TRADE_DECISION_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "pair": types.Schema(
            type="STRING",
            description="Trading pair in Kraken format, e.g. XBTUSD or ETHUSD",
        ),
        "action": types.Schema(
            type="STRING",
            enum=["BUY", "SELL", "HOLD"],
            description="Trade direction, or HOLD if no clear edge",
        ),
        "amount_usd": types.Schema(
            type="NUMBER",
            description="Trade size in USD (not scaled). E.g. 500.0 for a $500 trade.",
        ),
        "max_slippage_bps": types.Schema(
            type="INTEGER",
            description=(
                "Maximum acceptable slippage in basis points. "
                "Use 30-50 for liquid pairs (BTC, ETH), up to 100 for less liquid ones."
            ),
        ),
        "rationale": types.Schema(
            type="STRING",
            description="One sentence explaining why this decision was made.",
        ),
    },
    required=["pair", "action", "amount_usd", "max_slippage_bps", "rationale"],
)

_EXTRACTION_CONFIG = None  # built lazily per-instance to use the right model


class Trader(TradingAgent):
    """Execution agent: picks paper or live tools based on config."""

    def __init__(self, cfg: AgentConfig):
        trade_tools = PAPER_TRADE_TOOLS if cfg.kraken.paper_mode else LIVE_TRADE_TOOLS
        super().__init__(
            cfg,
            tools=MARKET_TOOLS + trade_tools,
            prompt_name="trader",
        )
        # Separate config for the schema-constrained extraction call (no tools).
        self._extraction_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_TRADE_DECISION_SCHEMA,
            temperature=0.0,   # deterministic — since we're extracting, not generating
            max_output_tokens=512,
        )

    def _extract_decision(self, analysis_text: str) -> dict:
        """Second-pass Gemini call: extract structured decision from the analysis text.

        This call has NO tools and uses response_schema for constrained JSON output,
        making it far more reliable than asking the main agent loop to format JSON.
        """
        prompt = (
            "The following is a crypto trading analysis report. "
            "Extract the primary trade decision as JSON, following the schema exactly.\n\n"
            f"{analysis_text}"
        )
        if self.llm_provider == "mistral":
            response = self._call_mistral(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You extract a single trade decision object. "
                            "Return valid JSON only, with keys: pair, action, amount_usd, max_slippage_bps, rationale."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                include_tools=False,
            )
            content = response.choices[0].message.content if response.choices else "{}"
            if isinstance(content, list):
                content = "".join(getattr(chunk, "text", "") for chunk in content)
            return json.loads(content or "{}")

        response = self.client.models.generate_content(
            model=self.cfg.gemini.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
            config=self._extraction_config,
        )
        return json.loads(response.text)

    def run_trade_intent(self, user_message: str) -> tuple[str, TradeIntent | None]:
        """Run the full agent loop, then extract a typed TradeIntent.

        Returns:
            (analysis_text, trade_intent)
            trade_intent is None if extraction fails or action is HOLD.
        """
        analysis = self.run(user_message)

        try:
            decision = self._extract_decision(analysis)
        except Exception as e:
            log.error("[Trader] structured extraction failed: %s", e)
            return analysis, None

        action = decision.get("action", "HOLD").upper()
        amount_usd = float(decision.get("amount_usd", 0.0))
        identity = self.cfg.identity

        intent = TradeIntent(
            agent_id=identity.agent_id,
            agent_wallet=identity.agent_wallet,
            pair=normalise_pair(decision.get("pair", "")),
            action=action,
            amount_usd_scaled=int(round(amount_usd * 100)),
            max_slippage_bps=int(decision.get(
                "max_slippage_bps", identity.default_max_slippage_bps
            )),
            nonce=int(time.time() * 1000),        # ms timestamp — monotonically increasing
            deadline=int(time.time()) + identity.deadline_buffer_seconds,
        )

        log.info(
            "[Trader] TradeIntent | %s %s $%.2f | slippage=%dbps | deadline=%d",
            intent.action, intent.pair, intent.amount_usd,
            intent.max_slippage_bps, intent.deadline,
        )
        return analysis, intent
