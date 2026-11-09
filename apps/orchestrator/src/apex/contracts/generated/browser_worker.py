# DO NOT EDIT. Generated from contracts/internal/browser-worker.openapi.yaml by contracts/scripts/generate.mjs.
# ruff: noqa: UP035, UP040

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AnyUrl, AwareDatetime, BaseModel, ConfigDict, Field, RootModel


class Currency(StrEnum):
    """
    Closed enum. Same as the public contract (spec 3.5.1).
    """

    EUR = "EUR"
    USD = "USD"
    CNY = "CNY"


class Money(BaseModel):
    """
    Amount in integer minor units (cents, fen). Never a float.
    """

    amount_minor: Annotated[int, Field(ge=0, le=9223372036854775807)]
    currency: Currency


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


class Transport(StrEnum):
    """
    How the adapter reads the platform (ADR-500). `browser` is used only for login and chat where possible.
    """

    http = "http"
    browser = "browser"


class WorkerErrorCode(StrEnum):
    """
    Closed error codes. The runbooks in docs/runbooks/ are keyed by these values.
    """

    validation_error = "validation_error"
    unauthorized = "unauthorized"
    unknown_job = "unknown_job"
    unknown_chat = "unknown_chat"
    unknown_platform = "unknown_platform"
    unknown_account = "unknown_account"
    unknown_seller = "unknown_seller"
    unknown_product = "unknown_product"
    platform_disabled = "platform_disabled"
    idempotency_conflict = "idempotency_conflict"
    chat_locked = "chat_locked"
    lock_held = "lock_held"
    not_lock_holder = "not_lock_holder"
    rate_limited = "rate_limited"
    session_invalid = "session_invalid"
    captcha = "captcha"
    dom_changed = "dom_changed"
    robots_disallowed = "robots_disallowed"
    upstream_error = "upstream_error"
    timeout = "timeout"
    internal = "internal"


class WorkerProblem(BaseModel):
    """
    RFC 9457 problem details with a closed `code`.
    """

    type: str
    title: str
    status: Annotated[int, Field(ge=400, le=599)]
    detail: str | None = None
    instance: str | None = None
    code: WorkerErrorCode
    retryable: bool | None = False
    retry_after_seconds: Annotated[int | None, Field(ge=0)] = None


class PlatformStatus(BaseModel):
    platform: str
    enabled: Annotated[bool, Field(description="Value of the `platform.<id>.enabled` flag.")]
    transport: Transport


class WorkerHealthStatus(StrEnum):
    ok = "ok"
    degraded = "degraded"


class JobKind(StrEnum):
    search = "search"
    product = "product"
    seller = "seller"
    seller_signals = "seller_signals"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    dead_lettered = "dead_lettered"


class SearchJobRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["search"]
    tenant_id: Annotated[str, Field(min_length=1)]
    mission_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    platform: Annotated[str, Field(min_length=1)]
    priority: Annotated[
        int | None, Field(description="BullMQ priority. 1 is the highest.", ge=1, le=10)
    ] = 5
    query: Annotated[str, Field(max_length=500, min_length=1)]
    quantity: Annotated[
        int | None,
        Field(
            description="Requested volume, used to read the matching price tier when the platform shows it.",
            ge=1,
        ),
    ] = None
    max_results: Annotated[int | None, Field(ge=1, le=200)] = 50


class ProductJobRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["product"]
    tenant_id: Annotated[str, Field(min_length=1)]
    mission_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    platform: Annotated[str, Field(min_length=1)]
    priority: Annotated[
        int | None, Field(description="BullMQ priority. 1 is the highest.", ge=1, le=10)
    ] = 5
    platform_offer_id: Annotated[str, Field(min_length=1)]


class SellerJobRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["seller"]
    tenant_id: Annotated[str, Field(min_length=1)]
    mission_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    platform: Annotated[str, Field(min_length=1)]
    priority: Annotated[
        int | None, Field(description="BullMQ priority. 1 is the highest.", ge=1, le=10)
    ] = 5
    platform_seller_id: Annotated[str, Field(min_length=1)]


class SellerSignalsJobRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    kind: Literal["seller_signals"]
    tenant_id: Annotated[str, Field(min_length=1)]
    mission_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    platform: Annotated[str, Field(min_length=1)]
    priority: Annotated[
        int | None, Field(description="BullMQ priority. 1 is the highest.", ge=1, le=10)
    ] = 5
    platform_seller_id: Annotated[str, Field(min_length=1)]
    max_reviews: Annotated[
        int | None,
        Field(
            description="How many of the most recent reviews to sample for manipulation checks.",
            ge=0,
            le=500,
        ),
    ] = 200


class JobRequest(
    RootModel[SearchJobRequest | ProductJobRequest | SellerJobRequest | SellerSignalsJobRequest]
):
    root: Annotated[
        SearchJobRequest | ProductJobRequest | SellerJobRequest | SellerSignalsJobRequest,
        Field(discriminator="kind"),
    ]


class JobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    deduplicated: Annotated[
        bool,
        Field(
            description="True when this Idempotency-Key was already accepted and the existing job is returned."
        ),
    ]


class RawOffer(BaseModel):
    """
    One listing as the platform shows it. No EUR conversion, no bands, no scores.
    """

    platform: str
    platform_offer_id: Annotated[str, Field(min_length=1)]
    product_id: Annotated[
        str,
        Field(
            description="Platform product id. Equal to `platform_offer_id` on platforms without separate listings.",
            min_length=1,
        ),
    ]
    platform_seller_id: Annotated[str, Field(min_length=1)]
    seller_name: str | None = None
    title: str
    product_url: AnyUrl | None = None
    unit_price: Money
    list_price: Money | None = None
    price_tiers: list[PriceTier]
    moq: Annotated[int, Field(ge=1)]
    quantity_available: Annotated[
        int | None,
        Field(
            description="Stock shown by the platform. Null when the platform does not show it.",
            ge=0,
        ),
    ] = None
    specifications: dict[str, str]
    certifications: list[str]
    seller_country: Annotated[
        str | None, Field(description="ISO 3166-1 alpha-2 when the platform shows it.")
    ] = None
    shipping: ShippingEstimate | None = None
    incoterm: Incoterm | None = None
    lead_time_days: Annotated[int | None, Field(ge=0)] = None
    captured_at: AwareDatetime


class SkipReason(StrEnum):
    unsupported_currency = "unsupported_currency"
    missing_price = "missing_price"
    parse_error = "parse_error"


class SkippedListing(BaseModel):
    """
    A listing found but not returned as an offer, with the reason.
    """

    platform_offer_id: str
    reason: SkipReason
    currency_raw: Annotated[
        str | None,
        Field(
            description="The currency code the platform showed, for `unsupported_currency`.",
            max_length=16,
        ),
    ] = None


class RawSeller(BaseModel):
    platform: str
    platform_seller_id: Annotated[str, Field(min_length=1)]
    display_name: str
    country: str | None = None
    profile_url: AnyUrl | None = None
    captured_at: AwareDatetime


class RawReview(BaseModel):
    """
    One review as shown. Used only for structural manipulation checks (spec 3.4.2).
    """

    rating: Annotated[int, Field(ge=1, le=5)]
    created_at: AwareDatetime | None = None
    verified_purchase: bool | None = None
    text: Annotated[str | None, Field(max_length=2000)] = None


class RawSellerSignals(BaseModel):
    """
    Raw seller signals as published by the platform (spec 3.4.1). A signal the platform does not publish is
    null, never 0. The orchestrator computes `data_completeness` and the confidence score.

    """

    platform: str
    platform_seller_id: Annotated[str, Field(min_length=1)]
    captured_at: AwareDatetime
    account_age_days: Annotated[int | None, Field(ge=0)] = None
    first_sale_date: date | None = None
    months_active_last_12: Annotated[int | None, Field(ge=0, le=12)] = None
    lifetime_transactions: Annotated[int | None, Field(ge=0)] = None
    transactions_12m: Annotated[int | None, Field(ge=0)] = None
    gmv_12m: Money | None = None
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
    recent_reviews: Annotated[list[RawReview], Field(max_length=500)]


