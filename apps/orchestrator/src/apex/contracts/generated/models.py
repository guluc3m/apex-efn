# DO NOT EDIT. Generated from contracts/openapi.yaml by contracts/scripts/generate.mjs.
# ruff: noqa: UP035, UP040

from __future__ import annotations

from datetime import date as date_aliased
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field, RootModel
from typing_extensions import TypeAliasType


class Problem(BaseModel):
    """
    RFC 9457 problem details.
    """

    model_config = ConfigDict(
        extra="allow",
    )
    type: str
    title: str
    status: Annotated[int, Field(ge=400, le=599)]
    detail: str | None = None
    instance: str | None = None


class FieldError(BaseModel):
    field: str
    code: str
    message: str


class ValidationProblem(Problem):
    errors: list[FieldError]


class BlockReasonCode(StrEnum):
    """
    Why an action is not available (D4-11). Closed so the UI can translate it.
    """

    price_band_requires_unblock = "price_band_requires_unblock"
    seller_band_requires_unblock = "seller_band_requires_unblock"
    out_of_budget = "out_of_budget"
    financials_stale = "financials_stale"
    fx_provisional = "fx_provisional"
    renegotiation_limit = "renegotiation_limit"
    already_decided = "already_decided"
    not_in_queue = "not_in_queue"
    role_not_allowed = "role_not_allowed"
    comment_required = "comment_required"


class ReauthReason(StrEnum):
    session_missing = "session_missing"
    session_expired = "session_expired"
    session_revoked = "session_revoked"
    session_exhausted = "session_exhausted"
    key_revoked = "key_revoked"
    key_rotated = "key_rotated"
    device_mismatch = "device_mismatch"
    network_anomaly = "network_anomaly"
    high_value_decision = "high_value_decision"
    immediate_reauth_required = "immediate_reauth_required"
    risk_flagged = "risk_flagged"
    step_up_required = "step_up_required"


class Currency(StrEnum):
    """
    Closed enum. No other currency is accepted anywhere (spec 3.5.1).
    """

    EUR = "EUR"
    USD = "USD"
    CNY = "CNY"


class Money(BaseModel):
    """
    Amount in integer minor units (cents, fen). Never a float.
    """

    amount_minor: Annotated[int, Field(ge=-9223372036854775808, le=9223372036854775807)]
    currency: Currency


class ConvertedMoney(BaseModel):
    """
    Money that may have been converted from another currency at ingestion (spec 3.5.1).
    """

    amount_minor: Annotated[int, Field(ge=-9223372036854775808, le=9223372036854775807)]
    currency: Currency
    original_amount_minor: Annotated[
        int | None, Field(ge=-9223372036854775808, le=9223372036854775807)
    ] = None
    original_currency: Currency | None = None
    fx_rate: Annotated[
        str | None,
        Field(description="Decimal string, never a float.", pattern="^[0-9]+(\\.[0-9]+)?$"),
    ] = None
    fx_as_of: AwareDatetime | None = None
    fx_source: str | None = None
    converted: bool
    fx_provisional: Annotated[
        bool,
        Field(description="True when the rate is older than fx.max_age_hours (spec 3.5.1)."),
    ]


class PriceSanityBand(StrEnum):
    normal = "normal"
    atypical = "atypical"
    implausible = "implausible"
    insufficient_reference = "insufficient_reference"


