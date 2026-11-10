import NextAuth from 'next-auth'

import { authConfig } from '@/server/auth/config'

const nextAuth = NextAuth(authConfig)

/**
 * Auth.js v5 entry point (D1-05b). Sessions are stateless JWTs in an httpOnly cookie; the raw
 * Keycloak tokens never leave this cookie and are read server-side only (`getAccessToken`).
 */
export const handlers = nextAuth.handlers
export const auth = nextAuth.auth
export const signOut = nextAuth.signOut

/**
 * Narrow, portable signature. Auth.js types `signIn` against a `ProviderId` union that lives in a
 * transitive package, so re-exporting the inferred type breaks declaration emit (TS2742).
 */
export type SignInFn = (
  provider: string,
  options?: { redirect?: boolean; redirectTo?: string } & Record<string, unknown>
) => Promise<unknown>

export const signIn: SignInFn = nextAuth.signIn
