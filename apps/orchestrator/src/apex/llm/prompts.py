"""Versioned prompt registry (spec §5.6, D4-05).

Prompts live in ``apps/orchestrator/prompts/<name>.v<N>.jinja``. Each file defines a ``system`` block and a
``user`` block and is rendered with ``StrictUndefined``, so a missing variable is a loud error and never an
empty string. The version string ``<name>@v<N>`` is what callers pass as ``prompt_version`` to the
``LLMGateway`` (it ends up in ``LLMEvent``). Rendering takes no clock and no randomness: the caller passes
every value, including "today".

Prompts orchestrate; code decides (spec §10). They never carry thresholds, weights or limits.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, meta

from apex.llm.config import LLMRole

PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"
_FILE_RE = re.compile(r"^(?P<name>[a-z][a-z0-9_]*)\.v(?P<version>\d+)\.jinja$")
_ROLE_RE = re.compile(r"\{#\s*role:\s*(?P<role>[a-z]+)\s*#\}")
_BLOCKS = ("system", "user")


class PromptError(Exception):
    """Unknown prompt, malformed prompt file or missing variable."""


@dataclass(frozen=True)
class PromptSpec:
    name: str
    version: int
    role: LLMRole
    path: Path
    variables: frozenset[str]
    sha256: str

    @property
    def prompt_version(self) -> str:
        return f"{self.name}@v{self.version}"


@dataclass(frozen=True)
class RenderedPrompt:
    spec: PromptSpec
    messages: list[dict[str, Any]]

    @property
    def prompt_version(self) -> str:
        return self.spec.prompt_version


class PromptRegistry:
    """Discovers, validates and renders the prompt files in a directory."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or PROMPTS_DIR
        self._env = Environment(
            loader=FileSystemLoader(str(self._root)),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._specs: dict[tuple[str, int], PromptSpec] = {}
        self._load()

    def _load(self) -> None:
        for path in sorted(self._root.glob("*.jinja")):
            match = _FILE_RE.match(path.name)
            if match is None:
                raise PromptError(f"prompt file name must be <name>.v<N>.jinja: {path.name}")
            source = path.read_text(encoding="utf-8")
            role_match = _ROLE_RE.search(source)
            if role_match is None:
                raise PromptError(f"{path.name}: missing '{{# role: <role> #}}' header")
            try:
                role = LLMRole(role_match.group("role"))
            except ValueError as exc:
                raise PromptError(
                    f"{path.name}: unknown role {role_match.group('role')!r}"
                ) from exc
            template = self._env.get_template(path.name)
            for block in _BLOCKS:
                if block not in template.blocks:
                    raise PromptError(f"{path.name}: missing {{% block {block} %}}")
            variables = frozenset(meta.find_undeclared_variables(self._env.parse(source)))
            spec = PromptSpec(
                name=match.group("name"),
                version=int(match.group("version")),
                role=role,
                path=path,
                variables=variables,
                sha256=hashlib.sha256(source.encode("utf-8")).hexdigest(),
            )
            self._specs[(spec.name, spec.version)] = spec

    def specs(self) -> list[PromptSpec]:
        return [self._specs[key] for key in sorted(self._specs)]

    def latest(self, name: str) -> PromptSpec:
        versions = [v for (n, v) in self._specs if n == name]
        if not versions:
            raise PromptError(f"unknown prompt: {name}")
        return self._specs[(name, max(versions))]

    def get(self, name: str, version: int | None = None) -> PromptSpec:
        if version is None:
            return self.latest(name)
        try:
            return self._specs[(name, version)]
        except KeyError as exc:
            raise PromptError(f"unknown prompt version: {name}@v{version}") from exc

    def render(self, name: str, *, version: int | None = None, **variables: Any) -> RenderedPrompt:
        spec = self.get(name, version)
        missing = spec.variables - variables.keys()
        if missing:
            raise PromptError(f"{spec.prompt_version}: missing variables {sorted(missing)}")
        template = self._env.get_template(spec.path.name)
        context = template.new_context(variables)
        messages = [
            {"role": block, "content": "".join(template.blocks[block](context)).strip()}
            for block in _BLOCKS
        ]
        return RenderedPrompt(spec=spec, messages=messages)


__all__ = ["PROMPTS_DIR", "PromptError", "PromptRegistry", "PromptSpec", "RenderedPrompt"]
