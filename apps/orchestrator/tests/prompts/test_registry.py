"""Prompt registry: discovery, strict rendering, versioning and portability rules."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from apex.llm.config import LLMRole
from apex.llm.prompts import PROMPTS_DIR, PromptError, PromptRegistry


def _write(root: Path, name: str, body: str) -> None:
    (root / name).write_text(body, encoding="utf-8")


GOOD = "{# role: narrator #}\n{% block system %}Hi {{ who }}{% endblock %}\n{% block user %}Go{% endblock %}\n"


def test_all_shipped_prompts_load_with_a_role_and_version() -> None:
    specs = PromptRegistry().specs()
    assert len(specs) >= 5
    for spec in specs:
        assert spec.version >= 1
        assert isinstance(spec.role, LLMRole)
        assert spec.prompt_version == f"{spec.name}@v{spec.version}"


def test_render_returns_system_then_user_messages() -> None:
    rendered = PromptRegistry().render("narrator_import_warnings", language="es", report_json="{}")
    assert [m["role"] for m in rendered.messages] == ["system", "user"]
    assert "es" in rendered.messages[0]["content"]
    assert rendered.prompt_version == "narrator_import_warnings@v1"


def test_missing_variable_is_a_loud_error(tmp_path: Path) -> None:
    _write(tmp_path, "greet.v1.jinja", GOOD)
    with pytest.raises(PromptError, match="missing variables"):
        PromptRegistry(tmp_path).render("greet")


def test_rendering_is_deterministic() -> None:
    reg = PromptRegistry()
    a = reg.render("planner_sourcing_plan", request_json="{}", platforms_json="[]")
    b = reg.render("planner_sourcing_plan", request_json="{}", platforms_json="[]")
    assert a.messages == b.messages


def test_latest_picks_highest_version_and_old_versions_stay_addressable(tmp_path: Path) -> None:
    _write(tmp_path, "greet.v1.jinja", GOOD)
    _write(tmp_path, "greet.v2.jinja", GOOD.replace("Hi", "Hello"))
    reg = PromptRegistry(tmp_path)
    assert reg.latest("greet").version == 2
    assert "Hi" in reg.render("greet", version=1, who="x").messages[0]["content"]
    assert "Hello" in reg.render("greet", who="x").messages[0]["content"]
    assert reg.get("greet", 1).sha256 != reg.get("greet", 2).sha256


def test_unknown_prompt_and_version_raise(tmp_path: Path) -> None:
    _write(tmp_path, "greet.v1.jinja", GOOD)
    reg = PromptRegistry(tmp_path)
    with pytest.raises(PromptError, match="unknown prompt: nope"):
        reg.latest("nope")
    with pytest.raises(PromptError, match="greet@v9"):
        reg.get("greet", 9)


@pytest.mark.parametrize(
    ("name", "body", "message"),
    [
        ("bad-name.jinja", GOOD, "must be <name>.v<N>.jinja"),
        ("x.v1.jinja", "{% block system %}a{% endblock %}{% block user %}b{% endblock %}", "role"),
        (
            "x.v1.jinja",
            "{# role: wizard #}{% block system %}a{% endblock %}{% block user %}b{% endblock %}",
            "unknown role",
        ),
        ("x.v1.jinja", "{# role: narrator #}{% block system %}a{% endblock %}", "block user"),
    ],
)
def test_malformed_prompt_files_fail_at_load(
    tmp_path: Path, name: str, body: str, message: str
) -> None:
    _write(tmp_path, name, body)
    with pytest.raises(PromptError, match=message):
        PromptRegistry(tmp_path)


def test_prompts_are_portable_and_carry_no_business_numbers() -> None:
    """No model-specific tricks (spec §5.6) and no thresholds or limits baked into prompt text."""
    forbidden_tricks = re.compile(
        r"(?i)\b(gpt|claude|llama|mistral|qwen|gemini)\b|<\|im_start\|>|\[INST\]"
    )
    for path in PROMPTS_DIR.glob("*.jinja"):
        text = path.read_text(encoding="utf-8")
        assert not forbidden_tricks.search(text), path.name
        literal_text = re.sub(r"\{[{%#].*?[}%#]\}", "", text, flags=re.S)
        assert not re.search(r"\b\d{2,}\s?%|\b\d+\s?(EUR|USD|CNY)\b", literal_text), path.name


def test_every_prompt_demands_json_only_and_forbids_inventing() -> None:
    for spec in PromptRegistry().specs():
        system = spec.path.read_text(encoding="utf-8")
        assert "one JSON object and nothing else" in system, spec.name
