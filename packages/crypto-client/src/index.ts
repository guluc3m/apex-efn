/**
 * @trato/crypto-client
 *
 * Ed25519 signing in the browser using WebCrypto.
 * Private keys are generated as non-exportable and never leave the device.
 *
 * Implements section 5.10 of the spec.
 */

export { SigningClient, type SigningClientOptions } from './client.js'
export { canonicalize } from './jcs.js'
export { sha256Hex } from './hash.js'
export type { SigningKey, Signature, SigningSession } from '@trato/shared-types/signing'
