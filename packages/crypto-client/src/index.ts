/**
 * @apex/crypto-client
 *
 * Ed25519 signing in the browser using WebCrypto.
 * Private keys are generated as non-exportable and never leave the device.
 *
 * Implements section 5.10 of the spec.
 */

export { SigningClient, type SigningClientOptions } from './client.js'
export { CanonicalizationError, canonicalBytes, canonicalize } from './jcs.js'
export { payloadHash, sha256, sha256Hex } from './hash.js'
export type { SigningKey, Signature, SigningSession } from '@apex/shared-types/signing'
