-- CreateExtension
CREATE EXTENSION IF NOT EXISTS "vector";

-- CreateEnum
CREATE TYPE "Currency" AS ENUM ('EUR', 'USD', 'CNY');

-- CreateEnum
CREATE TYPE "Role" AS ENUM ('owner', 'admin', 'buyer', 'finance', 'viewer');

-- CreateEnum
CREATE TYPE "ActorType" AS ENUM ('human', 'service', 'agent');

-- CreateEnum
CREATE TYPE "OnboardingStatus" AS ENUM ('profiling', 'financials_pending', 'financials_imported', 'active', 'completed');

-- CreateEnum
CREATE TYPE "PurchaseFrequency" AS ENUM ('weekly', 'monthly', 'quarterly', 'yearly', 'ad_hoc');

-- CreateEnum
CREATE TYPE "FinancialImportStatus" AS ENUM ('draft', 'active', 'superseded', 'rejected');

-- CreateEnum
CREATE TYPE "FinancialMetric" AS ENUM ('cash_balance', 'credit_line_available', 'credit_line_limit', 'accounts_receivable', 'accounts_payable', 'revenue', 'cogs', 'fixed_costs', 'payroll', 'debt_service', 'capex', 'tax_reserve', 'safety_buffer_pct', 'payment_term_days', 'budget');

-- CreateEnum
CREATE TYPE "FinancialSnapshotStatus" AS ENUM ('active', 'superseded');

-- CreateEnum
CREATE TYPE "ConnectedAccountStatus" AS ENUM ('active', 'session_invalidated', 'reauth_required', 'disabled');

-- CreateEnum
CREATE TYPE "SourcingRequestStatus" AS ENUM ('normalized', 'needs_clarification');

-- CreateEnum
CREATE TYPE "MissionState" AS ENUM ('created', 'planning', 'sourcing', 'enriching', 'evaluating', 'negotiating', 'awaiting_decision', 'completed', 'cancelled', 'failed');

-- CreateEnum
CREATE TYPE "SellerConfidenceBand" AS ENUM ('high', 'medium', 'low', 'untrusted', 'insufficient_data');

-- CreateEnum
CREATE TYPE "ReviewAnomalyType" AS ENUM ('burst_velocity', 'five_star_anomaly', 'low_verified_share', 'duplicate_text', 'creation_correlation');

-- CreateEnum
CREATE TYPE "ReviewAnomalySeverity" AS ENUM ('warning', 'critical');

-- CreateEnum
CREATE TYPE "OfferState" AS ENUM ('discovered', 'enriched', 'trust_scored', 'sanity_checked', 'gate_pending', 'gate_approved', 'gate_rejected', 'financially_checked', 'negotiating', 'negotiated', 'sanity_rechecked', 'scored', 'awaiting_human', 'signed', 'approved', 'rejected', 'purchased');

