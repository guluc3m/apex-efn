"""Translate one seller message for the buyer reading the transcript (issue 161).

Read-only: the result is returned, never stored and never sent to the seller. The model only translates
(``narrator`` role); code decides everything else. Outgoing text goes through the gateway's redaction guard,
so credentials or bank data in a message are refused instead of sent (criterion 29).
"""

from __future__ import annotations

from apex.agents.schemas import MessageTranslation
from apex.llm.config import LLMRole
from apex.llm.gateway import LLMGateway
from apex.llm.prompts import PromptRegistry

LANGUAGES: dict[str, str] = {"es": "Spanish", "en": "English", "zh": "Chinese", "he": "Hebrew"}


class MessageTranslator:
    def __init__(self, gateway: LLMGateway, prompts: PromptRegistry) -> None:
        self._gateway = gateway
        self._prompts = prompts

    async def translate(
        self, *, tenant_id: str, negotiation_id: str, text: str, target_language: str
    ) -> str:
        rendered = self._prompts.render(
            "narrator_translate_message",
            target_language=LANGUAGES[target_language],
            message_text=text,
        )
        out = await self._gateway.chat_structured(
            LLMRole.NARRATOR,
            rendered.messages,
            MessageTranslation,
            mission_id=f"negotiation:{negotiation_id}",
            tenant_id=tenant_id,
            prompt_version=rendered.prompt_version,
        )
        return out.text


__all__ = ["LANGUAGES", "MessageTranslator"]
