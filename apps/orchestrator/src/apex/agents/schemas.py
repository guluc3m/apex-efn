"""Pydantic shapes of the LLM outputs requested by the versioned prompts (D4-05).

These are *drafts*: text and structure the model produced. Agents validate and then hand them to
deterministic code (importer, planner rules, MCDA). They never carry a computed price, band or score.
Amounts stay as the user's text; code parses them.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class QuantityTierDraft(_Draft):
    min_quantity: int = Field(gt=0)


class SourcingRequestDraft(_Draft):
    spec: str = Field(min_length=1)
    quantity_tiers: list[QuantityTierDraft]
    deadline: str | None
    deadline_text: str | None
    destination_country: str | None
    certifications: list[str]
    budget_text: str | None
    missing_fields: list[str]


class PlanStepDraft(_Draft):
    platform_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    tier_index: int | None = Field(default=None, ge=0)


class SourcingPlanDraft(_Draft):
    steps: list[PlanStepDraft] = Field(min_length=1)
    rationale: str


class HeaderMappingItem(_Draft):
    source: str = Field(min_length=1)
    target: str | None
    reason: str


class HeaderMappingSuggestion(_Draft):
    mappings: list[HeaderMappingItem]


class ImportWarnings(_Draft):
    warnings: list[str]


class MessageTranslation(_Draft):
    text: str = Field(min_length=1)


class RecommendationNarrative(_Draft):
    top_offer_id: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    trade_offs: list[str]


class IntakeProfileDraft(_Draft):
    """Company profile fields the buyer stated in chat. Never money: budget is not here on purpose."""

    legal_name: str | None = Field(default=None, max_length=200)
    sector: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=64)
    base_currency: str | None = Field(default=None, max_length=16)


class IntakeTurnDraft(_Draft):
    reply: str = Field(min_length=1, max_length=2000)
    profile: IntakeProfileDraft


SCHEMAS: dict[str, type[BaseModel]] = {
    "IntakeTurnDraft": IntakeTurnDraft,
    "SourcingRequestDraft": SourcingRequestDraft,
    "SourcingPlanDraft": SourcingPlanDraft,
    "HeaderMappingSuggestion": HeaderMappingSuggestion,
    "ImportWarnings": ImportWarnings,
    "MessageTranslation": MessageTranslation,
    "RecommendationNarrative": RecommendationNarrative,
}

__all__ = [
    "SCHEMAS",
    "HeaderMappingItem",
    "HeaderMappingSuggestion",
    "ImportWarnings",
    "IntakeProfileDraft",
    "IntakeTurnDraft",
    "MessageTranslation",
    "PlanStepDraft",
    "RecommendationNarrative",
    "SourcingPlanDraft",
    "SourcingRequestDraft",
]
