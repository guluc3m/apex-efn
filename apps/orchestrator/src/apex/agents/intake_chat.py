"""IntakeAgent chat turn for onboarding (D4-07b, spec §3.1).

The LLM replies and may *propose* company-profile fields. Code validates every proposed field against
:class:`CompanyProfile` and drops the invalid ones; the buyer confirms what was filled in the form.
Only the non-financial profile goes into the prompt: the budget and any money stay out of LLM context.
"""

from __future__ import annotations

import json
from typing import Any

from apex.agents.onboarding import CompanyProfile, IntakeMessage, OnboardingSession
from apex.agents.schemas import IntakeTurnDraft
from apex.llm.config import LLMRole
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry

HISTORY_TURNS = 12
"""Only the latest turns go back to the model: enough context, bounded tokens."""


class IntakeChatAgent:
    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry) -> None:
        self._gateway = gateway
        self._prompts = prompts

    async def reply(
        self, *, tenant_id: str, session: OnboardingSession, history: list[IntakeMessage], text: str
    ) -> tuple[str, CompanyProfile]:
        known = session.profile.model_dump(exclude={"budget_minor"})
        rendered = self._prompts.render(
            "intake_onboarding_chat",
            profile_json=json.dumps(known, ensure_ascii=False),
            history_text="\n".join(f"{m.role}: {m.text}" for m in history[-HISTORY_TURNS:]),
            user_text=text,
        )
        draft = await self._gateway.chat_structured(
            LLMRole.EXTRACTOR,
            rendered.messages,
            IntakeTurnDraft,
            mission_id=f"onboarding:{session.id}",
            tenant_id=tenant_id,
            prompt_version=rendered.prompt_version,
        )
        return draft.reply, _valid_fields(draft)


def _valid_fields(draft: IntakeTurnDraft) -> CompanyProfile:
    """Keep each proposed field only if it passes the profile validation on its own."""
    fields: dict[str, Any] = {}
    for name, value in draft.profile.model_dump(exclude_none=True).items():
        value = value.strip()
        if name in ("country", "base_currency"):
            value = value.upper()
        try:
            CompanyProfile(**{name: value})
        except ValueError:
            continue
        if value and (name != "country" or len(value) == 2):
            fields[name] = value
    return CompanyProfile(**fields)


__all__ = ["IntakeChatAgent"]
