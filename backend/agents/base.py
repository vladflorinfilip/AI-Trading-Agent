from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC
from pathlib import Path
from typing import Any

import yaml
from google import genai
from google.genai import types
from google.genai.errors import ClientError
from mistralai.client import Mistral

from ..config import AgentConfig
from ..kraken_client import KrakenClient

MAX_RETRIES = 5

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> dict[str, Any]:
    path = PROMPTS_DIR / f"{name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _parse_retry_delay(error_msg: str) -> float:
    """Extract retry delay from a 429 error message, default 15s."""
    match = re.search(r"retry in (\d+\.?\d*)", error_msg, re.IGNORECASE)
    return float(match.group(1)) if match else 15.0


class TradingAgent(ABC):
    """Base class: LLM model with function-calling wired to Kraken CLI.

    Uses a Gemini-first strategy: every call tries Gemini (with key rotation
    and 429 retries).  If Gemini fails entirely, falls back to Mistral.
    """

    def __init__(
        self,
        cfg: AgentConfig,
        tools: list[types.FunctionDeclaration],
        prompt_name: str,
    ):
        self.cfg = cfg
        self.kraken = KrakenClient(cfg.kraken)
        self.prompt_data = load_prompt(prompt_name)
        self.name = self.prompt_data.get("role", self.__class__.__name__)
        self.tools = tools
        self._system_prompt = self._build_system_prompt()
        self._api_keys: list[str] = [k for k in [cfg.gemini.api_key, cfg.gemini.fallback_api_key] if k]
        self._active_key_idx = 0
        self._gemini_available = bool(self._api_keys)

        if self._gemini_available:
            self.gemini_client = genai.Client(
                vertexai=cfg.gemini.use_vertex,
                api_key=self._active_api_key or None,
            )
            self._gen_config = self._build_gen_config(self._system_prompt)
            key_preview = (self._active_api_key or "")[:8] + "..."
            log.info(
                "[%s] gemini ready | model=%s | %d tools | key=%s | %d key(s)",
                self.name,
                cfg.gemini.model,
                len(self.tools),
                key_preview,
                len(self._api_keys),
            )
        else:
            self.gemini_client = None
            self._gen_config = None
            log.warning("[%s] gemini skipped — no API key configured", self.name)

        # --- Mistral setup (always available as fallback) ---
        self.mistral_client = Mistral(api_key=cfg.mistral.api_key)
        self._mistral_tools = self._to_mistral_tools(self.tools)
        log.info(
            "[%s] mistral ready (fallback) | model=%s | %d tools",
            self.name,
            cfg.mistral.model,
            len(self.tools),
        )

        # Keep legacy .client pointing at the primary provider for _extract_decision etc.
        self.client = self.gemini_client if self._gemini_available else self.mistral_client

    @property
    def _active_api_key(self) -> str:
        if not self._api_keys:
            return ""
        return self._api_keys[self._active_key_idx]

    def _swap_to_next_key(self) -> bool:
        """Switch to the next available API key. Returns True if a swap occurred."""
        if len(self._api_keys) <= 1:
            return False
        prev_idx = self._active_key_idx
        self._active_key_idx = (self._active_key_idx + 1) % len(self._api_keys)
        if self._active_key_idx == prev_idx:
            return False
        self.gemini_client = genai.Client(
            vertexai=self.cfg.gemini.use_vertex,
            api_key=self._active_api_key or None,
        )
        self.client = self.gemini_client
        key_preview = (self._active_api_key or "")[:8] + "..."
        log.info("[%s] swapped to fallback API key %s", self.name, key_preview)
        return True

    def _build_system_prompt(self) -> str:
        template_vars = {
            "pairs": ", ".join(self.cfg.trading_pairs),
            "mode": "paper trading (simulated)" if self.cfg.kraken.paper_mode else "LIVE trading (real money)",
            "buy_fn": "paper_buy" if self.cfg.kraken.paper_mode else "buy",
            "sell_fn": "paper_sell" if self.cfg.kraken.paper_mode else "sell",
            "balance_fn": "paper_balance" if self.cfg.kraken.paper_mode else "balance",
        }

        system_prompt = self.prompt_data["system_prompt"]
        try:
            system_prompt = system_prompt.format(**template_vars)
        except KeyError:
            pass

        constraints = self.prompt_data.get("constraints", [])
        if constraints:
            system_prompt += "\n\nConstraints:\n" + "\n".join(
                f"- {c}" for c in constraints
            )
        return system_prompt

    def _build_gen_config(self, system_prompt: str) -> types.GenerateContentConfig:
        thinking = None
        if self.cfg.gemini.thinking_level:
            thinking = types.ThinkingConfig(thinking_level=self.cfg.gemini.thinking_level)

        return types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=self.cfg.gemini.temperature,
            max_output_tokens=self.cfg.gemini.max_output_tokens,
            tools=[types.Tool(function_declarations=self.tools)],
            thinking_config=thinking,
        )

    def _to_mistral_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in schema.items():
            if value is None:
                continue
            if key == "type" and isinstance(value, str):
                normalized[key] = value.lower()
                continue
            if isinstance(value, dict):
                normalized[key] = self._to_mistral_schema(value)
            elif isinstance(value, list):
                normalized[key] = [
                    self._to_mistral_schema(v) if isinstance(v, dict) else v
                    for v in value
                ]
            else:
                normalized[key] = value
        return normalized

    def _to_mistral_tools(self, tools: list[types.FunctionDeclaration]) -> list[dict[str, Any]]:
        mistral_tools: list[dict[str, Any]] = []
        for tool in tools:
            schema_dict = tool.parameters.model_dump(by_alias=True, exclude_none=True)
            mistral_tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description or "",
                        "parameters": self._to_mistral_schema(schema_dict),
                    },
                }
            )
        return mistral_tools

    def dispatch_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Route a Gemini function call to the matching KrakenClient method or local analysis."""
        if name == "technical_signals":
            return self._compute_technical_signals(args)
        method = getattr(self.kraken, name, None)
        if method is None:
            log.warning("[%s] unknown tool: %s", self.name, name)
            return {"error": f"Unknown tool: {name}"}
        try:
            return method(**args)
        except Exception as e:
            log.error("[%s] %s failed: %s", self.name, name, e)
            return {"error": str(e)}

    def _compute_technical_signals(self, args: dict[str, Any]) -> Any:
        """Fetch OHLC + ticker + orderbook, compute indicators locally, return formatted signals."""
        from ..analysis.indicators import compute_signals, format_signals_for_llm
        pair = args.get("pair", "BTC/USD")
        interval = args.get("interval", 60)
        try:
            candles_raw = self.kraken.ohlc(pair, interval)
            if isinstance(candles_raw, list):
                candles = candles_raw
            elif isinstance(candles_raw, dict):
                # Handle multiple Kraken CLI response shapes:
                # - {"candles":[...]}
                # - {"result":{"XBT/USD":[...], "last":...}}
                # - {"XBT/USD":[...], "last":...}
                candles = candles_raw.get("candles")
                if candles is None:
                    result_block = candles_raw.get("result")
                    if isinstance(result_block, dict):
                        candles = result_block.get(pair)
                        if candles is None:
                            candles = next((v for v in result_block.values() if isinstance(v, list)), [])
                if candles is None:
                    candles = candles_raw.get(pair)
                if candles is None:
                    candles = next((v for v in candles_raw.values() if isinstance(v, list)), [])
            else:
                candles = []
            ticker = self.kraken.ticker(pair)
            try:
                orderbook = self.kraken.orderbook(pair, count=10)
            except Exception:
                orderbook = None
            signals = compute_signals(pair, candles, ticker, orderbook)
            return {"formatted": format_signals_for_llm(signals), "atr_14": signals.atr_14, "rsi_14": signals.rsi_14, "trend": signals.trend}
        except Exception as e:
            log.error("[%s] technical_signals failed: %s", self.name, e)
            return {"error": str(e)}

    def _call_gemini(self, contents: list[types.Content]):
        """Call Gemini with automatic key failover and retry on rate-limit (429)."""
        for attempt in range(MAX_RETRIES):
            try:
                return self.gemini_client.models.generate_content(
                    model=self.cfg.gemini.model,
                    contents=contents,
                    config=self._gen_config,
                )
            except ClientError as e:
                is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                if not is_rate_limit or attempt == MAX_RETRIES - 1:
                    raise
                if self._swap_to_next_key():
                    log.info("[%s] rate limited on key, retrying immediately with fallback key", self.name)
                    continue
                wait = _parse_retry_delay(str(e))
                log.info("[%s] rate limited (all keys exhausted), waiting %.0fs...", self.name, wait)
                time.sleep(wait)

    def _call_mistral(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        include_tools: bool = True,
    ):
        """Call Mistral chat.complete with retries on transient failures."""
        for attempt in range(MAX_RETRIES):
            try:
                kwargs: dict[str, Any] = {
                    "model": self.cfg.mistral.model,
                    "messages": messages,
                    "temperature": self.cfg.mistral.temperature,
                    "max_tokens": self.cfg.mistral.max_output_tokens,
                }
                if include_tools:
                    kwargs["tools"] = self._mistral_tools
                    kwargs["tool_choice"] = "auto"
                if response_format:
                    kwargs["response_format"] = response_format
                return self.mistral_client.chat.complete(**kwargs)
            except Exception as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                wait = min(2 ** attempt, 10)
                log.info("[%s] mistral call failed (%s), retrying in %ss", self.name, e, wait)
                time.sleep(wait)

    def run(self, user_message: str) -> str:
        """Single turn: user message -> final text response."""
        result = self.run_traced(user_message)
        return result["response"]

    def run_traced(self, user_message: str) -> dict[str, Any]:
        """Try Gemini first; on any failure fall back to Mistral."""
        if self._gemini_available:
            try:
                return self._run_traced_gemini(user_message)
            except Exception as e:
                log.warning(
                    "[%s] Gemini failed (%s), falling back to Mistral",
                    self.name, e,
                )
        return self._run_traced_mistral(user_message)

    def _run_traced_gemini(self, user_message: str) -> dict[str, Any]:
        """Gemini execution with tool-calling loop."""
        log.info("[%s] run | %.100s", self.name, user_message)
        t_start = time.perf_counter()
        traced_tools: list[dict[str, Any]] = []

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)]),
        ]

        for i in range(1, self.cfg.max_agent_iterations + 1):
            response = self._call_gemini(contents)

            if not response.candidates:
                log.warning("[%s] empty response from model", self.name)
                return self._trace_result("[no response from model]", traced_tools, t_start)

            parts = response.candidates[0].content.parts
            tool_calls = [p for p in parts if p.function_call]

            if not tool_calls:
                text = "".join(p.text for p in parts if p.text)
                ms = (time.perf_counter() - t_start) * 1000
                log.info("[%s] done | %d steps | %.0fms", self.name, i, ms)
                return self._trace_result(text, traced_tools, t_start)

            log.info("[%s] step %d | tools: %s",
                     self.name, i, ", ".join(p.function_call.name for p in tool_calls))

            contents.append(response.candidates[0].content)
            tool_responses: list[types.Part] = []
            for part in tool_calls:
                fc = part.function_call
                t_tool = time.perf_counter()
                args = dict(fc.args)
                result = self.dispatch_tool(fc.name, args)
                traced_tools.append({
                    "step": i,
                    "name": fc.name,
                    "args": args,
                    "result": result,
                    "duration_ms": round((time.perf_counter() - t_tool) * 1000),
                })
                tool_responses.append(
                    types.Part.from_function_response(
                        name=fc.name, response={"result": result},
                    )
                )
            contents.append(types.Content(role="user", parts=tool_responses))

        log.warning("[%s] max iterations reached", self.name)
        return self._trace_result("[max iterations reached]", traced_tools, t_start)

    def _run_traced_mistral(self, user_message: str) -> dict[str, Any]:
        """Mistral execution with tool-calling loop."""
        log.info("[%s] run | %.100s", self.name, user_message)
        t_start = time.perf_counter()
        traced_tools: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_message},
        ]

        for i in range(1, self.cfg.max_agent_iterations + 1):
            response = self._call_mistral(messages=messages, include_tools=True)
            if not response.choices:
                log.warning("[%s] empty response from model", self.name)
                return self._trace_result("[no response from model]", traced_tools, t_start)

            msg = response.choices[0].message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                text = msg.content if isinstance(msg.content, str) else json.dumps(msg.content or "")
                ms = (time.perf_counter() - t_start) * 1000
                log.info("[%s] done | %d steps | %.0fms", self.name, i, ms)
                return self._trace_result(text, traced_tools, t_start)

            log.info("[%s] step %d | tools: %s", self.name, i, ", ".join(tc.function.name for tc in tool_calls))
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

        log.warning("[%s] max iterations reached", self.name)
        return self._trace_result("[max iterations reached]", traced_tools, t_start)

    def _trace_result(self, response: str, tool_calls: list, t_start: float) -> dict[str, Any]:
        return {
            "agent": self.name,
            "response": response,
            "tool_calls": tool_calls,
            "duration_ms": round((time.perf_counter() - t_start) * 1000),
        }
