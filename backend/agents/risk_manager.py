from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from google.genai import types

from ..config import AgentConfig
from ..tools import MARKET_TOOLS, PAPER_TRADE_TOOLS
from .base import TradingAgent

log = logging.getLogger(__name__)

_RISK_STRUCTURED_SCHEMA = types.Schema(
    type="OBJECT",
    properties={
        "output_text": types.Schema(
            type="STRING",
            description=(
                "Complete risk report including the RISK DECISIONS block "
                "(one verdict line per proposed trade when trades were proposed)."
            ),
        ),
        "confidence_score": types.Schema(
            type="NUMBER",
            description="Confidence in these risk verdicts, from 0 to 100.",
        ),
    },
    required=["output_text", "confidence_score"],
)

RISK_MANAGER_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "output_text": {"type": "string"},
        "confidence_score": {"type": "number"},
    },
    "required": ["output_text", "confidence_score"],
}

_RISK_STRUCTURED_APPENDIX = """

## Final output (mandatory)

After you finish any portfolio or market tool calls, you will be asked for a single JSON
object only. Keys:
- output_text (string): your full analysis, including the RISK DECISIONS block in the
  format specified above when trades were proposed.
- confidence_score (number 0–100): how confident you are that these verdicts correctly
  reflect portfolio risk and the stated rules.
"""


class RiskManager(TradingAgent):
    """Pre-trade risk gate: tool phase then schema-constrained JSON (output_text + confidence)."""

    def __init__(self, cfg: AgentConfig):
        read_only_trade_tools = [
            t for t in PAPER_TRADE_TOOLS
            if t.name in ("paper_balance", "paper_positions", "paper_history")
        ]
        super().__init__(
            cfg,
            tools=MARKET_TOOLS + read_only_trade_tools,
            prompt_name="risk_manager",
        )
        self._structured_gemini_config = types.GenerateContentConfig(
            system_instruction=self._system_prompt + _RISK_STRUCTURED_APPENDIX,
            temperature=0.0,
            max_output_tokens=min(4096, self.cfg.gemini.max_output_tokens),
            response_mime_type="application/json",
            response_schema=_RISK_STRUCTURED_SCHEMA,
        )

    @staticmethod
    def _parse_model_json(text: str) -> dict[str, Any]:
        text = (text or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```\s*$", "", text)
        return json.loads(text)

    def _risk_json_followup_user_text(self) -> str:
        return (
            "Now respond with ONLY a JSON object (no markdown fences, no prose). "
            'Shape: {"output_text": string, "confidence_score": number}. '
            "output_text must include the full risk write-up and, when trades were proposed, "
            "a RISK DECISIONS block with one verdict line per trade. "
            "confidence_score must be between 0 and 100 (your confidence in these verdicts)."
        )

    def _structured_followup_gemini(self, contents: list[types.Content]) -> str:
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=self._risk_json_followup_user_text())],
            )
        )
        response = self._call_gemini_with_config(contents, self._structured_gemini_config)
        if not response.candidates:
            raise ValueError("empty structured response from Gemini")
        parts = response.candidates[0].content.parts
        return "".join(p.text for p in parts if p.text)

    def _structured_followup_mistral(self, messages: list[dict[str, Any]]) -> str:
        messages = list(messages)
        messages.append({"role": "user", "content": self._risk_json_followup_user_text()})
        sys_msg = self._system_prompt + _RISK_STRUCTURED_APPENDIX
        fmt_schema: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "risk_manager_output",
                "schema": RISK_MANAGER_JSON_SCHEMA,
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
            log.warning("[RiskManager] Mistral json_schema failed (%s), using json_object", e)
            response = self._call_mistral(
                messages=[{"role": "system", "content": sys_msg}, *messages],
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

    def _finalize_risk_json(
        self, json_text: str, traced_tools: list[dict[str, Any]], t_start: float
    ) -> dict[str, Any]:
        try:
            parsed = self._parse_model_json(json_text)
            output_text = str(parsed.get("output_text", "")).strip()
            raw_conf = parsed.get("confidence_score", 0)
            conf = float(raw_conf) if raw_conf is not None else 0.0
            conf = max(0.0, min(100.0, conf))
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            log.warning("[RiskManager] structured parse failed (%s); using empty output, 0 confidence", e)
            output_text = (json_text or "").strip() or "[structured output parse failed]"
            conf = 0.0

        out = self._trace_result(output_text, traced_tools, t_start)
        out["risk_confidence_score"] = conf
        return out

    def _run_risk_phased_gemini(self, user_message: str) -> dict[str, Any]:
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
        ms = (time.perf_counter() - t_start) * 1000
        log.info("[%s] phased gemini done | %.0fms", self.name, ms)
        return self._finalize_risk_json(json_text, traced_tools, t_start)

    def _run_risk_phased_mistral(self, user_message: str) -> dict[str, Any]:
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
                messages.append({"role": "assistant", "content": msg.content or ""})
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
        ms = (time.perf_counter() - t_start) * 1000
        log.info("[%s] phased mistral done | %.0fms", self.name, ms)
        return self._finalize_risk_json(json_text, traced_tools, t_start)

    def run_traced(self, user_message: str) -> dict[str, Any]:
        """Tool phase (optional) then JSON with output_text and confidence_score."""
        if self._gemini_available:
            try:
                result = self._run_risk_phased_gemini(user_message)
                result["provider"] = "gemini"
                return result
            except Exception as e:
                log.warning(
                    "[RiskManager] Gemini phased failed (%s), falling back to Mistral phased",
                    e,
                )
                result = self._run_risk_phased_mistral(user_message)
                result["provider"] = "mistral"
                result["fallback"] = True
                return result
        result = self._run_risk_phased_mistral(user_message)
        result["provider"] = "mistral"
        return result
