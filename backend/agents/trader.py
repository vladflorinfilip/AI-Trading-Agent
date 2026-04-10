from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from google.genai import types

from ..config import AgentConfig
from ..models import TradeIntent, normalise_pair
from ..tools import MARKET_TOOLS
from .base import TradingAgent

log = logging.getLogger(__name__)

_SINGLE_DECISION_SCHEMA = types.Schema(
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
            description="Trade size in USD (0 for HOLD). E.g. 500.0 for a $500 trade.",
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
        "confidence": types.Schema(
            type="NUMBER",
            description="Confidence in this pair decision from 0.0 to 1.0",
        ),
    },
    required=["pair", "action", "amount_usd", "max_slippage_bps", "rationale", "confidence"],
)

_TRADE_DECISIONS_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "decisions": types.Schema(
            type="ARRAY",
            items=_SINGLE_DECISION_SCHEMA,
            description="One decision per trading pair. Every pair must be included.",
        ),
    },
    required=["decisions"],
)

# JSON Schema for Mistral structured output (OpenAPI-style subset).
TRADER_DECISIONS_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "pair": {"type": "string"},
                    "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
                    "amount_usd": {"type": "number"},
                    "max_slippage_bps": {"type": "integer"},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["pair", "action", "amount_usd", "max_slippage_bps", "rationale", "confidence"],
            },
        }
    },
    "required": ["decisions"],
}

_STRUCTURED_APPENDIX = """

## Final output (mandatory)

After you finish any market data tool calls, you will be asked for a single JSON object
only. That object must have a top-level key "decisions" whose value is an array with
exactly one object per configured trading pair. Each element must include:
pair (Kraken style, e.g. XBTUSD), action (BUY, SELL, or HOLD), amount_usd (0 for HOLD),
max_slippage_bps (integer), rationale (short string), confidence (0..1).
"""


