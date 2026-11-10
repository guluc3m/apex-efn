-- ADR-209: one name per decision type, matching what DEV-4 calls (#92).
ALTER TYPE "DecisionType" RENAME VALUE 'activate_financial_snapshot' TO 'financial_snapshot_activation';
ALTER TYPE "DecisionType" RENAME VALUE 'override_discard' TO 'gate_override_discard';
ALTER TYPE "DecisionType" RENAME VALUE 'unblock' TO 'gate_unblock';
ALTER TYPE "DecisionType" ADD VALUE 'deal_action';
ALTER TYPE "DecisionType" ADD VALUE 'service_event';
