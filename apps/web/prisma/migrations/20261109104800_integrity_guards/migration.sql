-- D2-03: integrity guards Prisma cannot model (ADR-201, ADR-205).
-- Append-only triggers, guarded state transitions, CHECK constraints, a partial unique index and the
-- LangGraph checkpointer schema. Row-level security and database roles come in D2-04.
--
-- Every guard raises SQLSTATE 23000 (integrity_constraint_violation) with a message that starts with
-- "apex:" so callers and tests can tell these errors apart from ordinary constraint failures.

-- =============================================================================
-- Append-only tables: no UPDATE, no DELETE, no TRUNCATE
-- =============================================================================

CREATE FUNCTION apex_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'apex: % on % is forbidden, the table is append-only', TG_OP, TG_TABLE_NAME
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'audit_events',
    'signatures',
    'fx_rates',
    'seller_signal_snapshots',
    'seller_confidences',
    'tenant_config_versions',
    'user_profile_preferences',
    'financial_rows'
  ] LOOP
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION apex_forbid_mutation()',
      t || '_append_only', t);
    EXECUTE format(
      'CREATE TRIGGER %I BEFORE TRUNCATE ON %I FOR EACH STATEMENT EXECUTE FUNCTION apex_forbid_mutation()',
      t || '_no_truncate', t);
  END LOOP;
END;
$$;

-- =============================================================================
-- Financial snapshots: immutable once active. The only allowed change is active -> superseded,
-- which sets superseded_at once and touches nothing else.
-- =============================================================================

CREATE FUNCTION apex_guard_financial_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'apex: financial snapshot % cannot be deleted', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status = 'active' AND NEW.status = 'superseded'
     AND OLD.superseded_at IS NULL AND NEW.superseded_at IS NOT NULL
     AND (to_jsonb(NEW) - 'status' - 'superseded_at') = (to_jsonb(OLD) - 'status' - 'superseded_at') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'apex: financial snapshot % is immutable (only active -> superseded is allowed)', OLD.id
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE TRIGGER financial_snapshots_guard
  BEFORE UPDATE OR DELETE ON financial_snapshots
  FOR EACH ROW EXECUTE FUNCTION apex_guard_financial_snapshot();
CREATE TRIGGER financial_snapshots_no_truncate
  BEFORE TRUNCATE ON financial_snapshots
  FOR EACH STATEMENT EXECUTE FUNCTION apex_forbid_mutation();

-- At most one active snapshot per tenant.
CREATE UNIQUE INDEX financial_snapshots_one_active_per_tenant
  ON financial_snapshots (tenant_id) WHERE status = 'active';

-- =============================================================================
-- Financial imports: the report is immutable. Status moves draft -> active | rejected and
-- active -> superseded. Only drafts may be deleted.
-- =============================================================================

CREATE FUNCTION apex_guard_financial_import() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.status = 'draft' THEN
      RETURN OLD;
    END IF;
    RAISE EXCEPTION 'apex: financial import % is % and cannot be deleted', OLD.id, OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'status') <> (to_jsonb(OLD) - 'status') THEN
    RAISE EXCEPTION 'apex: financial import % is immutable except its status', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF NEW.status = OLD.status
     OR (OLD.status = 'draft' AND NEW.status IN ('active', 'rejected'))
     OR (OLD.status = 'active' AND NEW.status = 'superseded') THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'apex: financial import % cannot go from % to %', OLD.id, OLD.status, NEW.status
    USING ERRCODE = 'integrity_constraint_violation';
END;
$$;

CREATE TRIGGER financial_imports_guard
  BEFORE UPDATE OR DELETE ON financial_imports
  FOR EACH ROW EXECUTE FUNCTION apex_guard_financial_import();

-- =============================================================================
-- Decisions: the canonical payload is immutable. Status moves pending_signature -> signed | rejected |
-- expired, and terminal decisions never change. Decisions are never deleted.
-- =============================================================================

CREATE FUNCTION apex_guard_decision() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'apex: decision % cannot be deleted', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF (to_jsonb(NEW) - 'status' - 'signed_at' - 'rejected_at')
     <> (to_jsonb(OLD) - 'status' - 'signed_at' - 'rejected_at') THEN
    RAISE EXCEPTION 'apex: decision % is immutable except status, signed_at and rejected_at', OLD.id
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  IF OLD.status <> 'pending_signature' THEN
    RAISE EXCEPTION 'apex: decision % is % and can no longer change', OLD.id, OLD.status
      USING ERRCODE = 'integrity_constraint_violation';
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER decisions_guard
  BEFORE UPDATE OR DELETE ON decisions
  FOR EACH ROW EXECUTE FUNCTION apex_guard_decision();
