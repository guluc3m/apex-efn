"""Loading and matching of scenario fixtures.

Priority (highest first):
1. Explicit ``X-Stub-Scenario: <name>`` header.
2. A scenario whose ``models``/``role``/``prompt_sha256`` match the request (most specific wins).
3. The scenario named ``default``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from llm_stub.models import ChatMessage, Scenario

DEFAULT_SCENARIO = "default"
_ROLE_RE = re.compile(r"role:\s*(planner|negotiator|extractor|narrator)\b", re.IGNORECASE)


class ScenarioError(Exception):
    """Raised when a scenario file is invalid or a lookup fails."""


def canonical_messages(messages: Iterable[ChatMessage]) -> str:
    """Canonical JSON of the messages, used for ``prompt_sha256`` matching."""
    payload = [{"role": m.role, "content": m.content} for m in messages]
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def prompt_sha256(messages: Iterable[ChatMessage]) -> str:
    return hashlib.sha256(canonical_messages(messages).encode("utf-8")).hexdigest()


def role_marker(messages: Iterable[ChatMessage]) -> str | None:
    """Return the role named by a ``role: <planner|...>`` marker in the system message."""
    for m in messages:
        if m.role != "system":
            continue
        text = m.content if isinstance(m.content, str) else json.dumps(m.content, default=str)
        match = _ROLE_RE.search(text or "")
        if match:
            return match.group(1).lower()
    return None


def load_scenarios(directory: Path) -> dict[str, Scenario]:
    """Load every ``*.yaml``, ``*.yml`` and ``*.json`` file in ``directory``."""
    if not directory.is_dir():
        raise ScenarioError(f"scenarios directory does not exist: {directory}")
    scenarios: dict[str, Scenario] = {}
    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in {".yaml", ".yml", ".json"})
    for path in files:
        raw = path.read_text(encoding="utf-8")
        data: Any = json.loads(raw) if path.suffix.lower() == ".json" else yaml.safe_load(raw)
        items: list[Any]
        if isinstance(data, dict) and "scenarios" in data:
            items = list(data["scenarios"])
        elif isinstance(data, list):
            items = data
        else:
            items = [data]
        for item in items:
            try:
                scenario = Scenario.model_validate(item)
            except ValidationError as exc:
                raise ScenarioError(f"invalid scenario in {path.name}: {exc}") from exc
            if scenario.name in scenarios:
                raise ScenarioError(f"duplicate scenario name '{scenario.name}' in {path.name}")
            scenarios[scenario.name] = scenario
    if DEFAULT_SCENARIO not in scenarios:
        raise ScenarioError(f"no '{DEFAULT_SCENARIO}' scenario found in {directory}")
    return scenarios


def _specificity(s: Scenario, model: str, role: str | None, digest: str) -> int | None:
    """Return a specificity score if ``s`` matches the request, else None."""
    score = 0
    if s.models:
        if model not in s.models:
            return None
        score += 1
    if s.role is not None:
        if role != s.role:
            return None
        score += 2
    if s.prompt_sha256 is not None:
        if s.prompt_sha256.lower() != digest:
            return None
        score += 4
    if score == 0:
        return None  # only ``default`` (or explicitly-named scenarios) match without criteria
    return score


def select_scenario(
    scenarios: Mapping[str, Scenario],
    *,
    header_name: str | None,
    model: str,
    messages: list[ChatMessage],
) -> Scenario:
    """Resolve the scenario for a chat request. Raises ``ScenarioError`` if unknown name."""
    if header_name:
        if header_name not in scenarios:
            raise ScenarioError(f"unknown scenario '{header_name}'")
        return scenarios[header_name]
    role = role_marker(messages)
    digest = prompt_sha256(messages)
    best: Scenario | None = None
    best_score = -1
    for s in scenarios.values():
        score = _specificity(s, model, role, digest)
        if score is not None and score > best_score:
            best, best_score = s, score
    if best is not None:
        return best
    return scenarios[DEFAULT_SCENARIO]


def select_embedding_scenario(
    scenarios: Mapping[str, Scenario], header_name: str | None, model: str
) -> Scenario:
    if header_name:
        if header_name not in scenarios:
            raise ScenarioError(f"unknown scenario '{header_name}'")
        return scenarios[header_name]
    for s in scenarios.values():
        if s.models and model in s.models and s.name != DEFAULT_SCENARIO:
            return s
    return scenarios[DEFAULT_SCENARIO]
