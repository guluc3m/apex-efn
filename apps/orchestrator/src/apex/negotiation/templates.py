"""Deterministic message templates (D5-07b).

Used when the LLM is unavailable or its drafts fail the guardrails or the plan check, so the agent can
always send a compliant message. Every template states only the price chosen by the playbook.
"""

from __future__ import annotations

from apex.negotiation.models import Intent, NegotiationSession, Plan


def format_price(minor: int, currency: str) -> str:
    """``EUR 4.10``: the form the guardrails and every seller parser recognise."""
    return f"{currency} {minor // 100}.{minor % 100:02d}"


def _context_en(session: NegotiationSession) -> str:
    c = session.params.context
    parts = [f"we are sourcing {session.params.quantity} units of {c.product_title}"]
    if c.destination:
        parts.append(f"delivered to {c.destination}")
    if c.deadline:
        parts.append(f"needed by {c.deadline}")
    text = ", ".join(parts)
    if c.recurring:
        text += ", and we expect to reorder regularly"
    return text


def _context_es(session: NegotiationSession) -> str:
    c = session.params.context
    parts = [f"buscamos {session.params.quantity} unidades de {c.product_title}"]
    if c.destination:
        parts.append(f"con entrega en {c.destination}")
    if c.deadline:
        parts.append(f"para antes de {c.deadline}")
    text = ", ".join(parts)
    if c.recurring:
        text += ", con intención de repetir pedido"
    return text


def render(plan: Plan, session: NegotiationSession) -> str:
    p = session.params
    price = format_price(plan.price_minor, p.currency) if plan.price_minor is not None else ""
    q = p.quantity
    if p.language == "es":
        texts = {
            Intent.OPEN: f"Hola, {_context_es(session)}. ¿Qué escalado de precios por volumen ofrecen?",
            Intent.REQUEST_PRICE: f"Gracias. ¿Podrían indicarnos el precio unitario para {q} unidades?",
            Intent.ANCHOR: f"Gracias. Para {q} unidades, ¿podrían ofrecernos {price} por unidad?",
            Intent.COUNTER: f"Entendemos. Para {q} unidades podemos considerar {price} por unidad.",
            Intent.REQUEST_CURRENCY: f"¿Podrían enviarnos la cotización en {p.currency}, por favor?",
            Intent.SUMMARY: (
                f"Resumen: {q} unidades a {price} por unidad. "
                "¿Pueden confirmar estas condiciones por escrito? Nuestro equipo las revisará."
            ),
        }
    else:
        texts = {
            Intent.OPEN: f"Hello, {_context_en(session)}. What volume price tiers do you offer?",
            Intent.REQUEST_PRICE: f"Thank you. Could you share your unit price for {q} units?",
            Intent.ANCHOR: f"Thank you. For {q} units, could you offer {price} per unit?",
            Intent.COUNTER: f"We understand. For {q} units we could consider {price} per unit.",
            Intent.REQUEST_CURRENCY: f"Could you please send the quote in {p.currency}?",
            Intent.SUMMARY: (
                f"Summary: {q} units at {price} per unit. "
                "Could you confirm these conditions in writing? Our team will review them."
            ),
        }
    return texts[plan.intent]
