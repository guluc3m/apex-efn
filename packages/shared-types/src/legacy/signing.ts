/**
 * @deprecated Hand-written DTO kept only so existing imports keep compiling.
 * Use the generated types from `@apex/shared-types/contracts` (source: contracts/openapi.yaml).
 * This folder is deleted once DEV-3 and DEV-5 migrate off it (D2-01 follow-up issues).
 */
import { z } from 'zod'

/**
 * Signing key owner type
 */
export const SigningKeyOwnerTypeSchema = z.enum(['human', 'service'])
export type SigningKeyOwnerType = z.infer<typeof SigningKeyOwnerTypeSchema>

/**
 * Signing key record
 */
export const SigningKeySchema = z.object({
  keyId: z.string(),
  ownerId: z.string(),
  ownerType: SigningKeyOwnerTypeSchema,
  publicKey: z.string(), // Base64-encoded Ed25519 public key
  alg: z.literal('Ed25519'),
  createdAt: z.string().datetime(),
  rotatedAt: z.string().datetime().nullable(),
  revokedAt: z.string().datetime().nullable(),
})
export type SigningKey = z.infer<typeof SigningKeySchema>

/**
 * Signing session (15-minute window per section 5.10.4)
 */
export const SigningSessionStatusSchema = z.enum(['active', 'expired', 'revoked', 'exhausted'])
export type SigningSessionStatus = z.infer<typeof SigningSessionStatusSchema>

export const SigningSessionSchema = z.object({
  sessionId: z.string(),
  userId: z.string(),
  keyId: z.string(),
  authMethod: z.enum(['webauthn', 'passkey']),
  authAt: z.string().datetime(),
  expiresAt: z.string().datetime(),
  deviceFingerprintRef: z.string(),
  decisionsSigned: z.array(z.string()),
  maxDecisions: z.number().int().positive(),
  status: SigningSessionStatusSchema,
  revokedReason: z.string().nullable(),
})
export type SigningSession = z.infer<typeof SigningSessionSchema>

/**
 * Decision types that require signing
 */
export const DecisionTypeSchema = z.enum([
  'follow',
  'renegotiate',
  'takeover',
  'hold',
  'discard',
  'approve_purchase',
  'activate_financial_snapshot',
  'override_discard',
  'change_pricing_threshold',
  'change_confidence_weights',
  'change_scoring_weights',
  'rotate_key',
  'revoke_key',
])
export type DecisionType = z.infer<typeof DecisionTypeSchema>

/**
 * Decision record (pending signature)
 */
export const DecisionSchema = z.object({
  id: z.string(),
  type: DecisionTypeSchema,
  subjectRef: z.string(),
  payloadCanonical: z.string(), // RFC 8785 JCS
  payloadHash: z.string(), // SHA-256 hex
  decidedBy: z.string(),
  status: z.enum(['pending_signature', 'signed', 'rejected']),
  createdAt: z.string().datetime(),
})
export type Decision = z.infer<typeof DecisionSchema>

/**
 * Signature record
 */
export const SignatureSchema = z.object({
  decisionId: z.string(),
  signerId: z.string(),
  keyId: z.string(),
  alg: z.literal('Ed25519'),
  payloadHash: z.string(),
  signature: z.string(), // Base64-encoded signature
  signedAt: z.string().datetime(),
  signingSessionId: z.string(),
  authAt: z.string().datetime(),
  prevSignatureHash: z.string().nullable(),
  clientAttestation: z.string().nullable(),
})
export type Signature = z.infer<typeof SignatureSchema>

/**
 * Decisions requiring immediate reauth per section 5.10.4
 */
export const IMMEDIATE_REAUTH_DECISIONS: DecisionType[] = [
  'activate_financial_snapshot',
  'change_pricing_threshold',
  'change_confidence_weights',
  'change_scoring_weights',
  'rotate_key',
  'revoke_key',
]