CREATE TRIGGER decisions_no_truncate
  BEFORE TRUNCATE ON decisions
  FOR EACH STATEMENT EXECUTE FUNCTION apex_forbid_mutation();

-- =============================================================================
-- CHECK constraints
-- =============================================================================

ALTER TABLE signing_keys
  ADD CONSTRAINT signing_keys_owner_consistent CHECK (
    (owner_type = 'human' AND user_id IS NOT NULL AND user_id = owner_id AND tenant_id IS NOT NULL)
    OR (owner_type = 'service' AND user_id IS NULL)
  ),
  ADD CONSTRAINT signing_keys_alg CHECK (alg = 'Ed25519');

ALTER TABLE signatures
  ADD CONSTRAINT signatures_human_has_session CHECK (
    signer_type <> 'human' OR (signing_session_id IS NOT NULL AND auth_at IS NOT NULL)
  ),
  ADD CONSTRAINT signatures_alg CHECK (alg = 'Ed25519'),
  ADD CONSTRAINT signatures_payload_hash_hex CHECK (payload_hash ~ '^[a-f0-9]{64}$');

ALTER TABLE decisions
  ADD CONSTRAINT decisions_required_signers CHECK (required_signers BETWEEN 1 AND 2),
  ADD CONSTRAINT decisions_payload_hash_hex CHECK (payload_hash ~ '^[a-f0-9]{64}$'),
  ADD CONSTRAINT decisions_status_timestamps CHECK (
    (status = 'signed') = (signed_at IS NOT NULL)
    AND (status = 'rejected') = (rejected_at IS NOT NULL)
  );

ALTER TABLE signing_sessions
  ADD CONSTRAINT signing_sessions_window CHECK (expires_at > auth_at),
  ADD CONSTRAINT signing_sessions_max_decisions CHECK (max_decisions >= 1);

ALTER TABLE audit_events
  ADD CONSTRAINT audit_events_seq_positive CHECK (seq >= 1);

ALTER TABLE fx_rates
  ADD CONSTRAINT fx_rates_positive CHECK (rate > 0),
  ADD CONSTRAINT fx_rates_distinct_pair CHECK (base <> quote);

ALTER TABLE financial_rows
  ADD CONSTRAINT financial_rows_period_format CHECK (period ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
  ADD CONSTRAINT financial_rows_one_value CHECK ((value_minor IS NULL) <> (value_bp IS NULL)),
  ADD CONSTRAINT financial_rows_currency_with_amount CHECK ((value_minor IS NULL) = (currency IS NULL)),
  ADD CONSTRAINT financial_rows_budget_has_category CHECK (metric <> 'budget' OR category IS NOT NULL);

ALTER TABLE seller_confidences
  ADD CONSTRAINT seller_confidences_score_range CHECK (score IS NULL OR score BETWEEN 0 AND 100),
  ADD CONSTRAINT seller_confidences_score_presence CHECK ((score IS NULL) = (band = 'insufficient_data'));

ALTER TABLE offers
  ADD CONSTRAINT offers_unit_price_non_negative CHECK (unit_price_minor >= 0),
  ADD CONSTRAINT offers_moq_positive CHECK (moq >= 1);

ALTER TABLE negotiation_outcomes
  ADD CONSTRAINT negotiation_outcomes_agreed_has_price CHECK (
    (outcome = 'agreed') = (final_price_minor IS NOT NULL)
  );

ALTER TABLE gate_queue_items
  ADD CONSTRAINT gate_queue_items_has_cause CHECK (cardinality(causes) >= 1),
  ADD CONSTRAINT gate_queue_items_resolution CHECK (
    (status = 'resolved') = (resolution IS NOT NULL AND resolved_at IS NOT NULL)
  );

ALTER TABLE tenant_config_versions
  ADD CONSTRAINT tenant_config_versions_positive CHECK (config_version >= 1);

ALTER TABLE financial_snapshots
  ADD CONSTRAINT financial_snapshots_superseded_at CHECK (
    (status = 'superseded') = (superseded_at IS NOT NULL)
  );

-- =============================================================================
-- LangGraph checkpointer schema (ADR-201). Its tables are created by the checkpointer's setup(), which
-- runs as a deploy step under the migrator role. Prisma does not manage anything inside this schema.
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS langgraph;
