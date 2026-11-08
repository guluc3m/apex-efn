"""Structured-output escalation ladder (spec §5.6).

Steps, in order, each validated with Pydantic:

1. ``response_format: json_schema`` — only if ``supports_json_schema``.
2. ``response_format: json_object`` + schema in the prompt — only if ``supports_json_object``.
3. Tool call with the schema as function parameters — only if ``supports_tools``.
4. Guided decoding (vLLM ``guided_json`` / llama.cpp ``grammar``) — only if declared.
5. Plain completion, parsed with at most ``MAX_REPAIR_ATTEMPTS`` (2) repair round-trips that re-prompt
   with the validation error.

Capability-gated steps are skipped entirely (no ``response_format`` is sent to an endpoint that did not
declare it). An HTTP 400 "unsupported" response degrades to the next step and is recorded. When every
step fails, :class:`StructuredOutputError` is raised with the attempt log — never a default value.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from apex.llm.config import CapabilityProfile, GuidedDecoding
from apex.llm.transport import LLMHTTPError

MAX_REPAIR_ATTEMPTS = 2

M = TypeVar("M", bound=BaseModel)

# Single chat round-trip: (messages, extra_request_params) -> (choice_message, usage)
ChatInvoker = Callable[
    [list[dict[str, Any]], dict[str, Any]],
    Awaitable[tuple[dict[str, Any], dict[str, Any]]],
]


class LadderStep(StrEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"
    TOOL_CALL = "tool_call"
    GUIDED = "guided"
    PLAIN_REPAIR = "plain_repair"


@dataclass
class AttemptRecord:
    step: LadderStep
    # ok | skipped_unsupported | degraded_400 | validation_failed | http_error
    outcome: str
    detail: str = ""


class StructuredOutputError(Exception):
    """All ladder steps failed. ``attempts`` lists every step tried and why it failed."""

    def __init__(self, schema_name: str, attempts: list[AttemptRecord]) -> None:
        self.schema_name = schema_name
        self.attempts = attempts
        summary = "; ".join(f"{a.step.value}:{a.outcome}" for a in attempts)
        super().__init__(f"structured output failed for {schema_name} ({summary})")


@dataclass
class StructuredResult:
    value: Any
    step: LadderStep
    repair_attempts: int
    attempts: list[AttemptRecord] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


class _StepDegraded(Exception):
    """HTTP 400 'unsupported' on a native step: degrade to the next step."""


class _StepValidationFailed(Exception):
    """Native step returned output that did not validate: degrade to the next step."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def schema_json(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema()


def build_schema_prompt(model: type[BaseModel]) -> str:
    return (
        "Respond ONLY with a JSON object matching this JSON schema. No text outside the JSON.\n"
        f"```json\n{json.dumps(schema_json(model), ensure_ascii=False)}\n```"
    )


def parse_json_text(text: str) -> Any:
    """Parse model output as JSON, tolerating a single fenced code block."""
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
        if match is None:
            raise
        return json.loads(match.group(1).strip())


def _tool_for(model: type[BaseModel]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": model.__name__,
            "description": f"Return the {model.__name__} object.",
            "parameters": schema_json(model),
        },
    }


def _guided_extra(guided: GuidedDecoding, model: type[BaseModel]) -> dict[str, Any]:
    schema = schema_json(model)
    if guided is GuidedDecoding.VLLM_GUIDED_JSON:
        return {"guided_json": schema}
    if guided is GuidedDecoding.LLAMACPP_GRAMMAR:
        # llama.cpp server accepts a JSON schema converted server-side into a grammar.
        return {"json_schema": schema}
    return {}


def plan_steps(caps: CapabilityProfile) -> list[LadderStep]:
    """Steps the declared capabilities allow, in ladder order (plain repair is always last)."""
    steps: list[LadderStep] = []
    if caps.supports_json_schema:
        steps.append(LadderStep.JSON_SCHEMA)
    if caps.supports_json_object:
        steps.append(LadderStep.JSON_OBJECT)
    if caps.supports_tools:
        steps.append(LadderStep.TOOL_CALL)
    if caps.supports_guided is not GuidedDecoding.NONE:
        steps.append(LadderStep.GUIDED)
    steps.append(LadderStep.PLAIN_REPAIR)
    return steps


def _tool_arguments(message: dict[str, Any]) -> str:
    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        raise _StepValidationFailed("no tool_calls in response")
    arguments = tool_calls[0].get("function", {}).get("arguments")
    if not isinstance(arguments, str):
        raise _StepValidationFailed("tool call arguments missing")
    return arguments