-- CreateEnum
CREATE TYPE "Incoterm" AS ENUM ('EXW', 'FCA', 'FAS', 'FOB', 'CFR', 'CIF', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP');

-- CreateEnum
CREATE TYPE "PriceSanityBand" AS ENUM ('normal', 'atypical', 'implausible', 'insufficient_reference');

-- CreateEnum
CREATE TYPE "SanityDecision" AS ENUM ('negotiate', 'human_gate', 'discard');

-- CreateEnum
CREATE TYPE "DispersionMeasure" AS ENUM ('mad', 'iqr', 'relative');

-- CreateEnum
CREATE TYPE "SanityStage" AS ENUM ('listed', 'negotiated');

-- CreateEnum
CREATE TYPE "FinancialVerdict" AS ENUM ('within_budget', 'stretch', 'out_of_budget');

-- CreateEnum
CREATE TYPE "NegotiationState" AS ENUM ('queued', 'running', 'awaiting_approval', 'human_control', 'paused', 'completed', 'aborted', 'escalated');

-- CreateEnum
CREATE TYPE "MessageRole" AS ENUM ('agent', 'seller', 'human');

-- CreateEnum
CREATE TYPE "MessageStatus" AS ENUM ('drafted', 'approved', 'sent', 'received', 'discarded');

-- CreateEnum
CREATE TYPE "NegotiationOutcomeKind" AS ENUM ('agreed', 'no_agreement', 'escalated', 'stopped_anomalous_price', 'aborted');

-- CreateEnum
CREATE TYPE "ScoreCriterion" AS ENUM ('landed_cost', 'lead_time', 'seller_confidence', 'financial_fit', 'margin_potential', 'spec_match', 'compliance_risk', 'negotiation_gain');

-- CreateEnum
CREATE TYPE "GateReason" AS ENUM ('price_atypical', 'price_insufficient_reference', 'seller_low', 'seller_insufficient_data', 'out_of_budget', 'stretch_above_threshold', 'negotiator_escalated', 'financials_stale', 'fx_provisional', 'dual_control_pending', 'supervisor');

-- CreateEnum
CREATE TYPE "GateStatus" AS ENUM ('open', 'resolved');

-- CreateEnum
CREATE TYPE "GateResolution" AS ENUM ('unblocked', 'discarded', 'overridden', 'held', 'followed');

-- CreateEnum
CREATE TYPE "SigningKeyOwnerType" AS ENUM ('human', 'service');

-- CreateEnum
CREATE TYPE "AuthMethod" AS ENUM ('keycloak_step_up');

-- CreateEnum
CREATE TYPE "SigningSessionStatus" AS ENUM ('active', 'expired', 'revoked', 'exhausted', 'closed');

-- CreateEnum
CREATE TYPE "ReauthReason" AS ENUM ('session_missing', 'session_expired', 'session_revoked', 'session_exhausted', 'key_revoked', 'key_rotated', 'device_mismatch', 'network_anomaly', 'high_value_decision', 'immediate_reauth_required', 'risk_flagged', 'step_up_required');

-- CreateEnum
CREATE TYPE "DecisionType" AS ENUM ('follow', 'renegotiate', 'takeover', 'hold', 'discard', 'approve_purchase', 'activate_financial_snapshot', 'override_discard', 'change_pricing_threshold', 'change_confidence_weights', 'change_scoring_weights', 'rotate_key', 'revoke_key', 'unblock', 'config_change');

-- CreateEnum
CREATE TYPE "DecisionStatus" AS ENUM ('pending_signature', 'signed', 'rejected', 'expired');

-- CreateEnum
CREATE TYPE "ApprovalDecision" AS ENUM ('approve', 'reject');

-- CreateEnum
CREATE TYPE "LlmRole" AS ENUM ('planner', 'negotiator', 'extractor', 'narrator', 'embedder');

-- CreateTable
CREATE TABLE "tenants" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "vat_number" TEXT,
    "country" CHAR(2) NOT NULL,
    "base_currency" "Currency" NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "updated_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "tenants_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL,
    "email" TEXT NOT NULL,
    "display_name" TEXT NOT NULL,
    "external_subject" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "updated_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "memberships" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "role" "Role" NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "memberships_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "onboarding_sessions" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "status" "OnboardingStatus" NOT NULL,
    "created_by_id" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "updated_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "onboarding_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "company_profiles" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "legal_name" TEXT NOT NULL,
    "tax_id" TEXT NOT NULL,
    "country" CHAR(2) NOT NULL,
    "shipping_address" TEXT,
    "billing_address" TEXT,
    "customs_regime" TEXT,
    "cnae" TEXT,
    "sector" TEXT,
    "purchase_categories" TEXT[],
    "purchase_frequency" "PurchaseFrequency",
    "seasonality" TEXT,
    "base_currency" "Currency" NOT NULL,
    "budget_minor" BIGINT,
    "budget_currency" "Currency",
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "updated_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "company_profiles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "financial_imports" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "onboarding_session_id" TEXT,
    "status" "FinancialImportStatus" NOT NULL,
    "csv_ref" TEXT NOT NULL,
    "csv_sha256" TEXT NOT NULL,
    "base_currency" "Currency" NOT NULL,
    "report" JSONB NOT NULL,
    "rows_ok" INTEGER NOT NULL,
    "rows_rejected" INTEGER NOT NULL,
    "projection_enabled" BOOLEAN NOT NULL,
    "periods_loaded" INTEGER NOT NULL,
    "reference_date" DATE,
    "net_buying_capacity_minor" BIGINT,
    "buying_power_score" INTEGER,
    "created_by_type" "ActorType" NOT NULL,
    "created_by_id" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "financial_imports_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "financial_rows" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "import_id" TEXT NOT NULL,
    "row_number" INTEGER NOT NULL,
    "period" CHAR(7) NOT NULL,
    "metric" "FinancialMetric" NOT NULL,
    "category" TEXT,
    "value_minor" BIGINT,
    "value_bp" INTEGER,
    "currency" "Currency",
    "original_value_minor" BIGINT,
    "original_currency" "Currency",
    "fx_rate" DECIMAL(24,12),
    "fx_as_of" TIMESTAMPTZ(6),
    "fx_source" TEXT,
    "converted" BOOLEAN NOT NULL,
    "notes" VARCHAR(500),

    CONSTRAINT "financial_rows_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "financial_snapshots" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "import_id" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "status" "FinancialSnapshotStatus" NOT NULL,
    "base_currency" "Currency" NOT NULL,
    "decision_id" TEXT NOT NULL,
    "activated_at" TIMESTAMPTZ(6) NOT NULL,
    "activated_by_id" TEXT NOT NULL,
    "superseded_at" TIMESTAMPTZ(6),
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "financial_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "budget_envelopes" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "import_id" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "currency" "Currency" NOT NULL,
    "allocated_minor" BIGINT NOT NULL,
    "spent_minor" BIGINT NOT NULL,
    "available_minor" BIGINT NOT NULL,
    "period_start" DATE NOT NULL,
    "period_end" DATE NOT NULL,

    CONSTRAINT "budget_envelopes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "credential_refs" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "vault_path" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "revoked_at" TIMESTAMPTZ(6),

    CONSTRAINT "credential_refs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "connected_accounts" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "label" TEXT,
    "status" "ConnectedAccountStatus" NOT NULL,
    "credential_ref_id" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "updated_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "connected_accounts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "tenant_config_versions" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "config_version" INTEGER NOT NULL,
    "content_hash" TEXT NOT NULL,
    "values" JSONB NOT NULL,
    "decision_id" TEXT,
    "created_by_type" "ActorType" NOT NULL,
    "created_by_id" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "tenant_config_versions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_profile_preferences" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "profile_key" TEXT NOT NULL,
    "version" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "weights" JSONB NOT NULL,
    "negotiation" JSONB NOT NULL,
    "hard_constraints" JSONB NOT NULL,
    "decision_id" TEXT,
    "created_by_type" "ActorType" NOT NULL,
    "created_by_id" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "user_profile_preferences_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "sourcing_requests" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "created_by_id" TEXT NOT NULL,
    "status" "SourcingRequestStatus" NOT NULL,
    "raw_text" TEXT,
    "spec" JSONB NOT NULL,
    "quantity_tiers" JSONB NOT NULL,
    "max_budget_minor" BIGINT,
    "max_budget_currency" "Currency",
    "target_delivery_date" DATE,
    "delivery_country" CHAR(2) NOT NULL,
    "delivery_address" TEXT,
    "excluded_platforms" TEXT[],
    "excluded_countries" TEXT[],
    "excluded_sellers" TEXT[],
    "needs_clarification" TEXT[],
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "sourcing_requests_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "sourcing_items" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "position" INTEGER NOT NULL,
    "spec" JSONB NOT NULL,
    "quantity_tiers" JSONB NOT NULL,

    CONSTRAINT "sourcing_items_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "sourcing_plans" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "platforms" TEXT[],
    "queries" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "sourcing_plans_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "missions" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "request_id" TEXT NOT NULL,
    "plan_id" TEXT,
    "state" "MissionState" NOT NULL,
    "config_version" INTEGER NOT NULL,
    "offers_discovered" INTEGER NOT NULL,
    "offers_negotiated" INTEGER NOT NULL,
    "offers_in_gate" INTEGER NOT NULL,
    "tokens_used" BIGINT NOT NULL,
    "token_budget" BIGINT NOT NULL,
    "started_at" TIMESTAMPTZ(6) NOT NULL,
    "completed_at" TIMESTAMPTZ(6),
    "error" JSONB,

    CONSTRAINT "missions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "sellers" (
    "id" TEXT NOT NULL,
    "canonical_id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "country" CHAR(2),
    "risk_flags" TEXT[],
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "updated_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "sellers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "seller_platform_ids" (
    "id" TEXT NOT NULL,
    "seller_id" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "platform_seller_id" TEXT NOT NULL,

    CONSTRAINT "seller_platform_ids_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "seller_signal_snapshots" (
    "id" TEXT NOT NULL,
    "seller_id" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "account_age_days" INTEGER,
    "first_sale_date" DATE,
    "months_active_last_12" INTEGER,
    "lifetime_transactions" BIGINT,
    "transactions_12m" BIGINT,
    "gmv_12m_minor" BIGINT,
    "gmv_12m_currency" "Currency",
    "repeat_buyer_share" DECIMAL(7,6),
    "published_products_count" INTEGER,
    "catalog_churn_30d" DECIMAL(7,6),
    "spec_completeness_avg" DECIMAL(7,6),
    "reviews_total" BIGINT,
    "reviews_12m" BIGINT,
    "rating_avg" DECIMAL(4,3),
    "rating_count" BIGINT,
    "verified_review_share" DECIMAL(7,6),
    "response_rate" DECIMAL(7,6),
    "identity_verified" BOOLEAN,
    "trade_assurance" BOOLEAN,
    "escrow_available" BOOLEAN,
    "dispute_rate" DECIMAL(7,6),
    "refund_rate" DECIMAL(7,6),
    "signal_count" INTEGER NOT NULL,
    "data_completeness" DECIMAL(5,4) NOT NULL,
    "raw" JSONB NOT NULL,
    "captured_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "seller_signal_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "seller_confidences" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "seller_id" TEXT NOT NULL,
    "snapshot_id" TEXT,
    "score" INTEGER,
    "band" "SellerConfidenceBand" NOT NULL,
    "signals_normalized" JSONB NOT NULL,
    "penalties" TEXT[],
    "flags" JSONB NOT NULL,
    "model_version" TEXT NOT NULL,
    "config_version" INTEGER NOT NULL,
    "computed_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "seller_confidences_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "review_anomalies" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "seller_id" TEXT NOT NULL,
    "snapshot_id" TEXT,
    "type" "ReviewAnomalyType" NOT NULL,
    "severity" "ReviewAnomalySeverity" NOT NULL,
    "evidence" JSONB NOT NULL,
    "detected_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "review_anomalies_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "offers" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "mission_id" TEXT NOT NULL,
    "platform" TEXT NOT NULL,
    "platform_offer_id" TEXT NOT NULL,
    "product_url" TEXT,
    "product_key" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "description" TEXT,
    "specifications" JSONB NOT NULL,
    "certifications" TEXT[],
    "image_urls" TEXT[],
    "seller_id" TEXT NOT NULL,
    "seller_name" TEXT NOT NULL,
    "seller_country" CHAR(2),
    "unit_price_minor" BIGINT NOT NULL,
    "currency" "Currency" NOT NULL,
    "original_amount_minor" BIGINT,
    "original_currency" "Currency",
    "fx_rate" DECIMAL(24,12),
    "fx_as_of" TIMESTAMPTZ(6),
    "fx_source" TEXT,
    "converted" BOOLEAN NOT NULL,
    "fx_provisional" BOOLEAN NOT NULL,
    "moq" INTEGER NOT NULL,
    "price_tiers" JSONB NOT NULL,
    "shipping" JSONB,
    "incoterm" "Incoterm",
    "lead_time_days" INTEGER,
    "state" "OfferState" NOT NULL,
    "discovered_at" TIMESTAMPTZ(6) NOT NULL,
    "expires_at" TIMESTAMPTZ(6),

    CONSTRAINT "offers_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "price_sanity_checks" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "offer_id" TEXT NOT NULL,
    "stage" "SanityStage" NOT NULL,
    "reference_price_eur_minor" BIGINT NOT NULL,
    "median_eur_minor" BIGINT,
    "dispersion_measure" "DispersionMeasure",
    "dispersion_value" DECIMAL(30,10),
    "sample_size" INTEGER NOT NULL,
    "index_score" DECIMAL(20,10),
    "relative_deviation" DECIMAL(20,10),
    "band" "PriceSanityBand" NOT NULL,
    "decision" "SanityDecision" NOT NULL,
    "explanations" JSONB NOT NULL,
    "config_version" INTEGER NOT NULL,
    "checked_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "price_sanity_checks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "price_history" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "product_key" TEXT NOT NULL,
    "seller_id" TEXT NOT NULL,
    "landed_unit_cost_eur_minor" BIGINT NOT NULL,
    "date" DATE NOT NULL,
    "mission_id" TEXT,
    "offer_id" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "price_history_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fx_rates" (
    "id" TEXT NOT NULL,
    "base" "Currency" NOT NULL,
    "quote" "Currency" NOT NULL,
    "rate" DECIMAL(24,12) NOT NULL,
    "as_of" TIMESTAMPTZ(6) NOT NULL,
    "source" TEXT NOT NULL,
    "ingested_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "fx_rates_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "financial_fits" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "offer_id" TEXT NOT NULL,
    "snapshot_id" TEXT,
    "quantity" INTEGER NOT NULL,
    "currency" "Currency" NOT NULL,
    "landed_total_minor" BIGINT NOT NULL,
    "unit_landed_cost_minor" BIGINT NOT NULL,
    "landed_cost" JSONB NOT NULL,
    "verdict" "FinancialVerdict" NOT NULL,
    "reasons" TEXT[],
    "budget_utilization_bp" INTEGER,
    "treasury_impact_minor" BIGINT,
    "financials_stale" BOOLEAN NOT NULL,
    "fx_provisional" BOOLEAN NOT NULL,
    "config_version" INTEGER NOT NULL,
    "computed_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "financial_fits_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "negotiations" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "offer_id" TEXT NOT NULL,
    "attempt" INTEGER NOT NULL,
    "idempotency_key" TEXT NOT NULL,
    "connected_account_id" TEXT,
    "strategy" TEXT NOT NULL,
    "state" "NegotiationState" NOT NULL,
    "rounds" INTEGER NOT NULL,
    "max_rounds" INTEGER,
    "guardrail_hits" JSONB NOT NULL,
    "controlled_by_id" TEXT,
    "started_at" TIMESTAMPTZ(6) NOT NULL,
    "completed_at" TIMESTAMPTZ(6),

    CONSTRAINT "negotiations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "negotiation_messages" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "negotiation_id" TEXT NOT NULL,
    "seq" INTEGER NOT NULL,
    "role" "MessageRole" NOT NULL,
    "status" "MessageStatus" NOT NULL,
    "content" TEXT NOT NULL,
    "at" TIMESTAMPTZ(6) NOT NULL,
    "screenshot_ref" TEXT,
    "redactions" INTEGER NOT NULL,
    "approved_by_id" TEXT,

    CONSTRAINT "negotiation_messages_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "negotiation_outcomes" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "negotiation_id" TEXT NOT NULL,
    "offer_id" TEXT NOT NULL,
    "outcome" "NegotiationOutcomeKind" NOT NULL,
    "currency" "Currency" NOT NULL,
    "initial_price_minor" BIGINT NOT NULL,
    "final_price_minor" BIGINT,
    "quantity" INTEGER,
    "discount_bp" INTEGER,
    "concessions" JSONB NOT NULL,
    "terms" JSONB NOT NULL,
    "seller_confidence_id" TEXT,
    "transcript_ref" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "negotiation_outcomes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "scores" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "offer_id" TEXT NOT NULL,
    "profile_id" TEXT NOT NULL,
    "value" DECIMAL(20,10) NOT NULL,
    "rank" INTEGER,
    "config_version" INTEGER NOT NULL,
    "model_version" TEXT NOT NULL,
    "computed_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "scores_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "score_breakdowns" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "score_id" TEXT NOT NULL,
    "criterion" "ScoreCriterion" NOT NULL,
    "weight" DECIMAL(20,10) NOT NULL,
    "normalized_value" DECIMAL(20,10),
    "contribution" DECIMAL(20,10) NOT NULL,
    "penalty" DECIMAL(20,10) NOT NULL,

    CONSTRAINT "score_breakdowns_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "recommendations" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "mission_id" TEXT NOT NULL,
    "profile_id" TEXT NOT NULL,
    "ranking" JSONB NOT NULL,
    "excluded" JSONB NOT NULL,
    "alternatives" JSONB NOT NULL,
    "savings" JSONB NOT NULL,
    "narrative" TEXT,
    "config_version" INTEGER NOT NULL,
    "model_version" TEXT NOT NULL,
    "generated_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "recommendations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "gate_queue_items" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "mission_id" TEXT NOT NULL,
    "offer_id" TEXT,
    "causes" "GateReason"[],
    "status" "GateStatus" NOT NULL,
    "resolution" "GateResolution",
    "decision_id" TEXT,
    "assigned_to_id" TEXT,
    "sla_due_at" TIMESTAMPTZ(6) NOT NULL,
    "reminder_sent_at" TIMESTAMPTZ(6),
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "resolved_at" TIMESTAMPTZ(6),

    CONSTRAINT "gate_queue_items_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "signing_keys" (
    "id" TEXT NOT NULL,
    "owner_type" "SigningKeyOwnerType" NOT NULL,
    "owner_id" TEXT NOT NULL,
    "user_id" TEXT,
    "tenant_id" TEXT,
    "public_key" TEXT NOT NULL,
    "alg" TEXT NOT NULL,
    "label" TEXT,
    "vault_key_ref" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "rotated_at" TIMESTAMPTZ(6),
    "revoked_at" TIMESTAMPTZ(6),
    "revoked_reason" TEXT,

    CONSTRAINT "signing_keys_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "signing_sessions" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "key_id" TEXT NOT NULL,
    "auth_method" "AuthMethod" NOT NULL,
    "auth_at" TIMESTAMPTZ(6) NOT NULL,
    "expires_at" TIMESTAMPTZ(6) NOT NULL,
    "device_fingerprint_ref" TEXT NOT NULL,
    "decisions_signed" TEXT[],
    "max_decisions" INTEGER NOT NULL,
    "status" "SigningSessionStatus" NOT NULL,
    "revoked_reason" "ReauthReason",
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "ended_at" TIMESTAMPTZ(6),

    CONSTRAINT "signing_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "decisions" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "type" "DecisionType" NOT NULL,
    "subject_ref" TEXT NOT NULL,
    "payload_canonical" TEXT NOT NULL,
    "payload_hash" TEXT NOT NULL,
    "status" "DecisionStatus" NOT NULL,
    "requires_immediate_reauth" BOOLEAN NOT NULL,
    "required_signers" INTEGER NOT NULL,
    "config_version" INTEGER,
    "created_by_type" "ActorType" NOT NULL,
    "created_by_id" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "signed_at" TIMESTAMPTZ(6),
    "rejected_at" TIMESTAMPTZ(6),

    CONSTRAINT "decisions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "signatures" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "decision_id" TEXT NOT NULL,
    "signer_type" "ActorType" NOT NULL,
    "signer_id" TEXT NOT NULL,
    "key_id" TEXT NOT NULL,
    "alg" TEXT NOT NULL,
    "payload_hash" TEXT NOT NULL,
    "signature" TEXT NOT NULL,
    "signed_at" TIMESTAMPTZ(6) NOT NULL,
    "signing_session_id" TEXT,
    "auth_at" TIMESTAMPTZ(6),
    "prev_signature_hash" TEXT,
    "chain_hash" TEXT NOT NULL,
    "client_attestation" TEXT,

    CONSTRAINT "signatures_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "approvals" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "decision_id" TEXT NOT NULL,
    "requested_by_type" "ActorType" NOT NULL,
    "requested_by_id" TEXT NOT NULL,
    "approver_id" TEXT,
    "decision" "ApprovalDecision",
    "comment" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL,
    "decided_at" TIMESTAMPTZ(6),

    CONSTRAINT "approvals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_events" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "seq" BIGINT NOT NULL,
    "actor_type" "ActorType" NOT NULL,
    "actor_id" TEXT NOT NULL,
    "event_type" TEXT NOT NULL,
    "subject_ref" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "payload_hash" TEXT NOT NULL,
    "prev_hash" TEXT NOT NULL,
    "hash" TEXT NOT NULL,
    "service_signature" TEXT,
    "service_key_id" TEXT,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "audit_events_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "llm_events" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT,
    "mission_id" TEXT,
    "role" "LlmRole" NOT NULL,
    "endpoint" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "prompt_version" TEXT NOT NULL,
    "tokens_in" INTEGER NOT NULL,
    "tokens_out" INTEGER NOT NULL,
    "latency_ms" INTEGER NOT NULL,
    "repaired_json" BOOLEAN NOT NULL,
    "cost_minor" BIGINT,
    "cost_currency" "Currency",
    "gpu_seconds" DECIMAL(20,6),
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "llm_events_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "effect_ledger" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "key" TEXT NOT NULL,
    "result" JSONB NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "effect_ledger_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "product_embeddings" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "offer_id" TEXT,
    "product_key" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "dimensions" INTEGER NOT NULL,
    "embedding" vector NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "product_embeddings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "negotiation_embeddings" (
    "id" TEXT NOT NULL,
    "tenant_id" TEXT NOT NULL,
    "negotiation_id" TEXT NOT NULL,
    "chunk" INTEGER NOT NULL,
    "model" TEXT NOT NULL,
    "dimensions" INTEGER NOT NULL,
    "embedding" vector NOT NULL,
    "created_at" TIMESTAMPTZ(6) NOT NULL,

    CONSTRAINT "negotiation_embeddings_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "users_external_subject_key" ON "users"("external_subject");

-- CreateIndex
CREATE INDEX "memberships_user_id_idx" ON "memberships"("user_id");

-- CreateIndex
CREATE UNIQUE INDEX "memberships_tenant_id_user_id_key" ON "memberships"("tenant_id", "user_id");

-- CreateIndex
CREATE INDEX "onboarding_sessions_tenant_id_idx" ON "onboarding_sessions"("tenant_id");

-- CreateIndex
CREATE UNIQUE INDEX "company_profiles_tenant_id_key" ON "company_profiles"("tenant_id");

-- CreateIndex
CREATE INDEX "financial_imports_tenant_id_status_idx" ON "financial_imports"("tenant_id", "status");

-- CreateIndex
CREATE INDEX "financial_rows_tenant_id_metric_period_idx" ON "financial_rows"("tenant_id", "metric", "period");

-- CreateIndex
CREATE UNIQUE INDEX "financial_rows_import_id_row_number_key" ON "financial_rows"("import_id", "row_number");

-- CreateIndex
CREATE UNIQUE INDEX "financial_snapshots_import_id_key" ON "financial_snapshots"("import_id");

-- CreateIndex
CREATE UNIQUE INDEX "financial_snapshots_decision_id_key" ON "financial_snapshots"("decision_id");

-- CreateIndex
CREATE UNIQUE INDEX "financial_snapshots_tenant_id_version_key" ON "financial_snapshots"("tenant_id", "version");

-- CreateIndex
CREATE UNIQUE INDEX "budget_envelopes_import_id_category_period_start_key" ON "budget_envelopes"("import_id", "category", "period_start");

-- CreateIndex
CREATE INDEX "credential_refs_tenant_id_idx" ON "credential_refs"("tenant_id");

-- CreateIndex
CREATE INDEX "connected_accounts_tenant_id_platform_idx" ON "connected_accounts"("tenant_id", "platform");

-- CreateIndex
CREATE UNIQUE INDEX "tenant_config_versions_decision_id_key" ON "tenant_config_versions"("decision_id");

-- CreateIndex
CREATE UNIQUE INDEX "tenant_config_versions_tenant_id_config_version_key" ON "tenant_config_versions"("tenant_id", "config_version");

-- CreateIndex
CREATE UNIQUE INDEX "user_profile_preferences_decision_id_key" ON "user_profile_preferences"("decision_id");

-- CreateIndex
CREATE UNIQUE INDEX "user_profile_preferences_tenant_id_profile_key_version_key" ON "user_profile_preferences"("tenant_id", "profile_key", "version");

-- CreateIndex
CREATE INDEX "sourcing_requests_tenant_id_created_at_idx" ON "sourcing_requests"("tenant_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "sourcing_items_request_id_position_key" ON "sourcing_items"("request_id", "position");

-- CreateIndex
CREATE INDEX "sourcing_plans_request_id_idx" ON "sourcing_plans"("request_id");

-- CreateIndex
CREATE INDEX "missions_tenant_id_state_idx" ON "missions"("tenant_id", "state");

-- CreateIndex
CREATE UNIQUE INDEX "sellers_canonical_id_key" ON "sellers"("canonical_id");

-- CreateIndex
CREATE INDEX "seller_platform_ids_seller_id_idx" ON "seller_platform_ids"("seller_id");

-- CreateIndex
CREATE UNIQUE INDEX "seller_platform_ids_platform_platform_seller_id_key" ON "seller_platform_ids"("platform", "platform_seller_id");

-- CreateIndex
CREATE INDEX "seller_signal_snapshots_seller_id_captured_at_idx" ON "seller_signal_snapshots"("seller_id", "captured_at");

-- CreateIndex
CREATE INDEX "seller_confidences_tenant_id_seller_id_computed_at_idx" ON "seller_confidences"("tenant_id", "seller_id", "computed_at");

-- CreateIndex
CREATE INDEX "review_anomalies_tenant_id_seller_id_idx" ON "review_anomalies"("tenant_id", "seller_id");

-- CreateIndex
CREATE INDEX "offers_tenant_id_mission_id_state_idx" ON "offers"("tenant_id", "mission_id", "state");

-- CreateIndex
CREATE INDEX "offers_seller_id_idx" ON "offers"("seller_id");

-- CreateIndex
CREATE INDEX "offers_product_key_idx" ON "offers"("product_key");

-- CreateIndex
CREATE UNIQUE INDEX "offers_mission_id_platform_platform_offer_id_key" ON "offers"("mission_id", "platform", "platform_offer_id");

-- CreateIndex
CREATE INDEX "price_sanity_checks_tenant_id_offer_id_checked_at_idx" ON "price_sanity_checks"("tenant_id", "offer_id", "checked_at");

-- CreateIndex
CREATE INDEX "price_history_tenant_id_product_key_date_idx" ON "price_history"("tenant_id", "product_key", "date");

-- CreateIndex
CREATE INDEX "fx_rates_base_quote_as_of_idx" ON "fx_rates"("base", "quote", "as_of");

-- CreateIndex
CREATE UNIQUE INDEX "fx_rates_base_quote_as_of_source_key" ON "fx_rates"("base", "quote", "as_of", "source");

-- CreateIndex
CREATE INDEX "financial_fits_tenant_id_offer_id_computed_at_idx" ON "financial_fits"("tenant_id", "offer_id", "computed_at");

-- CreateIndex
CREATE UNIQUE INDEX "negotiations_idempotency_key_key" ON "negotiations"("idempotency_key");

-- CreateIndex
CREATE INDEX "negotiations_tenant_id_state_idx" ON "negotiations"("tenant_id", "state");

-- CreateIndex
CREATE UNIQUE INDEX "negotiations_offer_id_attempt_key" ON "negotiations"("offer_id", "attempt");

-- CreateIndex
CREATE UNIQUE INDEX "negotiation_messages_negotiation_id_seq_key" ON "negotiation_messages"("negotiation_id", "seq");

-- CreateIndex
CREATE UNIQUE INDEX "negotiation_outcomes_negotiation_id_key" ON "negotiation_outcomes"("negotiation_id");

-- CreateIndex
CREATE INDEX "negotiation_outcomes_tenant_id_offer_id_idx" ON "negotiation_outcomes"("tenant_id", "offer_id");

-- CreateIndex
CREATE INDEX "scores_tenant_id_offer_id_idx" ON "scores"("tenant_id", "offer_id");

-- CreateIndex
CREATE UNIQUE INDEX "score_breakdowns_score_id_criterion_key" ON "score_breakdowns"("score_id", "criterion");

-- CreateIndex
CREATE INDEX "recommendations_tenant_id_mission_id_idx" ON "recommendations"("tenant_id", "mission_id");

-- CreateIndex
CREATE UNIQUE INDEX "gate_queue_items_decision_id_key" ON "gate_queue_items"("decision_id");

-- CreateIndex
CREATE INDEX "gate_queue_items_tenant_id_status_sla_due_at_idx" ON "gate_queue_items"("tenant_id", "status", "sla_due_at");

-- CreateIndex
CREATE UNIQUE INDEX "signing_keys_public_key_key" ON "signing_keys"("public_key");

-- CreateIndex
CREATE INDEX "signing_keys_owner_type_owner_id_idx" ON "signing_keys"("owner_type", "owner_id");

-- CreateIndex
CREATE INDEX "signing_keys_tenant_id_idx" ON "signing_keys"("tenant_id");

-- CreateIndex
CREATE INDEX "signing_sessions_tenant_id_user_id_status_idx" ON "signing_sessions"("tenant_id", "user_id", "status");

-- CreateIndex
CREATE INDEX "decisions_tenant_id_status_idx" ON "decisions"("tenant_id", "status");

-- CreateIndex
CREATE INDEX "decisions_tenant_id_subject_ref_idx" ON "decisions"("tenant_id", "subject_ref");

-- CreateIndex
CREATE UNIQUE INDEX "signatures_chain_hash_key" ON "signatures"("chain_hash");

-- CreateIndex
CREATE INDEX "signatures_tenant_id_signed_at_idx" ON "signatures"("tenant_id", "signed_at");

-- CreateIndex
CREATE UNIQUE INDEX "signatures_decision_id_signer_id_key" ON "signatures"("decision_id", "signer_id");

-- CreateIndex
CREATE UNIQUE INDEX "signatures_tenant_id_prev_signature_hash_key" ON "signatures"("tenant_id", "prev_signature_hash");

-- CreateIndex
CREATE INDEX "approvals_tenant_id_decision_id_idx" ON "approvals"("tenant_id", "decision_id");

-- CreateIndex
CREATE UNIQUE INDEX "audit_events_hash_key" ON "audit_events"("hash");

-- CreateIndex
CREATE INDEX "audit_events_tenant_id_created_at_idx" ON "audit_events"("tenant_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "audit_events_tenant_id_seq_key" ON "audit_events"("tenant_id", "seq");

-- CreateIndex
CREATE UNIQUE INDEX "audit_events_tenant_id_prev_hash_key" ON "audit_events"("tenant_id", "prev_hash");

-- CreateIndex
CREATE INDEX "llm_events_tenant_id_mission_id_idx" ON "llm_events"("tenant_id", "mission_id");

-- CreateIndex
CREATE UNIQUE INDEX "effect_ledger_tenant_id_key_key" ON "effect_ledger"("tenant_id", "key");

-- CreateIndex
CREATE INDEX "product_embeddings_tenant_id_product_key_idx" ON "product_embeddings"("tenant_id", "product_key");

-- CreateIndex
CREATE UNIQUE INDEX "negotiation_embeddings_negotiation_id_chunk_model_key" ON "negotiation_embeddings"("negotiation_id", "chunk", "model");

-- AddForeignKey
ALTER TABLE "memberships" ADD CONSTRAINT "memberships_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "memberships" ADD CONSTRAINT "memberships_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "onboarding_sessions" ADD CONSTRAINT "onboarding_sessions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "company_profiles" ADD CONSTRAINT "company_profiles_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_imports" ADD CONSTRAINT "financial_imports_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_imports" ADD CONSTRAINT "financial_imports_onboarding_session_id_fkey" FOREIGN KEY ("onboarding_session_id") REFERENCES "onboarding_sessions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_rows" ADD CONSTRAINT "financial_rows_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_rows" ADD CONSTRAINT "financial_rows_import_id_fkey" FOREIGN KEY ("import_id") REFERENCES "financial_imports"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_snapshots" ADD CONSTRAINT "financial_snapshots_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_snapshots" ADD CONSTRAINT "financial_snapshots_import_id_fkey" FOREIGN KEY ("import_id") REFERENCES "financial_imports"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_snapshots" ADD CONSTRAINT "financial_snapshots_decision_id_fkey" FOREIGN KEY ("decision_id") REFERENCES "decisions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "budget_envelopes" ADD CONSTRAINT "budget_envelopes_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "budget_envelopes" ADD CONSTRAINT "budget_envelopes_import_id_fkey" FOREIGN KEY ("import_id") REFERENCES "financial_imports"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "credential_refs" ADD CONSTRAINT "credential_refs_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "connected_accounts" ADD CONSTRAINT "connected_accounts_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "connected_accounts" ADD CONSTRAINT "connected_accounts_credential_ref_id_fkey" FOREIGN KEY ("credential_ref_id") REFERENCES "credential_refs"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tenant_config_versions" ADD CONSTRAINT "tenant_config_versions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "tenant_config_versions" ADD CONSTRAINT "tenant_config_versions_decision_id_fkey" FOREIGN KEY ("decision_id") REFERENCES "decisions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_profile_preferences" ADD CONSTRAINT "user_profile_preferences_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "user_profile_preferences" ADD CONSTRAINT "user_profile_preferences_decision_id_fkey" FOREIGN KEY ("decision_id") REFERENCES "decisions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sourcing_requests" ADD CONSTRAINT "sourcing_requests_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sourcing_items" ADD CONSTRAINT "sourcing_items_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sourcing_items" ADD CONSTRAINT "sourcing_items_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "sourcing_requests"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sourcing_plans" ADD CONSTRAINT "sourcing_plans_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "sourcing_plans" ADD CONSTRAINT "sourcing_plans_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "sourcing_requests"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "missions" ADD CONSTRAINT "missions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "missions" ADD CONSTRAINT "missions_request_id_fkey" FOREIGN KEY ("request_id") REFERENCES "sourcing_requests"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "missions" ADD CONSTRAINT "missions_plan_id_fkey" FOREIGN KEY ("plan_id") REFERENCES "sourcing_plans"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "missions" ADD CONSTRAINT "missions_tenant_id_config_version_fkey" FOREIGN KEY ("tenant_id", "config_version") REFERENCES "tenant_config_versions"("tenant_id", "config_version") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "seller_platform_ids" ADD CONSTRAINT "seller_platform_ids_seller_id_fkey" FOREIGN KEY ("seller_id") REFERENCES "sellers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "seller_signal_snapshots" ADD CONSTRAINT "seller_signal_snapshots_seller_id_fkey" FOREIGN KEY ("seller_id") REFERENCES "sellers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "seller_confidences" ADD CONSTRAINT "seller_confidences_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "seller_confidences" ADD CONSTRAINT "seller_confidences_seller_id_fkey" FOREIGN KEY ("seller_id") REFERENCES "sellers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "seller_confidences" ADD CONSTRAINT "seller_confidences_snapshot_id_fkey" FOREIGN KEY ("snapshot_id") REFERENCES "seller_signal_snapshots"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "seller_confidences" ADD CONSTRAINT "seller_confidences_tenant_id_config_version_fkey" FOREIGN KEY ("tenant_id", "config_version") REFERENCES "tenant_config_versions"("tenant_id", "config_version") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "review_anomalies" ADD CONSTRAINT "review_anomalies_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "review_anomalies" ADD CONSTRAINT "review_anomalies_seller_id_fkey" FOREIGN KEY ("seller_id") REFERENCES "sellers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "review_anomalies" ADD CONSTRAINT "review_anomalies_snapshot_id_fkey" FOREIGN KEY ("snapshot_id") REFERENCES "seller_signal_snapshots"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "offers" ADD CONSTRAINT "offers_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "offers" ADD CONSTRAINT "offers_mission_id_fkey" FOREIGN KEY ("mission_id") REFERENCES "missions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "offers" ADD CONSTRAINT "offers_seller_id_fkey" FOREIGN KEY ("seller_id") REFERENCES "sellers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_sanity_checks" ADD CONSTRAINT "price_sanity_checks_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_sanity_checks" ADD CONSTRAINT "price_sanity_checks_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_sanity_checks" ADD CONSTRAINT "price_sanity_checks_tenant_id_config_version_fkey" FOREIGN KEY ("tenant_id", "config_version") REFERENCES "tenant_config_versions"("tenant_id", "config_version") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_history" ADD CONSTRAINT "price_history_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_history" ADD CONSTRAINT "price_history_seller_id_fkey" FOREIGN KEY ("seller_id") REFERENCES "sellers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_history" ADD CONSTRAINT "price_history_mission_id_fkey" FOREIGN KEY ("mission_id") REFERENCES "missions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "price_history" ADD CONSTRAINT "price_history_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_fits" ADD CONSTRAINT "financial_fits_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_fits" ADD CONSTRAINT "financial_fits_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_fits" ADD CONSTRAINT "financial_fits_snapshot_id_fkey" FOREIGN KEY ("snapshot_id") REFERENCES "financial_snapshots"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "financial_fits" ADD CONSTRAINT "financial_fits_tenant_id_config_version_fkey" FOREIGN KEY ("tenant_id", "config_version") REFERENCES "tenant_config_versions"("tenant_id", "config_version") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiations" ADD CONSTRAINT "negotiations_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiations" ADD CONSTRAINT "negotiations_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiations" ADD CONSTRAINT "negotiations_connected_account_id_fkey" FOREIGN KEY ("connected_account_id") REFERENCES "connected_accounts"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_messages" ADD CONSTRAINT "negotiation_messages_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_messages" ADD CONSTRAINT "negotiation_messages_negotiation_id_fkey" FOREIGN KEY ("negotiation_id") REFERENCES "negotiations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_outcomes" ADD CONSTRAINT "negotiation_outcomes_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_outcomes" ADD CONSTRAINT "negotiation_outcomes_negotiation_id_fkey" FOREIGN KEY ("negotiation_id") REFERENCES "negotiations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_outcomes" ADD CONSTRAINT "negotiation_outcomes_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_outcomes" ADD CONSTRAINT "negotiation_outcomes_seller_confidence_id_fkey" FOREIGN KEY ("seller_confidence_id") REFERENCES "seller_confidences"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "scores" ADD CONSTRAINT "scores_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "scores" ADD CONSTRAINT "scores_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "scores" ADD CONSTRAINT "scores_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "user_profile_preferences"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "scores" ADD CONSTRAINT "scores_tenant_id_config_version_fkey" FOREIGN KEY ("tenant_id", "config_version") REFERENCES "tenant_config_versions"("tenant_id", "config_version") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "score_breakdowns" ADD CONSTRAINT "score_breakdowns_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "score_breakdowns" ADD CONSTRAINT "score_breakdowns_score_id_fkey" FOREIGN KEY ("score_id") REFERENCES "scores"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "recommendations" ADD CONSTRAINT "recommendations_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "recommendations" ADD CONSTRAINT "recommendations_mission_id_fkey" FOREIGN KEY ("mission_id") REFERENCES "missions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "recommendations" ADD CONSTRAINT "recommendations_profile_id_fkey" FOREIGN KEY ("profile_id") REFERENCES "user_profile_preferences"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "recommendations" ADD CONSTRAINT "recommendations_tenant_id_config_version_fkey" FOREIGN KEY ("tenant_id", "config_version") REFERENCES "tenant_config_versions"("tenant_id", "config_version") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "gate_queue_items" ADD CONSTRAINT "gate_queue_items_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "gate_queue_items" ADD CONSTRAINT "gate_queue_items_mission_id_fkey" FOREIGN KEY ("mission_id") REFERENCES "missions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "gate_queue_items" ADD CONSTRAINT "gate_queue_items_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "gate_queue_items" ADD CONSTRAINT "gate_queue_items_decision_id_fkey" FOREIGN KEY ("decision_id") REFERENCES "decisions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signing_keys" ADD CONSTRAINT "signing_keys_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signing_keys" ADD CONSTRAINT "signing_keys_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signing_sessions" ADD CONSTRAINT "signing_sessions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signing_sessions" ADD CONSTRAINT "signing_sessions_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signing_sessions" ADD CONSTRAINT "signing_sessions_key_id_fkey" FOREIGN KEY ("key_id") REFERENCES "signing_keys"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "decisions" ADD CONSTRAINT "decisions_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signatures" ADD CONSTRAINT "signatures_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signatures" ADD CONSTRAINT "signatures_decision_id_fkey" FOREIGN KEY ("decision_id") REFERENCES "decisions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signatures" ADD CONSTRAINT "signatures_key_id_fkey" FOREIGN KEY ("key_id") REFERENCES "signing_keys"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "signatures" ADD CONSTRAINT "signatures_signing_session_id_fkey" FOREIGN KEY ("signing_session_id") REFERENCES "signing_sessions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_decision_id_fkey" FOREIGN KEY ("decision_id") REFERENCES "decisions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "approvals" ADD CONSTRAINT "approvals_approver_id_fkey" FOREIGN KEY ("approver_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_events" ADD CONSTRAINT "audit_events_service_key_id_fkey" FOREIGN KEY ("service_key_id") REFERENCES "signing_keys"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "llm_events" ADD CONSTRAINT "llm_events_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "llm_events" ADD CONSTRAINT "llm_events_mission_id_fkey" FOREIGN KEY ("mission_id") REFERENCES "missions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "effect_ledger" ADD CONSTRAINT "effect_ledger_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product_embeddings" ADD CONSTRAINT "product_embeddings_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "product_embeddings" ADD CONSTRAINT "product_embeddings_offer_id_fkey" FOREIGN KEY ("offer_id") REFERENCES "offers"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_embeddings" ADD CONSTRAINT "negotiation_embeddings_tenant_id_fkey" FOREIGN KEY ("tenant_id") REFERENCES "tenants"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "negotiation_embeddings" ADD CONSTRAINT "negotiation_embeddings_negotiation_id_fkey" FOREIGN KEY ("negotiation_id") REFERENCES "negotiations"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