class SellerConfidenceBand(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"
    untrusted = "untrusted"
    insufficient_data = "insufficient_data"


class FinancialVerdict(StrEnum):
    within_budget = "within_budget"
    stretch = "stretch"
    out_of_budget = "out_of_budget"


class SignatureStatus(StrEnum):
    unsigned = "unsigned"
    pending = "pending"
    signed = "signed"
    invalid = "invalid"


class DecisionType(StrEnum):
    """
    `deal_action` carries `action` in its payload; `service_event` is an automatic transition signed by a service key (ADR-209).
    """

    follow = "follow"
    renegotiate = "renegotiate"
    takeover = "takeover"
    hold = "hold"
    discard = "discard"
    approve_purchase = "approve_purchase"
    financial_snapshot_activation = "financial_snapshot_activation"
    gate_override_discard = "gate_override_discard"
    change_pricing_threshold = "change_pricing_threshold"
    change_confidence_weights = "change_confidence_weights"
    change_scoring_weights = "change_scoring_weights"
    rotate_key = "rotate_key"
    revoke_key = "revoke_key"
    gate_unblock = "gate_unblock"
    config_change = "config_change"
    deal_action = "deal_action"
    service_event = "service_event"


class DecisionStatus(StrEnum):
    pending_signature = "pending_signature"
    signed = "signed"
    rejected = "rejected"
    expired = "expired"


class MissionState(StrEnum):
    created = "created"
    planning = "planning"
    sourcing = "sourcing"
    enriching = "enriching"
    evaluating = "evaluating"
    negotiating = "negotiating"
    awaiting_decision = "awaiting_decision"
    completed = "completed"
    cancelled = "cancelled"
    failed = "failed"


class OfferState(StrEnum):
    discovered = "discovered"
    enriched = "enriched"
    trust_scored = "trust_scored"
    sanity_checked = "sanity_checked"
    gate_pending = "gate_pending"
    gate_approved = "gate_approved"
    gate_rejected = "gate_rejected"
    financially_checked = "financially_checked"
    negotiating = "negotiating"
    negotiated = "negotiated"
    sanity_rechecked = "sanity_rechecked"
    scored = "scored"
    awaiting_human = "awaiting_human"
    signed = "signed"
    approved = "approved"
    rejected = "rejected"
    purchased = "purchased"


class Tenant(BaseModel):
    id: str
    name: str
    base_currency: Currency


class Role(StrEnum):
    """
    RBAC roles (spec 5.9). Only buyer, finance, admin and owner can sign.
    """

    owner = "owner"
    admin = "admin"
    buyer = "buyer"
    finance = "finance"
    viewer = "viewer"


class Membership(BaseModel):
    user_id: str
    tenant_id: str
    role: Role


class User(BaseModel):
    id: str
    display_name: str


class Role1(StrEnum):
    user = "user"
    agent = "agent"


class IntakeMessage(BaseModel):
    id: str
    role: Role1
    text: str
    created_at: AwareDatetime


class IntakeMessageList(BaseModel):
    items: list[IntakeMessage]


class SendIntakeMessageRequest(BaseModel):
    text: Annotated[str, Field(max_length=4000, min_length=1)]


class Item(BaseModel):
    id: Annotated[
        str,
        Field(
            description="The category as the tenant wrote it. No translated label: there is no catalog to translate from."
        ),
    ]


class CategoryList(BaseModel):
    items: list[Item]


class OnboardingStep(StrEnum):
    company = "company"
    sector = "sector"
    accounts = "accounts"
    budget = "budget"
    policy = "policy"
    negotiation = "negotiation"
    finance = "finance"


class OnboardingStepProgress(BaseModel):
    step: OnboardingStep
    done: Annotated[int, Field(description="Required items already filled in.", ge=0)]
    warnings: Annotated[
        int,
        Field(description="Items that need a look (for example import warnings).", ge=0),
    ]
    pending: Annotated[int, Field(description="Required items still missing.", ge=0)]


class FinancialCsvUpload(BaseModel):
    file: Annotated[
        bytes,
        Field(description="UTF-8 CSV, long format (spec 3.1.1). Separator is autodetected."),
    ]
    column_mapping: Annotated[
        str | None,
        Field(
            description="Optional JSON object {source_header: canonical_column} the buyer confirmed. Applied to the header row before parsing."
        ),
    ] = None


class Mapping(BaseModel):
    source: str
    target: Annotated[str | None, Field(description="A canonical column")]
    reason: str


class HeaderMappingSuggestion(BaseModel):
    canonical_columns: list[str]
    mappings: list[Mapping]


class ActivateFinancialSnapshotRequest(BaseModel):
    import_id: Annotated[str, Field(description="Draft import to activate.")]


class Status(StrEnum):
    active = "active"
    superseded = "superseded"


class CompanyFinancialsSnapshot(BaseModel):
    """
    Immutable once active or superseded (spec 6, 3.1.1).
    """

    id: str
    version: Annotated[int, Field(ge=1)]
    status: Status
    import_id: str
    base_currency: Currency
    activated_at: AwareDatetime | None = None
    activated_by: str | None = None
    decision_id: str | None = None
    superseded_at: AwareDatetime | None = None
    created_at: AwareDatetime


class BudgetEnvelope(BaseModel):
    category: str
    allocated: Money
    spent: Money
    available: Money
    period_start: date_aliased
    period_end: date_aliased


class CredentialRef(BaseModel):
    id: Annotated[
        str,
        Field(description="Opaque vault pointer. Never shown to the LLM or the browser."),
    ]


WeightsAdditionalProperty = TypeAliasType(
    "WeightsAdditionalProperty", Annotated[float, Field(ge=0.0, le=1.0)]
)


class NullableMoney(RootModel[Money | None]):
    root: Money | None


class CreateSourcingRequest(BaseModel):
    natural_language: Annotated[
        str,
        Field(
            description="The need in free text. An agent normalizes it (spec 3.2).",
            max_length=4000,
            min_length=1,
        ),
    ]
    delivery_country: Annotated[str, Field(pattern="^[A-Z]{2}$")]
    target_delivery_date: date_aliased | None = None
    max_budget: NullableMoney | None = None
    excluded_platforms: list[str] | None = None
    excluded_countries: list[str] | None = None


class SourcingSpec(BaseModel):
    description: str
    specifications: dict[str, str] | None = None
    certifications: list[str] | None = None


class CreateMissionRequest(BaseModel):
    sourcing_request_id: str
    profile_id: str | None = None
    token_budget: Annotated[
        int | None,
        Field(
            description="Hard LLM token budget for the mission (spec 5.6). Null uses the tenant default.",
            ge=1,
        ),
    ] = None


class Mission(BaseModel):
    id: str
    sourcing_request_id: str
    profile_id: Annotated[
        str | None,
        Field(description="Default ranking profile of the mission (a UserProfilePreference id)."),
    ] = None
    paused: Annotated[
        bool | None,
        Field(
            description="True after POST /pause until POST /resume. Orthogonal to `state`, which keeps the graph step."
        ),
    ] = None
    plan_id: str | None = None
    state: MissionState
    offers_discovered: Annotated[int, Field(ge=0)]
    offers_negotiated: Annotated[int, Field(ge=0)]
    offers_in_gate: Annotated[int, Field(ge=0)]
    tokens_used: Annotated[int, Field(ge=0)]
    token_budget: Annotated[int, Field(ge=1)]
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    error: Problem | None = None


class MissionPage(BaseModel):
    items: list[Mission]
    next_cursor: str | None


class ConfigVersionSummary(BaseModel):
    config_version: Annotated[int, Field(ge=1)]
    category: str | None = None
    created_at: AwareDatetime
    decision_id: Annotated[
        str | None,
        Field(
            description="The signed decision that created this version. Null for the seeded baseline."
        ),
    ] = None
    signer_id: str | None = None
    reason: str | None = None
    summary: Annotated[
        list[str] | None, Field(description="Dotted config keys the version changed.")
    ] = None


class ConfigVersionPage(BaseModel):
    items: list[ConfigVersionSummary]
    next_cursor: str | None


class Seller(BaseModel):
    id: str
    canonical_id: str
    platform_ids: list[str]
    country: str | None
    risk_flags: list[str]


class PriceTier(BaseModel):
    min_quantity: Annotated[int, Field(ge=1)]
    max_quantity: Annotated[int | None, Field(ge=1)] = None
    unit_price: Money


class ShippingEstimate(BaseModel):
    cost: Money
    min_days: Annotated[int, Field(ge=0)]
    max_days: Annotated[int, Field(ge=0)]
    carrier: str | None = None


class Incoterm(StrEnum):
    EXW = "EXW"
    FCA = "FCA"
    FAS = "FAS"
    FOB = "FOB"
    CFR = "CFR"
    CIF = "CIF"
    CPT = "CPT"
    CIP = "CIP"
    DAP = "DAP"
    DPU = "DPU"
    DDP = "DDP"


class SellerSignalSnapshot(BaseModel):
    """
    Immutable raw signals captured at a point in time (spec 3.4.1, 6).
    """

    id: str
    seller_id: str
    account_age_days: Annotated[int | None, Field(ge=0)] = None
    first_sale_date: date_aliased | None = None
    months_active_last_12: Annotated[int | None, Field(ge=0, le=12)] = None
    lifetime_transactions: Annotated[int | None, Field(ge=0)] = None
    transactions_12m: Annotated[int | None, Field(ge=0)] = None
    gmv_12m: NullableMoney | None = None
    repeat_buyer_share: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    published_products_count: Annotated[int | None, Field(ge=0)] = None
    catalog_churn_30d: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    spec_completeness_avg: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    reviews_total: Annotated[int | None, Field(ge=0)] = None
    reviews_12m: Annotated[int | None, Field(ge=0)] = None
    rating_avg: Annotated[float | None, Field(ge=0.0, le=5.0)] = None
    rating_count: Annotated[int | None, Field(ge=0)] = None
    verified_review_share: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    response_rate: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    identity_verified: bool | None = None
    trade_assurance: bool | None = None
    escrow_available: bool | None = None
    dispute_rate: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    refund_rate: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    data_completeness: Annotated[
        float,
        Field(
            description="Present signals over required signals (spec 3.4.1, ADR-303).",
            ge=0.0,
            le=1.0,
        ),
    ]
    captured_at: AwareDatetime


class DispersionMeasure(StrEnum):
    mad = "mad"
    iqr = "iqr"
    relative = "relative"


class SanityDecision(StrEnum):
    negotiate = "negotiate"
    human_gate = "human_gate"
    discard = "discard"


class PriceExplanationCode(StrEnum):
    """
    Structured causes only. Never free text generated by an LLM (spec 3.3.3).
    """

    volume_tier_difference = "volume_tier_difference"
    moq_difference = "moq_difference"
    incoterm_difference = "incoterm_difference"
    quality_grade_difference = "quality_grade_difference"
    specification_difference = "specification_difference"
    seasonal_pricing = "seasonal_pricing"
    clearance_sale = "clearance_sale"
    new_seller_promotion = "new_seller_promotion"
    bulk_discount = "bulk_discount"
    none = "none"


class PriceHistory(BaseModel):
    product_key: str
    seller_id: str
    landed_unit_cost: Money
    date: date_aliased
    mission_id: str | None = None


class FxRate(BaseModel):
    """
    Immutable history row (spec 3.5.1). Rate is a decimal string.
    """

    base: Currency
    quote: Currency
    rate: Annotated[str, Field(pattern="^[0-9]+(\\.[0-9]+)?$")]
    as_of: AwareDatetime
    source: str


class TradeOff(BaseModel):
    """
    Explicit trade-off between two offers, for example "cheaper but 18 more days and medium confidence".
    """

    offer_id: str
    versus_offer_id: str
    summary: str


class Savings(BaseModel):
    vs_list_price: NullableMoney | None
    vs_market_median: NullableMoney | None
    vs_last_price: NullableMoney | None = None
    yearly_category: NullableMoney | None = None


class NegotiationDraftSource(StrEnum):
    """
    `llm` is a draft from the `negotiator` role; `template` is the deterministic playbook text,
    used when no draft passed the guardrails.
    """

    llm = "llm"
    template = "template"


class NegotiationDraftRef(BaseModel):
    draft_id: Annotated[
        str, Field(description="Id of the `pending_draft` being approved or rejected.")
    ]


class NegotiationHumanMessage(BaseModel):
    content: Annotated[
        str,
        Field(
            description="Text to send, as written. It must respect the negotiation's configured message length\nlimit; a longer message is rejected rather than truncated.",
            min_length=1,
        ),
    ]


class TargetLanguage(StrEnum):
    es = "es"
    en = "en"
    zh = "zh"
    he = "he"


class NegotiationMessageTranslateRequest(BaseModel):
    target_language: TargetLanguage


class NegotiationMessageTranslation(BaseModel):
    message_id: str
    target_language: TargetLanguage
    text: Annotated[
        str,
        Field(
            description="Translation of the message; the original stays untouched in the transcript."
        ),
    ]


class NegotiationControlRequest(BaseModel):
    reason: Annotated[str | None, Field(max_length=500)] = None


class WeeklySavings(BaseModel):
    week_start: date_aliased
    saved: Money


class GateAssignee(StrEnum):
    owner = "owner"
    finance = "finance"
    none = "none"


class DealAction(StrEnum):
    follow = "follow"
    renegotiate = "renegotiate"
    takeover = "takeover"
    hold = "hold"
    discard = "discard"


class DiscardReasonCode(StrEnum):
    """
    Closed reason codes required by discard, plus a comment (spec 3.8, D4-11).
    """

    price_too_high = "price_too_high"
    seller_not_trusted = "seller_not_trusted"
    spec_mismatch = "spec_mismatch"
    lead_time = "lead_time"
    out_of_budget = "out_of_budget"
    duplicate = "duplicate"
    other = "other"


class DealActionRequest(BaseModel):
    action: DealAction
    discard_reason: Annotated[
        DiscardReasonCode | None,
        Field(description="Required when action is discard, together with `comment`."),
    ] = None
    comment: Annotated[str | None, Field(max_length=2000)] = None
    instructions: Annotated[
        str | None,
        Field(description="Free instructions for renegotiate.", max_length=4000),
    ] = None
    hold_until: Annotated[AwareDatetime | None, Field(description="Review date for hold.")] = None


class GateReason(StrEnum):
    """
    Causes that send an offer to the human gate (spec 3.8, D4-11).
    """

    price_atypical = "price_atypical"
    price_insufficient_reference = "price_insufficient_reference"
    seller_low = "seller_low"
    seller_insufficient_data = "seller_insufficient_data"
    out_of_budget = "out_of_budget"
    stretch_above_threshold = "stretch_above_threshold"
    negotiator_escalated = "negotiator_escalated"
    financials_stale = "financials_stale"
    fx_provisional = "fx_provisional"
    dual_control_pending = "dual_control_pending"


class GateStatus(StrEnum):
    open = "open"
    resolved = "resolved"


class ApprovalInboxStatus(StrEnum):
    """
    `sign` waits for signatures, `progress` is fully signed, `closed` was rejected or expired.
    """

    sign = "sign"
    progress = "progress"
    closed = "closed"


class ApprovalDocumentKind(StrEnum):
    rfq = "rfq"
    po = "po"
    certificate = "certificate"


class ApprovalFinanceNotice(BaseModel):
    approval_id: str
    notified_at: AwareDatetime


class ApprovalDocument(BaseModel):
    kind: ApprovalDocumentKind
    sha256: str | None = None
    available: bool


class Event(StrEnum):
    signed = "signed"
    po_sent = "po_sent"
    confirmed = "confirmed"
    transit = "transit"


class ApprovalTrackingEvent(BaseModel):
    at: AwareDatetime
    event: Event


class Score(BaseModel):
    """
    Score of one offer for one profile and configuration.
    """

    offer_id: str
    profile_id: str
    value: Annotated[float, Field(ge=0.0, le=1.0)]
    config_version: str
    model_version: str
    computed_at: AwareDatetime


class OpenSigningSessionRequest(BaseModel):
    """
    The bearer token must come from a Keycloak step-up (ACR plus recent `auth_time`). `auth_at` is taken from `auth_time`.
    """

    key_id: str
    device_fingerprint_ref: str


class CreateDecisionRequest(BaseModel):
    type: DecisionType
    subject_ref: str
    params: Annotated[
        dict[str, Any],
        Field(
            description="Inputs of the payload builder for this type. The server builds the canonical payload."
        ),
    ]


class SignDecisionRequest(BaseModel):
    key_id: str
    payload_hash: Annotated[str, Field(pattern="^[a-f0-9]{64}$")]
    signature: Annotated[
        str,
        Field(description="Base64 Ed25519 signature over the canonical payload bytes."),
    ]
    signing_session_id: str
    device_fingerprint_ref: Annotated[
        str, Field(description="Must match the device that opened the signing session.")
    ]
    client_attestation: str | None = None


class RegisterSigningKeyRequest(BaseModel):
    public_key: str
    alg: Literal["Ed25519"]
    label: Annotated[str | None, Field(max_length=100)] = None
    signing_session_id: str | None = None


class RevokeSigningKeyRequest(BaseModel):
    decision_id: Annotated[
        str,
        Field(description="Signed decision of type revoke_key. Needs immediate reauth."),
    ]


class ChainVerification(BaseModel):
    valid: bool
    checked_events: Annotated[int, Field(ge=-9223372036854775808, le=9223372036854775807)]
    head_hash: str | None = None
    first_broken_seq: Annotated[
        int | None, Field(ge=-9223372036854775808, le=9223372036854775807)
    ] = None
    anchored_head_hash: Annotated[
        str | None,
        Field(description="Head hash stored in S3 Object Lock (compliance mode)."),
    ] = None
    anchored_at: AwareDatetime | None = None
    verified_at: AwareDatetime


class ScoringWeightsConfig(BaseModel):
    """
    Versioned and signed MCDA weights (spec 5.10.2).
    """

    id: str
    config_version: str
    profile_id: str | None = None
    weights: dict[str, WeightsAdditionalProperty]
    decision_id: str
    created_at: AwareDatetime


class PlatformWebhookEvent(BaseModel):
    event_type: str
    platform_ref: str
    occurred_at: AwareDatetime
    data: dict[str, Any] | None = None


class OnboardingStatus(StrEnum):
    profiling = "profiling"
    financials_pending = "financials_pending"
    financials_imported = "financials_imported"
    active = "active"
    completed = "completed"


class FinancialImportStatus(StrEnum):
    draft = "draft"
    active = "active"
    superseded = "superseded"
    rejected = "rejected"


class RowRejectionReason(StrEnum):
    unknown_metric = "unknown_metric"
    malformed_period = "malformed_period"
    non_integer_amount = "non_integer_amount"
    unsupported_currency = "unsupported_currency"
    duplicate_period_metric = "duplicate_period_metric"
    missing_required_field = "missing_required_field"
    note_too_long = "note_too_long"


class PurchaseFrequency(StrEnum):
    one_off = "one_off"
    monthly = "monthly"
    quarterly = "quarterly"
    yearly = "yearly"


class ConnectedAccountStatus(StrEnum):
    active = "active"
    session_invalidated = "session_invalidated"
    reauth_required = "reauth_required"
    disabled = "disabled"


class AggressivenessLevel(StrEnum):
    conservative = "conservative"
    balanced = "balanced"
    aggressive = "aggressive"


class NegotiationTone(StrEnum):
    formal = "formal"
    friendly = "friendly"


class Language(StrEnum):
    es = "es"
    en = "en"
    zh = "zh"


class CounterpartType(StrEnum):
    """
    Counterparts the negotiator may offer (neg.allowed_counterparts). Phase 1 allows only higher_volume and framework_contract (ADR-900 Q15).
    """

    higher_volume = "higher_volume"
    framework_contract = "framework_contract"
    prepayment = "prepayment"
    payment_terms = "payment_terms"
    guarantee = "guarantee"
    penalty = "penalty"


class SellerBand(StrEnum):
    high = "high"
    medium = "medium"


class SellerConfigBand(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class OnInsufficientReference(RootModel[Literal["gate"]]):
    root: Annotated[Literal["gate"], Field(description="Single value since ADR-900 Q12.")]


class MissionEventType(StrEnum):
    state_changed = "state_changed"
    offer_discovered = "offer_discovered"
    offer_enriched = "offer_enriched"
    sanity_checked = "sanity_checked"
    trust_scored = "trust_scored"
    financially_checked = "financially_checked"
    gate_opened = "gate_opened"
    negotiation_message = "negotiation_message"
    negotiation_state_changed = "negotiation_state_changed"
    recommendation_ready = "recommendation_ready"
    budget_warning = "budget_warning"
    error = "error"
    keepalive = "keepalive"


class SourcingRequestStatus(StrEnum):
    normalized = "normalized"
    needs_clarification = "needs_clarification"


class QuantityPriority(StrEnum):
    primary = "primary"
    secondary = "secondary"
    fallback = "fallback"


class ReviewAnomalyType(StrEnum):
    burst_velocity = "burst_velocity"
    five_star_anomaly = "five_star_anomaly"
    low_verified_share = "low_verified_share"
    duplicate_text = "duplicate_text"
    creation_correlation = "creation_correlation"


class ReviewAnomalySeverity(StrEnum):
    warning = "warning"
    critical = "critical"


class ScoreCriterion(StrEnum):
    landed_cost = "landed_cost"
    lead_time = "lead_time"
    seller_confidence = "seller_confidence"
    financial_fit = "financial_fit"
    margin_potential = "margin_potential"
    spec_match = "spec_match"
    compliance_risk = "compliance_risk"
    negotiation_gain = "negotiation_gain"


class NegotiationState(StrEnum):
    queued = "queued"
    running = "running"
    awaiting_approval = "awaiting_approval"
    human_control = "human_control"
    paused = "paused"
    completed = "completed"
    aborted = "aborted"
    escalated = "escalated"


class GuardrailCode(StrEnum):
    max_discount_exceeded = "max_discount_exceeded"
    unauthorized_concession = "unauthorized_concession"
    max_rounds = "max_rounds"
    token_budget = "token_budget"
    message_rate = "message_rate"
    sensitive_data_request = "sensitive_data_request"
    off_platform_payment = "off_platform_payment"
    anomalous_price = "anomalous_price"
    binding_commitment_attempt = "binding_commitment_attempt"
    unsupported_currency = "unsupported_currency"


class MessageRole(StrEnum):
    agent = "agent"
    seller = "seller"
    human = "human"


class DealState(StrEnum):
    open = "open"
    renegotiating = "renegotiating"
    on_hold = "on_hold"
    human_control = "human_control"
    followed = "followed"
    discarded = "discarded"
    purchased = "purchased"


class LandedCostCode(StrEnum):
    goods = "goods"
    shipping = "shipping"
    insurance = "insurance"
    duties = "duties"
    import_vat = "import_vat"
    capital_cost = "capital_cost"
    payment_fees = "payment_fees"
    fx_conversion = "fx_conversion"
    fx_risk = "fx_risk"


class ApprovalDecision(StrEnum):
    approve = "approve"
    reject = "reject"


class AuthMethod(RootModel[Literal["keycloak_step_up"]]):
    root: Annotated[
        Literal["keycloak_step_up"],
        Field(description="Strong authentication that opened the session (ADR-900 Q11)."),
    ]


class SigningSessionStatus(StrEnum):
    active = "active"
    expired = "expired"
    revoked = "revoked"
    exhausted = "exhausted"
    closed = "closed"


class SigningKeyOwnerType(StrEnum):
    human = "human"
    service = "service"


class ActorType(StrEnum):
    human = "human"
    service = "service"
    agent = "agent"


class LlmRole(StrEnum):
    planner = "planner"
    negotiator = "negotiator"
    extractor = "extractor"
    narrator = "narrator"
    embedder = "embedder"


class ExcludedOffer(BaseModel):
    offer_id: str
    reasons: list[str]


class PlannedQuery(BaseModel):
    platform: str
    query: str
    filters: dict[str, Any] | None = None


class PriceExplanation(BaseModel):
    code: PriceExplanationCode
    detail: str | None = None


class VerificationCheck(BaseModel):
    name: str
    ok: bool
    detail: str | None = None


class Concession(BaseModel):
    type: CounterpartType
    detail: str | None = None


class DecisionAccepted(BaseModel):
    """
    A decision was created and waits for its signature. Nothing has changed yet.
    """

    decision_id: str
    status: DecisionStatus


class BlockedAction(BaseModel):
    """
    One action that cannot run, with a closed reason the UI translates (criterion 16).
    """

    action: str
    reason: BlockReasonCode
    detail: str


class GateResolution(StrEnum):
    unblocked = "unblocked"
    discarded = "discarded"
    overridden = "overridden"
    held = "held"
    followed = "followed"


class GateQueueAction(StrEnum):
    """
    `unblock` lets a held offer proceed. `override_discard` reverses a discard (finance, admin, owner).
    """

    unblock = "unblock"
    override_discard = "override_discard"


class GateQueueActionRequest(BaseModel):
    action: GateQueueAction
    comment: Annotated[str | None, Field(max_length=2000)] = None


class CompanyProfilePatch(BaseModel):
    """
    Any subset of CompanyProfile fields. Omitted fields keep their value.
    """

    legal_name: str | None = None
    tax_id: Annotated[str | None, Field(description="CIF or VAT number.")] = None
    country: Annotated[str | None, Field(pattern="^[A-Z]{2}$")] = None
    shipping_address: str | None = None
    billing_address: str | None = None
    customs_regime: str | None = None
    cnae: str | None = None
    purchase_categories: list[str] | None = None
    purchase_frequency: PurchaseFrequency | None = None
    seasonality: str | None = None
    base_currency: Currency | None = None
    sector: str | None = None
    budget: Annotated[NullableMoney | None, Field(description="Overall purchasing budget.")] = None


class UpdateOnboardingSessionRequest(BaseModel):
    """
    Partial profile update from the progressive form.
    """

    company_profile: CompanyProfilePatch


class ConfigLayer(StrEnum):
    global_ = "global"
    tenant = "tenant"
    category = "category"


class ConfigValueStatus(StrEnum):
    """
    `unset` is "sin definir" (spec 7).
    """

    set = "set"
    unset = "unset"


class EffectiveConfigValue(BaseModel):
    value: Annotated[
        Any,
        Field(
            description="Resolved value. Null when unset. Money is {amount_minor, currency}; rates are decimal strings or numbers."
        ),
    ]
    status: ConfigValueStatus
    layer: ConfigLayer


class ConfigChangeRequest(BaseModel):
    base_config_version: Annotated[int, Field(ge=1)]
    category: str | None = None
    patch: Annotated[
        dict[str, Any],
        Field(description="Deep-merge patch. Explicit null unsets a key."),
    ]
    reason: Annotated[
        str | None,
        Field(
            description="Why the change is made. Part of the signed payload and shown in the version history.",
            max_length=500,
        ),
    ] = None


class BlockReason(BaseModel):
    """
    Why an action is blocked. The UI shows `message` next to the disabled control.
    """

    code: BlockReasonCode
    message: str


class Conflict(Problem):
    reason: Annotated[
        str | None, Field(description="Closed machine-readable reason of the conflict.")
    ] = None
    blocked: list[BlockedAction] | None = None


class ReauthRequired(Problem):
    """
    Returned with 428 when the signing session is missing, expired, revoked or exhausted.
    """

    error: Literal["reauth_required"]
    reason: ReauthReason


class Actor(BaseModel):
    type: ActorType
    id: str


class CompanyProfile(BaseModel):
    """
    Fiscal identity, sector and activity (spec 3.1).
    """

    legal_name: str
    tax_id: Annotated[str, Field(description="CIF or VAT number.")]
    country: Annotated[str, Field(pattern="^[A-Z]{2}$")]
    shipping_address: str | None = None
    billing_address: str | None = None
    customs_regime: str | None = None
    cnae: str | None = None
    purchase_categories: list[str] | None = None
    purchase_frequency: PurchaseFrequency | None = None
    seasonality: str | None = None
    base_currency: Currency
    sector: str | None = None
    budget: Annotated[NullableMoney | None, Field(description="Overall purchasing budget.")] = None


class CreateOnboardingSessionRequest(BaseModel):
    company_profile: CompanyProfile | None = None
    base_currency: Currency


class RowRejection(BaseModel):
    row: Annotated[int, Field(ge=1)]
    field: str | None = None
    reason_code: RowRejectionReason
    message: str


class DerivedFinancials(BaseModel):
    envelopes: list[BudgetEnvelope]
    net_buying_capacity: Money
    buying_power_score: Annotated[
        int | None,
        Field(
            description="Null until the BuyingPowerScore formula is decided by the TL (question Q2)."
        ),
    ]


class ConnectedAccount(BaseModel):
    """
    Marketplace account. Credentials are never returned; only an opaque CredentialRef.
    """

    id: str
    platform: str
    status: ConnectedAccountStatus
    credential_ref: CredentialRef


class NegotiationParams(BaseModel):
    target_discount_bp: Annotated[
        int | None,
        Field(description='Basis points. Null until the tenant sets it (spec 7, "sin definir").'),
    ] = None
    max_discount_bp: Annotated[
        int | None,
        Field(description='Basis points. Null until the tenant sets it (spec 7, "sin definir").'),
    ] = None
    aggressiveness: AggressivenessLevel
    tone: NegotiationTone
    language: Language
    accepts_counterparts: list[CounterpartType]


class HardConstraints(BaseModel):
    banned_platforms: list[str]
    banned_countries: list[str]
    required_certifications: list[str]
    min_accepted_seller_band: SellerBand
    max_lead_time_days: int | None = None
    approval_threshold: NullableMoney | None = None


class EffectiveConfig(BaseModel):
    """
    Effective tenant configuration (global, then tenant, then category override) with provenance (ADR-400).
    Keys are dotted paths (`sanity.z_gate`). Unset values are null, never invented defaults.

    """

    tenant_id: str
    category: str | None
    config_version: Annotated[int, Field(description="Monotonic per tenant (ADR-400).", ge=1)]
    content_hash: Annotated[str, Field(pattern="^sha256:[0-9a-f]{64}$")]
    resolved_at: AwareDatetime
    values: dict[str, EffectiveConfigValue]


class SanityConfig(BaseModel):
    """
    Price sanity thresholds (spec 3.3.3, 7). Null means unset.
    """

    min_sample: int | None
    z_ok: float | None
    z_gate: float | None
    low_side_factor: float | None
    max_relative_rise: float | None
    max_relative_drop: float | None
    floor_per_unit: NullableMoney | None
    ceiling_per_unit: NullableMoney | None
    on_insufficient_reference: OnInsufficientReference | None


class SellerConfig(BaseModel):
    """
    Seller confidence thresholds and parameters (spec 3.4, 7). Null means unset.
    """

    rating_prior_weight: float | None
    age_saturation_days: int | None
    min_signals: int | None
    band_high: int | None
    band_medium: int | None
    band_low: int | None
    hard_block_below: int | None
    min_accepted_band: SellerConfigBand | None
    review_burst_z: float | None
    max_dispute_rate: float | None
    snapshot_max_age_days: int | None
    escalate_cheap_low_confidence: bool | None
    weights: Annotated[
        dict[str, Any] | None,
        Field(description="Signal-group weights as decimal strings summing to 1 (ADR-304)."),
    ] = None
    x_sat: Annotated[
        dict[str, Any] | None,
        Field(description="Saturation point per countable signal, decimal strings (ADR-304)."),
    ] = None
    category_rating_mean: Annotated[str | None, Field(pattern="^[0-9]+(\\.[0-9]+)?$")] = None
    category_five_star_share: Annotated[str | None, Field(pattern="^[0-9]+(\\.[0-9]+)?$")] = None
    wilson_confidence: Annotated[str | None, Field(pattern="^[0-9]+(\\.[0-9]+)?$")] = None
    min_verified_share: Annotated[str | None, Field(pattern="^[0-9]+(\\.[0-9]+)?$")] = None
    max_duplicate_text_share: Annotated[str | None, Field(pattern="^[0-9]+(\\.[0-9]+)?$")] = None


class QuantityTier(BaseModel):
    quantity: Annotated[int, Field(ge=1)]
    priority: QuantityPriority


class SourcingItem(BaseModel):
    id: str
    request_id: str
    spec: SourcingSpec
    quantity_tiers: list[QuantityTier]


class SourcingPlan(BaseModel):
    id: str
    request_id: str
    platforms: list[str]
    queries: list[PlannedQuery]
    created_at: AwareDatetime


class MissionEvent(BaseModel):
    """
    Payload of one SSE message. The SSE `event` field equals `type`.
    """

    id: str
    mission_id: str
    type: MissionEventType
    at: AwareDatetime
    data: dict[str, Any] | None = None


class ReviewAnomaly(BaseModel):
    seller_id: str
    type: ReviewAnomalyType
    severity: ReviewAnomalySeverity
    evidence: dict[str, Any]
    detected_at: AwareDatetime


class SellerConfidence(BaseModel):
    """
    Deterministic, versioned seller confidence (spec 3.4). Never produced by an LLM.
    """

    seller_id: str
    score: Annotated[
        int | None,
        Field(description="Null when band is insufficient_data.", ge=0, le=100),
    ]
    band: SellerConfidenceBand
    signals_normalized: Annotated[
        dict[str, float],
        Field(description="Normalized signals in [0, 1], keyed by signal name."),
    ]
    penalties: list[str]
    flags: list[ReviewAnomaly]
    model_version: str
    snapshot_id: str | None = None
    computed_at: AwareDatetime


class SellerConfidenceView(BaseModel):
    seller: Seller
    current: SellerConfidence
    history: list[SellerConfidence]
    next_cursor: str | None


class PriceSanityCheck(BaseModel):
    """
    Persisted for every offer and included in signed payloads (spec 3.3.4).
    """

    offer_id: str
    reference_price_eur: Money
    median: Money
    dispersion_measure: DispersionMeasure
    dispersion_value: float
    sample_size: Annotated[int, Field(ge=0)]
    band_lower: Annotated[
        Money | None,
        Field(
            description="Lower limit of the normal price band, so a chart can draw it. Null when there is no reference."
        ),
    ] = None
    band_upper: Money | None = None
    index_score: float | None = None
    relative_deviation: Annotated[
        float,
        Field(
            description="Ratio against the reference centre, not a percentage. -0.04 is 4% below the median."
        ),
    ]
    band: PriceSanityBand
    decision: SanityDecision
    explanations: list[PriceExplanation]
    config_version: str
    checked_at: AwareDatetime


class LandedCostLine(BaseModel):
    code: LandedCostCode
    amount: Money
    source: Annotated[
        str | None,
        Field(description="Identifier of the input that produced the line (duty table, rate id)."),
    ] = None


class ScoreBreakdown(BaseModel):
    """
    Contribution of one criterion to the score (spec 3.7, 6).
    """

    criterion: ScoreCriterion
    weight: Annotated[float, Field(ge=0.0, le=1.0)]
    normalized_value: Annotated[float, Field(ge=0.0, le=1.0)]
    contribution: float
    penalty: Annotated[float | None, Field(ge=0.0)] = None


class NegotiationDraft(BaseModel):
    """
    Message the agent wrote but did not send: Phase 1 sends nothing without a human approval
    (spec 3.6 step 5). `text` is the exact text that will be sent, so the approver sees no surprise.
    """

    id: str
    text: str
    source: NegotiationDraftSource
    created_at: AwareDatetime


class GuardrailHit(BaseModel):
    code: GuardrailCode
    at: AwareDatetime
    detail: str | None = None


class NegotiationMessage(BaseModel):
    id: str
    negotiation_id: str
    role: MessageRole
    content: str
    at: AwareDatetime
    seq: Annotated[
        int | None,
        Field(
            description="Monotonic position in the conversation. The transcript is ordered by it.",
            ge=0,
        ),
    ] = None
    approved_by: Annotated[
        str | None,
        Field(
            description="Principal that approved an agent message in semi-automatic mode. Null otherwise."
        ),
    ] = None
    screenshot_ref: str | None = None
    redactions: Annotated[int | None, Field(ge=0)] = None


class NegotiationOutcome(BaseModel):
    """
    Result of a negotiation (spec 3.6).
    """

    negotiation_id: str
    offer_id: str
    initial_price: Money
    final_price: Money
    discount_bp: Annotated[int, Field(description="Discount in basis points (1500 = 15,00%).")]
    concessions: list[Concession]
    terms: list[str]
    seller_confidence: SellerConfidence
    transcript_ref: Annotated[
        str,
        Field(description="Opaque S3 reference to the full transcript and screenshots."),
    ]


class DashboardSummary(BaseModel):
    pending_count: Annotated[int, Field(ge=0)]
    signed_count: Annotated[int, Field(ge=0)]
    nearest_sla_due_at: AwareDatetime | None
    savings_by_week: list[WeeklySavings]


class ActionAvailability(BaseModel):
    action: DealAction
    allowed: bool
    blocked_by: list[BlockReason]


class GateQueueItem(BaseModel):
    id: str
    mission_id: str
    offer_id: str
    causes: Annotated[list[GateReason], Field(min_length=1)]
    created_at: AwareDatetime
    sla_due_at: AwareDatetime
    sla_elapsed_ratio: Annotated[
        float | None,
        Field(
            description="Share of the SLA already used (1.0 = due now, above 1 = overdue). Computed by the server.",
            ge=0.0,
        ),
    ] = None
    assignee: GateAssignee | None = None
    assigned_to_me: bool | None = None
    reminder_sent_at: AwareDatetime | None = None
    status: GateStatus
    resolution: GateResolution | None
    decision_id: str | None


class GateQueuePage(BaseModel):
    items: list[GateQueueItem]
    next_cursor: str | None


class Approval(BaseModel):
    id: str
    decision_id: str
    requested_by: Actor
    approver: Actor | None = None
    decision: ApprovalDecision | None
    comment: str | None = None
    created_at: AwareDatetime


class SigningSession(BaseModel):
    """
    Fixed signing window opened by a strong authentication. `expires_at` never moves with signatures
    (spec 5.10.4). `server_time` lets the UI correct its clock offset before showing mm:ss.

    """

    id: str
    user_id: str
    key_id: str
    auth_method: AuthMethod
    auth_at: AwareDatetime
    expires_at: AwareDatetime
    device_fingerprint_ref: str
    decisions_signed: list[str]
    max_decisions: Annotated[int, Field(ge=1)]
    remaining_decisions: Annotated[int, Field(ge=0)]
    status: SigningSessionStatus
    revoked_reason: ReauthReason | None = None
    server_time: AwareDatetime


class Signature(BaseModel):
    """
    Signature record. Each record includes the hash of the previous one (hash chain, spec 5.10.2).
    """

    id: str | None = None
    decision_id: str
    signer_type: ActorType
    signer_id: str
    key_id: str
    alg: Literal["Ed25519"]
    payload_hash: str
    signature: str
    signed_at: AwareDatetime
    signing_session_id: Annotated[
        str | None,
        Field(description="Set for human signers. Service signatures have no signing session."),
    ] = None
    auth_at: AwareDatetime | None = None
    prev_signature_hash: str | None = None
    chain_hash: Annotated[
        str, Field(description="Hash of this record including prev_signature_hash.")
    ]
    client_attestation: str | None = None


class VerificationResult(BaseModel):
    decision_id: str
    valid: bool
    checks: list[VerificationCheck]
    verified_at: AwareDatetime


class SigningKey(BaseModel):
    """
    Public key only. Versioned, so revocation never invalidates past signatures.
    """

    id: str
    owner_id: str
    owner_type: SigningKeyOwnerType
    public_key: Annotated[str, Field(description="Base64 raw Ed25519 public key (32 bytes).")]
    alg: Literal["Ed25519"]
    label: str | None = None
    created_at: AwareDatetime
    rotated_at: AwareDatetime | None = None
    revoked_at: AwareDatetime | None = None


class SigningKeyList(BaseModel):
    items: list[SigningKey]


class AuditEvent(BaseModel):
    """
    Append-only, hash-chained (spec 5.9, 5.10).
    """

    id: str
    seq: Annotated[int, Field(ge=1, le=9223372036854775807)]
    actor: Actor
    event_type: str
    subject_ref: str
    payload_hash: str
    prev_hash: str
    hash: str
    created_at: AwareDatetime


class AuditEventPage(BaseModel):
    items: list[AuditEvent]
    next_cursor: str | None


class PricingThresholdConfig(BaseModel):
    """
    Versioned and signed (spec 6, 7). Changing it is a signed decision with immediate reauth.
    """

    id: str
    config_version: str
    category: str | None = None
    sanity: SanityConfig
    decision_id: str
    created_at: AwareDatetime


class ConfidenceModelConfig(BaseModel):
    """
    Versioned and signed seller confidence model (spec 6, 3.4.3).
    """

    id: str
    config_version: str
    model_version: str
    category: str | None = None
    seller: SellerConfig
    weights: Annotated[
        dict[str, WeightsAdditionalProperty] | None,
        Field(description="Weight per signal group (age, sales, catalog, reviews, institutional)."),
    ] = None
    decision_id: str
    created_at: AwareDatetime


class LLMEvent(BaseModel):
    """
    Accounting entry per LLM call (spec 5.6). Contains no prompt text and no secrets.
    """

    id: str
    mission_id: str | None = None
    role: LlmRole
    endpoint: str
    model: str
    prompt_version: str
    tokens_in: Annotated[int, Field(ge=0)]
    tokens_out: Annotated[int, Field(ge=0)]
    latency_ms: Annotated[int, Field(ge=0)]
    repaired_json: bool | None = None
    cost: NullableMoney | None = None
    created_at: AwareDatetime


class OnboardingSession(BaseModel):
    id: str
    status: OnboardingStatus
    company_profile: CompanyProfile
    active_financial_snapshot_id: str | None = None
    effective_config: EffectiveConfig
    steps: Annotated[
        list[OnboardingStepProgress] | None,
        Field(
            description="Per-step completion computed by the server from what it holds. Steps the server cannot evaluate (their data is tenant configuration, saved through signed decisions) are absent."
        ),
    ] = None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class OnboardingSessionList(BaseModel):
    items: list[OnboardingSession]


class ImportReport(BaseModel):
    rows_ok: Annotated[int, Field(ge=0)]
    rows_rejected: Annotated[int, Field(ge=0)]
    rows_duplicated: Annotated[
        int | None,
        Field(
            description="Rows rejected as later duplicates (spec 3.1.1). Subset of rows_rejected.",
            ge=0,
        ),
    ] = None
    rows_converted: Annotated[
        int | None,
        Field(
            description="Rows whose amount was converted to the base currency (converted=true).",
            ge=0,
        ),
    ] = None
    rejections: list[RowRejection]
    warnings: Annotated[
        list[str],
        Field(
            description="Written by the LLM from the structured report only. Never contains numbers the code did not compute."
        ),
    ]
    projection_enabled: bool
    periods_loaded: Annotated[int, Field(ge=0)]
    reference_date: date_aliased
    derived: DerivedFinancials


class UserProfilePreference(BaseModel):
    """
    A profile is weights plus hard constraints, not a UI role (spec 2).
    """

    id: str
    name: str
    weights: Annotated[
        dict[str, WeightsAdditionalProperty],
        Field(description="Weight per MCDA criterion, in [0, 1]."),
    ]
    negotiation: NegotiationParams
    hard_constraints: HardConstraints


class SourcingRequest(BaseModel):
    id: str
    status: SourcingRequestStatus
    spec: SourcingSpec
    quantity_tiers: list[QuantityTier]
    max_budget: NullableMoney | None = None
    target_delivery_date: date_aliased | None = None
    delivery_country: str
    needs_clarification: list[str]
    created_at: AwareDatetime


class ProfileList(BaseModel):
    items: list[UserProfilePreference]


class LandedCostBreakdown(BaseModel):
    """
    Line by line. The lines add up exactly to `total` in minor units (criterion 4).
    """

    unit_price: Money
    quantity: Annotated[int, Field(ge=1)]
    lines: list[LandedCostLine]
    total: Money
    unit_landed_cost: Money


class FinancialFit(BaseModel):
    offer_id: str
    landed_cost: LandedCostBreakdown
    verdict: FinancialVerdict
    reasons: Annotated[
        list[str],
        Field(
            description='Numeric reasons, for example "landed cost 1.234,56 EUR exceeds envelope by 4,2%".'
        ),
    ]
    budget_utilization_bp: int | None = None
    treasury_impact: Money | None = None
    financials_stale: bool
    computed_at: AwareDatetime


class RankedOffer(BaseModel):
    rank: Annotated[int, Field(ge=1)]
    offer_id: str
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    breakdown: list[ScoreBreakdown]
    narrative: Annotated[
        str | None, Field(description="LLM text built from the numbers above.")
    ] = None


class Negotiation(BaseModel):
    id: str
    offer_id: str
    strategy: str
    state: NegotiationState
    rounds: Annotated[int, Field(ge=0)]
    max_rounds: int | None
    guardrail_hits: list[GuardrailHit]
    pending_draft: Annotated[
        NegotiationDraft | None,
        Field(
            description="Draft waiting for a human. Present when `state` is `awaiting_approval`."
        ),
    ] = None
    mission_id: Annotated[
        str | None,
        Field(
            description="Mission that opened this negotiation. Lets the orchestrator route new messages and\nstate changes onto that mission's SSE stream instead of polling."
        ),
    ] = None
    trace_id: Annotated[
        str | None,
        Field(
            description="Trace identifier of the request that opened the negotiation, propagated from the mission."
        ),
    ] = None


class NegotiationMessagePage(BaseModel):
    items: list[NegotiationMessage]
    next_cursor: str | None


class ApprovalView(BaseModel):
    """
    Inbox view of an approval decision. Amount and seller come from the signed payload.
    """

    id: Annotated[str, Field(description="The decision id.")]
    status: ApprovalInboxStatus
    subject_ref: str
    amount: NullableMoney | None = None
    seller_ref: str | None = None
    required_signers: Annotated[int, Field(ge=1, le=2)]
    signatures: list[Signature]
    documents: list[ApprovalDocument]
    tracking: list[ApprovalTrackingEvent]
    created_at: AwareDatetime


class ApprovalViewPage(BaseModel):
    items: list[ApprovalView]
    next_cursor: str | None


class Decision(BaseModel):
    id: str
    type: DecisionType
    subject_ref: str
    status: DecisionStatus
    payload_canonical: Annotated[
        str,
        Field(description="RFC 8785 (JCS) canonical JSON, UTF-8. These are the bytes to sign."),
    ]
    payload_hash: Annotated[
        str,
        Field(description="SHA-256 of payload_canonical, hex.", pattern="^[a-f0-9]{64}$"),
    ]
    requires_immediate_reauth: bool
    required_signers: Annotated[
        int,
        Field(
            description="2 when the amount is above approval.dual_control_above (spec 5.10.2).",
            ge=1,
            le=2,
        ),
    ]
    signatures: list[Signature]
    decided_by: Actor | None = None
    created_at: AwareDatetime
    signed_at: AwareDatetime | None = None


class IntakeTurn(BaseModel):
    messages: Annotated[
        list[IntakeMessage],
        Field(description="The user message followed by the agent reply."),
    ]
    session: OnboardingSession


class FinancialImport(BaseModel):
    """
    Result of a CSV import. Status `draft` until a signed activation.
    """

    id: str
    onboarding_id: str
    status: FinancialImportStatus
    csv_ref: Annotated[str, Field(description="Opaque S3 reference to the original file.")]
    report: ImportReport
    created_at: AwareDatetime


class Offer(BaseModel):
    """
    Normalized offer with enrichment. Spec 3.2 and 6.
    """

    id: str
    mission_id: str
    platform: str
    platform_offer_id: str
    product_url: AnyUrl | None = None
    product_key: str
    title: str
    specifications: dict[str, str] | None = None
    certifications: list[str] | None = None
    seller_id: str
    seller_name: str
    seller_country: str | None = None
    unit_price: ConvertedMoney
    moq: Annotated[int, Field(ge=1)]
    price_tiers: list[PriceTier] | None = None
    shipping: ShippingEstimate | None = None
    incoterm: Incoterm | None = None
    lead_time_days: Annotated[int | None, Field(ge=0)] = None
    payment_terms_days: Annotated[
        int | None,
        Field(
            description="Payment term the seller offers (0 = prepayment). Null when unknown.",
            ge=0,
        ),
    ] = None
    signature_status: SignatureStatus | None = None
    state: OfferState
    seller_confidence: SellerConfidence | None = None
    price_sanity_check: PriceSanityCheck | None = None
    financial_fit: FinancialFit | None = None
    discovered_at: AwareDatetime
    expires_at: AwareDatetime | None = None


class OfferPage(BaseModel):
    total_count: Annotated[
        int | None,
        Field(
            description="Offers matching the filters across all pages, when known.",
            ge=0,
        ),
    ] = None
    items: list[Offer]
    next_cursor: str | None


class Recommendation(BaseModel):
    """
    Explainable ranking. The ranking comes from code; the narrative comes from the LLM (spec 3.7).
    """

    mission_id: str
    profile_id: str
    ranking: list[RankedOffer]
    excluded: Annotated[
        list[ExcludedOffer],
        Field(description="Offers removed by hard constraints, each with visible reasons."),
    ]
    alternatives: list[TradeOff] | None = None
    savings: Savings
    config_version: str
    model_version: str
    generated_at: AwareDatetime


class Deal(BaseModel):
    """
    Final deal shown on the dashboard. Shows the seller confidence next to the price (spec 3.8).
    """

    id: str
    mission_id: str
    offer: Offer
    state: DealState
    price_band: PriceSanityBand
    confidence_band: SellerConfidenceBand
    financial_verdict: FinancialVerdict
    signature_status: SignatureStatus
    flags: list[str] | None = None
    negotiation: Negotiation | None = None
    outcome: NegotiationOutcome | None = None
    recommendation_rank: int | None = None
    actions: list[ActionAvailability]
    updated_at: AwareDatetime


class DealPage(BaseModel):
    items: list[Deal]
    next_cursor: str | None
