"""``POST /v1/negotiations/{id}/messages/{message_id}/translate`` (issue 161).

Mounted under the same prefix as the negotiation router. Refusals are RFC 9457 problems with a closed reason:
``not_found`` (negotiation or message), ``sensitive_content`` (422, nothing was sent to the model),
``translation_unavailable`` (502, model down or over budget).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from apex.api.negotiations import _problem, get_negotiation_control
from apex.common.errors import Problem, not_implemented
from apex.common.tenant import get_tenant_id
from apex.contracts.generated.models import (
    NegotiationMessageTranslateRequest,
    NegotiationMessageTranslation,
)
from apex.llm.budget import TokenBudgetExceeded
from apex.llm.gateway import LLMGatewayError
from apex.llm.redaction import RedactionViolation
from apex.llm.resilience import AllEndpointsUnavailableError, CircuitOpenError
from apex.llm.structured import StructuredOutputError
from apex.llm.transport import LLMHTTPError, LLMTransportError
from apex.negotiation.api import NegotiationControlService
from apex.negotiation.api import message_id as public_message_id
from apex.negotiation.engine import NegotiationError

router = APIRouter()

_UNAVAILABLE = (
    LLMGatewayError,
    StructuredOutputError,
    TokenBudgetExceeded,
    AllEndpointsUnavailableError,
    CircuitOpenError,
    LLMHTTPError,
    LLMTransportError,
)


def get_translator() -> Any:
    """Overridable dependency: a ``MessageTranslator``."""
    raise not_implemented("the message translator needs the LLM gateway; wire it in the app")


@router.post("/{id}/messages/{message_id}/translate", response_model=NegotiationMessageTranslation)
async def translate_negotiation_message(
    id: str,
    message_id: str,
    body: NegotiationMessageTranslateRequest,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
    control: Annotated[NegotiationControlService, Depends(get_negotiation_control)],
    translator: Annotated[Any, Depends(get_translator)],
) -> NegotiationMessageTranslation:
    """Translation of one transcript message. Nothing is stored or sent to the seller."""
    try:
        session = await control.get(id, tenant_id=tenant_id)
    except NegotiationError as exc:
        raise _problem(exc) from exc
    message = next(
        (m for m in session.transcript if public_message_id(session, m) == message_id), None
    )
    if message is None:
        raise Problem(404, "Not Found", detail="unknown message", reason="not_found")
    try:
        text = await translator.translate(
            tenant_id=tenant_id,
            negotiation_id=session.id,
            text=message.text,
            target_language=body.target_language.value,
        )
    except RedactionViolation as exc:
        raise Problem(
            422,
            "Unprocessable Entity",
            detail="the message contains credentials or bank data and was not sent to the model",
            reason="sensitive_content",
        ) from exc
    except _UNAVAILABLE as exc:
        raise Problem(
            502,
            "Bad Gateway",
            detail="translation is unavailable",
            reason="translation_unavailable",
        ) from exc
    return NegotiationMessageTranslation(
        message_id=message_id, target_language=body.target_language, text=text
    )
