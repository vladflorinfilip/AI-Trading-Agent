from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import yaml
from google import genai
from google.genai import types

from ..config import AgentConfig
from ..kraken_client import KrakenClient

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt(name: str) -> dict[str, Any]:
    path = PROMPTS_DIR / f"{name}.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


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
        self.client = genai.Client(
            vertexai=cfg.gemini.use_vertex,
            api_key=cfg.gemini.api_key or None,
        )
        self.tools = tools
        self._gen_config = self._build_gen_config()
        log.info("[%s] ready | model=%s | %d tools", self.name, cfg.gemini.model, len(self.tools))

    def _build_gen_config(self) -> types.GenerateContentConfig:
        system_prompt = self.prompt_data["system_prompt"]
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

    def run(self, user_message: str) -> str:
        """Single turn: user message -> (tool calls)* -> final text response."""
        log.info("[%s] run | %.100s", self.name, user_message)
        t_start = time.perf_counter()

        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)]),
        ]

        for i in range(1, self.cfg.max_agent_iterations + 1):
            response = self.client.models.generate_content(
                model=self.cfg.gemini.model,
                contents=contents,
                config=self._gen_config,
            )

            if not response.candidates:
                log.warning("[%s] empty response from model", self.name)
                return "[no response from model]"

            parts = response.candidates[0].content.parts
            tool_calls = [p for p in parts if p.function_call]

            if not tool_calls:
                text = "".join(p.text for p in parts if p.text)
                ms = (time.perf_counter() - t_start) * 1000
                log.info("[%s] done | %d steps | %.0fms", self.name, i, ms)
                return text

            log.info("[%s] step %d | tools: %s",
                     self.name, i, ", ".join(p.function_call.name for p in tool_calls))

            contents.append(response.candidates[0].content)
            tool_responses: list[types.Part] = []
            for part in tool_calls:
                fc = part.function_call
                result = self.dispatch_tool(fc.name, dict(fc.args))
                tool_responses.append(
                    types.Part.from_function_response(
                        name=fc.name, response={"result": result},
                    )
                )
            contents.append(types.Content(role="user", parts=tool_responses))

        log.warning("[%s] max iterations reached", self.name)
        return "[max iterations reached]"
