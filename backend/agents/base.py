from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml
from google import genai
from google.genai import types
from google.genai.errors import ClientError

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
    """Base class: Gemini model with function-calling wired to Kraken CLI."""

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
        self._api_keys: list[str] = [k for k in [cfg.gemini.api_key, cfg.gemini.fallback_api_key] if k]
        self._active_key_idx = 0
        self.client = genai.Client(
            vertexai=cfg.gemini.use_vertex,
            api_key=self._active_api_key or None,
        )
        self.tools = tools
        self._gen_config = self._build_gen_config()
        key_preview = (self._active_api_key or "")[:8] + "..."
        log.info("[%s] ready | model=%s | %d tools | key=%s | %d key(s) available",
                 self.name, cfg.gemini.model, len(self.tools), key_preview, len(self._api_keys))

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
        self.client = genai.Client(
            vertexai=self.cfg.gemini.use_vertex,
            api_key=self._active_api_key or None,
        )
        key_preview = (self._active_api_key or "")[:8] + "..."
        log.info("[%s] swapped to fallback API key %s", self.name, key_preview)
        return True

    def _build_gen_config(self) -> types.GenerateContentConfig:
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

    def dispatch_tool(self, name: str, args: dict[str, Any]) -> Any:
        """Route a Gemini function call to the matching KrakenClient method."""
        method = getattr(self.kraken, name, None)
        if method is None:
            log.warning("[%s] unknown tool: %s", self.name, name)
            return {"error": f"Unknown tool: {name}"}
        try:
            return method(**args)
        except Exception as e:
            log.error("[%s] %s failed: %s", self.name, name, e)
            return {"error": str(e)}

    def _call_gemini(self, contents: list[types.Content]):
        """Call Gemini with automatic key failover and retry on rate-limit (429)."""
        for attempt in range(MAX_RETRIES):
            try:
                return self.client.models.generate_content(
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

    def run(self, user_message: str) -> str:
        """Single turn: user message -> final text response."""
        result = self.run_traced(user_message)
        return result["response"]

    def run_traced(self, user_message: str) -> dict[str, Any]:
        """Like run(), but returns full trace: response, tool_calls, timing."""
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

    def _trace_result(self, response: str, tool_calls: list, t_start: float) -> dict[str, Any]:
        return {
            "agent": self.name,
            "response": response,
            "tool_calls": tool_calls,
            "duration_ms": round((time.perf_counter() - t_start) * 1000),
        }