async def _attempt_native[M: BaseModel](
    step: LadderStep,
    model: type[M],
    base_messages: list[dict[str, Any]],
    caps: CapabilityProfile,
    invoke: ChatInvoker,
) -> StructuredResult:
    messages = base_messages
    extra: dict[str, Any]
    if step is LadderStep.JSON_SCHEMA:
        extra = {
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": model.__name__,
                    "schema": schema_json(model),
                    "strict": True,
                },
            }
        }
    elif step is LadderStep.JSON_OBJECT:
        extra = {"response_format": {"type": "json_object"}}
        messages = [*base_messages, {"role": "system", "content": build_schema_prompt(model)}]
    elif step is LadderStep.TOOL_CALL:
        extra = {
            "tools": [_tool_for(model)],
            "tool_choice": {"type": "function", "function": {"name": model.__name__}},
        }
    else:  # GUIDED
        extra = _guided_extra(caps.supports_guided, model)

    try:
        message, usage = await invoke(messages, extra)
    except LLMHTTPError as exc:
        if exc.is_unsupported:
            raise _StepDegraded(exc.body_excerpt[:120]) from exc
        raise

    raw_text = (
        _tool_arguments(message)
        if step is LadderStep.TOOL_CALL
        else str(message.get("content") or "")
    )
    try:
        value = model.model_validate(parse_json_text(raw_text))
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise _StepValidationFailed(str(exc)[:200]) from exc

    return StructuredResult(
        value=value,
        step=step,
        repair_attempts=0,
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
    )


async def _plain_with_repair[M: BaseModel](
    model: type[M],
    base_messages: list[dict[str, Any]],
    invoke: ChatInvoker,
    attempts: list[AttemptRecord],
) -> StructuredResult:
    messages = [*base_messages, {"role": "system", "content": build_schema_prompt(model)}]
    prompt_tokens = 0
    completion_tokens = 0
    for repair in range(MAX_REPAIR_ATTEMPTS + 1):
        message, usage = await invoke(messages, {})
        prompt_tokens += int(usage.get("prompt_tokens", 0))
        completion_tokens += int(usage.get("completion_tokens", 0))
        content = str(message.get("content") or "")
        try:
            value = model.model_validate(parse_json_text(content))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            error = str(exc)[:300]
            attempts.append(
                AttemptRecord(
                    LadderStep.PLAIN_REPAIR, "validation_failed", f"try={repair}: {error}"
                )
            )
            if repair == MAX_REPAIR_ATTEMPTS:
                break
            messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "The previous answer was not valid JSON for the schema. Error:\n"
                        f"{error}\nReturn ONLY the corrected JSON object."
                    ),
                },
            ]
            continue
        attempts.append(AttemptRecord(LadderStep.PLAIN_REPAIR, "ok", f"repairs={repair}"))
        return StructuredResult(
            value=value,
            step=LadderStep.PLAIN_REPAIR,
            repair_attempts=repair,
            attempts=attempts,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
    raise StructuredOutputError(model.__name__, attempts)


async def run_ladder[M: BaseModel](
    *,
    model: type[M],
    base_messages: list[dict[str, Any]],
    caps: CapabilityProfile,
    invoke: ChatInvoker,
) -> StructuredResult:
    """Run the ladder. Only capability-declared native steps are attempted.

    Raises :class:`StructuredOutputError` (with the attempt log) when every step fails.
    Non-400 HTTP errors and transport errors propagate to the resilience layer, not the ladder.
    """
    attempts: list[AttemptRecord] = []
    declared = set(plan_steps(caps))
    for step in (
        LadderStep.JSON_SCHEMA,
        LadderStep.JSON_OBJECT,
        LadderStep.TOOL_CALL,
        LadderStep.GUIDED,
    ):
        if step not in declared:
            attempts.append(AttemptRecord(step, "skipped_unsupported", "capability not declared"))
            continue
        try:
            result = await _attempt_native(step, model, base_messages, caps, invoke)
        except _StepDegraded as exc:
            attempts.append(AttemptRecord(step, "degraded_400", str(exc)))
            continue
        except _StepValidationFailed as exc:
            attempts.append(AttemptRecord(step, "validation_failed", exc.detail))
            continue
        attempts.append(AttemptRecord(step, "ok"))
        result.attempts = attempts
        return result

    return await _plain_with_repair(model, base_messages, invoke, attempts)


__all__ = [
    "MAX_REPAIR_ATTEMPTS",
    "AttemptRecord",
    "ChatInvoker",
    "LadderStep",
    "StructuredOutputError",
    "StructuredResult",
    "build_schema_prompt",
    "parse_json_text",
    "plan_steps",
    "run_ladder",
]