class SearchJobResult(BaseModel):
    kind: Literal["search"]
    offers: list[RawOffer]
    skipped: list[SkippedListing]
    truncated: Annotated[bool, Field(description="True when `max_results` cut the result list.")]


class ProductJobResult(BaseModel):
    kind: Literal["product"]
    offer: RawOffer


class SellerJobResult(BaseModel):
    kind: Literal["seller"]
    seller: RawSeller


class SellerSignalsJobResult(BaseModel):
    kind: Literal["seller_signals"]
    signals: RawSellerSignals


class JobResult(
    RootModel[SearchJobResult | ProductJobResult | SellerJobResult | SellerSignalsJobResult]
):
    root: Annotated[
        SearchJobResult | ProductJobResult | SellerJobResult | SellerSignalsJobResult,
        Field(discriminator="kind"),
    ]


class JobError(BaseModel):
    code: WorkerErrorCode
    message: Annotated[str, Field(max_length=1000)]
    retryable: bool


class JobState(BaseModel):
    job_id: str
    kind: JobKind
    platform: str
    mission_id: str
    trace_id: str
    status: JobStatus
    attempts: Annotated[int, Field(ge=0)]
    created_at: AwareDatetime
    finished_at: AwareDatetime | None
    result: JobResult | None
    error: JobError | None


class OpenChatRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    tenant_id: Annotated[str, Field(min_length=1)]
    mission_id: Annotated[str, Field(min_length=1)]
    trace_id: Annotated[str, Field(min_length=1)]
    negotiation_id: Annotated[str, Field(min_length=1)]
    platform: Annotated[str, Field(min_length=1)]
    account_id: Annotated[
        str,
        Field(
            description="Opaque connected-account id. The worker resolves the session from Vault.",
            min_length=1,
        ),
    ]
    platform_seller_id: Annotated[str, Field(min_length=1)]
    product_id: Annotated[str, Field(min_length=1)]


class ChatLockHolder(RootModel[Literal["human"]]):
    root: Literal["human"]


class ChatLock(BaseModel):
    holder: ChatLockHolder
    user_id: str
    acquired_at: AwareDatetime
    expires_at: AwareDatetime


class Chat(BaseModel):
    chat_id: str
    tenant_id: str
    negotiation_id: str
    platform: str
    account_id: str
    platform_seller_id: str
    product_id: str
    opened_at: AwareDatetime
    lock: ChatLock | None


class ChatRole(StrEnum):
    """
    Side of the conversation. The buyer is us (agent or human), the seller is the counterpart.
    """

    buyer = "buyer"
    seller = "seller"


class ChatSender(StrEnum):
    agent = "agent"
    human = "human"


class ChatMessage(BaseModel):
    seq: Annotated[int, Field(description="Strictly increasing per chat.", ge=1)]
    role: ChatRole
    text: str
    at: AwareDatetime
    sent_by: Annotated[
        ChatSender | None,
        Field(
            description="Who sent a buyer message through this worker. Null for seller messages."
        ),
    ]


class ChatMessagePage(BaseModel):
    chat_id: str
    messages: list[ChatMessage]
    last_seq: Annotated[
        int,
        Field(
            description="Highest `seq` in the chat, so the caller knows whether more pages remain.",
            ge=0,
        ),
    ]


class SendChatMessageRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    text: Annotated[str, Field(max_length=4000, min_length=1)]
    sender: ChatSender
    user_id: Annotated[
        str | None,
        Field(
            description="Required when `sender` is `human`. Must be the lock holder.",
            min_length=1,
        ),
    ] = None
    draft_id: Annotated[
        str | None,
        Field(description="The approved draft this text comes from, for the audit trail."),
    ] = None


class ChatScreenshot(BaseModel):
    screenshot_ref: Annotated[str, Field(description="S3 object key in the attachments bucket.")]
    sha256: Annotated[str, Field(pattern="^[0-9a-f]{64}$")]
    captured_at: AwareDatetime


class AcquireChatLockRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    user_id: Annotated[str, Field(min_length=1)]
    ttl_seconds: Annotated[int, Field(ge=60, le=3600)]


class WorkerHealth(BaseModel):
    status: WorkerHealthStatus
    platforms: list[PlatformStatus]