class Trader(TradingAgent):
    """Proposes per-pair trades; final answer is schema-constrained JSON (Gemini or Mistral)."""

    def __init__(self, cfg: AgentConfig):
        super().__init__(
            cfg,
            tools=MARKET_TOOLS,
            prompt_name="trader",
        )
        self._structured_gemini_config = types.GenerateContentConfig(
            system_instruction=self._system_prompt + _STRUCTURED_APPENDIX,
            temperature=0.0,
            max_output_tokens=min(4096, self.cfg.gemini.max_output_tokens),
            response_mime_type="application/json",
            response_schema=_TRADE_DECISIONS_SCHEMA,
        )
        self._extraction_config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_TRADE_DECISIONS_SCHEMA,
            temperature=0.0,
            max_output_tokens=2048,
        )

    def _json_followup_user_text(self) -> str:
        canon = ", ".join(normalise_pair(p) for p in self.cfg.trading_pairs)
        return (
            "Now respond with ONLY a JSON object (no markdown fences, no prose). "
            f'Root shape: {{"decisions": [...]}}. Include exactly one object per pair, '
            f"using these canonical pair strings: {canon}. "
            "Each object: pair, action (BUY|SELL|HOLD), amount_usd (number, 0 if HOLD), "
            "max_slippage_bps (integer), rationale (string), confidence (number 0..1)."
        )

    @staticmethod
    def _parse_model_json(text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```\s*$", "", text)
        return json.loads(text)

    def _normalize_decision_row(self, row: dict, canonical_pair: str) -> dict[str, Any]:
        action = str(row.get("action", "HOLD")).upper()
        if action not in ("BUY", "SELL", "HOLD"):
            action = "HOLD"
        try:
            amount = float(row.get("amount_usd", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if action == "HOLD":
            amount = 0.0
        try:
            bps = int(row.get("max_slippage_bps", self.cfg.identity.default_max_slippage_bps))
        except (TypeError, ValueError):
            bps = self.cfg.identity.default_max_slippage_bps
        try:
            confidence = float(row.get("confidence", 0.0 if action == "HOLD" else 0.5))
        except (TypeError, ValueError):
            confidence = 0.0 if action == "HOLD" else 0.5
        confidence = max(0.0, min(confidence, 1.0))
        return {
            "pair": canonical_pair,
            "action": action,
            "amount_usd": amount,
            "max_slippage_bps": bps,
            "rationale": str(row.get("rationale", "")).strip() or "(no rationale)",
            "confidence": confidence,
        }

    def _merge_required_pairs(self, decisions: list[dict]) -> list[dict[str, Any]]:
        required = [normalise_pair(p) for p in self.cfg.trading_pairs]
        by_pair: dict[str, dict] = {}
        for d in decisions:
            k = normalise_pair(d.get("pair", ""))
            if k:
                by_pair[k] = d
        out: list[dict[str, Any]] = []
        for canon in required:
            if canon in by_pair:
                out.append(self._normalize_decision_row(by_pair[canon], canon))
            else:
                out.append(
                    {
                        "pair": canon,
                        "action": "HOLD",
                        "amount_usd": 0.0,
                        "max_slippage_bps": self.cfg.identity.default_max_slippage_bps,
                        "rationale": "Pair missing from model output; defaulted to HOLD",
                        "confidence": 0.0,
                    }
                )
        return out

    def _structured_followup_gemini(self, contents: list[types.Content]) -> str:
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=self._json_followup_user_text())],
            )
        )
        response = self._call_gemini_with_config(contents, self._structured_gemini_config)
        if not response.candidates:
            raise ValueError("empty structured response from Gemini")
        parts = response.candidates[0].content.parts
        return "".join(p.text for p in parts if p.text)

    def _run_trader_phased_gemini(self, user_message: str) -> dict[str, Any]:
        t_start = time.perf_counter()
        traced_tools: list[dict[str, Any]] = []
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)]),
        ]
        closed_with_text = False

        for i in range(1, self.cfg.max_agent_iterations + 1):
            response = self._call_gemini(contents)
            if not response.candidates:
                raise ValueError("empty response from Gemini")
            parts = response.candidates[0].content.parts
            tool_calls = [p for p in parts if p.function_call]

            if not tool_calls:
                contents.append(response.candidates[0].content)
                closed_with_text = True
                break

            log.info(
                "[%s] step %d | tools: %s",
                self.name,
                i,
                ", ".join(p.function_call.name for p in tool_calls),
            )
            contents.append(response.candidates[0].content)
            tool_responses: list[types.Part] = []
            for part in tool_calls:
                fc = part.function_call
                t_tool = time.perf_counter()
                args = dict(fc.args)
                result = self.dispatch_tool(fc.name, args)
                traced_tools.append(
                    {
                        "step": i,
                        "name": fc.name,
                        "args": args,
                        "result": result,
                        "duration_ms": round((time.perf_counter() - t_tool) * 1000),
                    }
                )
                tool_responses.append(
                    types.Part.from_function_response(
                        name=fc.name,
                        response={"result": result},
                    )
                )
            contents.append(types.Content(role="user", parts=tool_responses))

        if not closed_with_text:
            log.warning("[%s] max iterations before structured follow-up", self.name)

        json_text = self._structured_followup_gemini(contents)
        parsed = self._parse_model_json(json_text)
        merged = self._merge_required_pairs(parsed.get("decisions", []))
        ms = (time.perf_counter() - t_start) * 1000
        log.info("[%s] phased gemini done | %.0fms | pairs=%d", self.name, ms, len(merged))
        out = self._trace_result(json_text, traced_tools, t_start)
        out["parsed_decisions"] = merged
        return out

    def _structured_followup_mistral(self, messages: list[dict[str, Any]]) -> str:
        messages = list(messages)
        messages.append({"role": "user", "content": self._json_followup_user_text()})
        sys_msg = self._system_prompt + _STRUCTURED_APPENDIX
        fmt_schema: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "trader_decisions",
                "schema": TRADER_DECISIONS_JSON_SCHEMA,
                "strict": False,
            },
        }
        try:
            response = self._call_mistral(
                messages=[{"role": "system", "content": sys_msg}, *messages],
                response_format=fmt_schema,
                include_tools=False,
            )
        except Exception as e:
            log.warning("[Trader] Mistral json_schema failed (%s), using json_object", e)
            response = self._call_mistral(
                messages=[
                    {"role": "system", "content": sys_msg},
                    *messages,
                ],
                response_format={"type": "json_object"},
                include_tools=False,
            )
        if not response.choices:
            raise ValueError("empty response from Mistral")
        msg = response.choices[0].message
        content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content or "")
        if isinstance(content, list):
            content = "".join(getattr(chunk, "text", "") for chunk in content)
        return content

    def _run_trader_phased_mistral(self, user_message: str) -> dict[str, Any]:
        t_start = time.perf_counter()
        traced_tools: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message},
        ]
        closed_with_text = False

        for i in range(1, self.cfg.max_agent_iterations + 1):
            response = self._call_mistral(
                messages=[{"role": "system", "content": self._system_prompt}, *messages],
                include_tools=True,
            )
            if not response.choices:
                raise ValueError("empty response from Mistral")
            msg = response.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                messages.append(
                    {"role": "assistant", "content": msg.content or ""},
                )
                closed_with_text = True
                break

            log.info(
                "[%s] step %d | tools: %s",
                self.name,
                i,
                ", ".join(tc.function.name for tc in tool_calls),
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [tc.model_dump(exclude_none=True) for tc in tool_calls],
                }
            )
            for tc in tool_calls:
                t_tool = time.perf_counter()
                raw_args = tc.function.arguments
                if isinstance(raw_args, str):
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}
                else:
                    args = dict(raw_args or {})
                result = self.dispatch_tool(tc.function.name, args)
                traced_tools.append(
                    {
                        "step": i,
                        "name": tc.function.name,
                        "args": args,
                        "result": result,
                        "duration_ms": round((time.perf_counter() - t_tool) * 1000),
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.function.name,
                        "content": json.dumps({"result": result}),
                    }
                )

        if not closed_with_text:
            log.warning("[%s] max iterations before structured follow-up (mistral)", self.name)

        json_text = self._structured_followup_mistral(messages)
        parsed = self._parse_model_json(json_text)
        merged = self._merge_required_pairs(parsed.get("decisions", []))
        ms = (time.perf_counter() - t_start) * 1000
        log.info("[%s] phased mistral done | %.0fms | pairs=%d", self.name, ms, len(merged))
        out = self._trace_result(json_text, traced_tools, t_start)
        out["parsed_decisions"] = merged
        return out

    def run_traced(self, user_message: str) -> dict[str, Any]:
        """Tool phase (optional market calls) then schema-constrained JSON decisions."""
        if self._gemini_available:
            try:
                result = self._run_trader_phased_gemini(user_message)
                result["provider"] = "gemini"
                return result
            except Exception as e:
                log.warning(
                    "[Trader] Gemini phased failed (%s), falling back to Mistral phased",
                    e,
                )
                result = self._run_trader_phased_mistral(user_message)
                result["provider"] = "mistral"
                result["fallback"] = True
                return result
        result = self._run_trader_phased_mistral(user_message)
        result["provider"] = "mistral"
        return result

    def _extract_decisions(self, trader_response: str) -> list[dict]:
        """Fallback: parse JSON from text, or re-extract via a separate LLM call."""
        text = (trader_response or "").strip()
        if text.startswith("{") or text.startswith("```"):
            try:
                parsed = self._parse_model_json(text)
                return self._merge_required_pairs(parsed.get("decisions", []))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

        prompt = (
            "The following is a crypto trading report. Extract ALL per-pair trade "
            "decisions as JSON with a 'decisions' array, following the schema exactly.\n\n"
            f"{trader_response}"
        )
        if self._gemini_available:
            try:
                response = self.gemini_client.models.generate_content(
                    model=self.cfg.gemini.model,
                    contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
                    config=self._extraction_config,
                )
                parsed = json.loads(response.text)
                raw = parsed.get("decisions", [parsed] if "pair" in parsed else [])
                return self._merge_required_pairs(raw)
            except Exception as e:
                log.warning("[Trader] Gemini extraction failed (%s), falling back to Mistral", e)

        response = self._call_mistral(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You extract trade decisions. Return JSON with a 'decisions' array. "
                        "Each element: pair, action, amount_usd, max_slippage_bps, rationale."
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
        parsed = json.loads(content or "{}")
        raw = parsed.get("decisions", [parsed] if "pair" in parsed else [])
        return self._merge_required_pairs(raw)

    def _extract_decision(self, analysis_text: str) -> dict:
        decisions = self._extract_decisions(analysis_text)
        actionable = [d for d in decisions if d.get("action", "HOLD").upper() != "HOLD"]
        if actionable:
            return actionable[0]
        return decisions[0] if decisions else {"pair": "", "action": "HOLD", "amount_usd": 0}

    def run_trade_intents(self, user_message: str) -> tuple[str, list[TradeIntent]]:
        traced = self.run_traced(user_message)
        analysis = traced["response"]
        decisions = traced.get("parsed_decisions")
        if not decisions:
            try:
                decisions = self._extract_decisions(analysis)
            except Exception as e:
                log.error("[Trader] decision parse failed: %s", e)
                return analysis, []

        identity = self.cfg.identity
        intents: list[TradeIntent] = []

        for decision in decisions:
            action = decision.get("action", "HOLD").upper()
            if action == "HOLD":
                continue
            amount_usd = float(decision.get("amount_usd", 0.0))
            intent = TradeIntent(
                agent_id=identity.agent_id,
                agent_wallet=identity.agent_wallet,
                pair=normalise_pair(decision.get("pair", "")),
                action=action,
                amount_usd_scaled=int(round(amount_usd * 100)),
                max_slippage_bps=int(
                    decision.get("max_slippage_bps", identity.default_max_slippage_bps)
                ),
                nonce=int(time.time() * 1000) + len(intents),
                deadline=int(time.time()) + identity.deadline_buffer_seconds,
            )
            intents.append(intent)
            log.info(
                "[Trader] TradeIntent | %s %s $%.2f | slippage=%dbps",
                intent.action,
                intent.pair,
                intent.amount_usd,
                intent.max_slippage_bps,
            )

        return analysis, intents

    def run_trade_intent(self, user_message: str) -> tuple[str, TradeIntent | None]:
        analysis, intents = self.run_trade_intents(user_message)
        return analysis, intents[0] if intents else None
