-- D2-08c (issue #346): network baseline of a signing session, "<country>|<asn>" from trusted proxy headers.
ALTER TABLE "signing_sessions" ADD COLUMN "network_ref" TEXT;
