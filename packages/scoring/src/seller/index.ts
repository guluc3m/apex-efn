/** Seller confidence (spec §3.4, D3-06). Preview mirror of `apex.domain.trust`; the API is authoritative. */
export {
  computeSellerConfidence,
  normalInvCdf,
  trustConfigFrom,
  TrustError,
  ENGINE_VERSION,
  RAW_SIGNALS,
  type Review,
  type TrustConfig,
  type TrustErrorCode,
} from './engine.js'
