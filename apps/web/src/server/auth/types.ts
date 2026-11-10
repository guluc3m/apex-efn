import type { DefaultSession } from 'next-auth'

/**
 * Roles the platform understands (closed set). Unknown roles a Keycloak token may carry
 * (`offline_access`, `uma_authorization`, client roles) are dropped before they reach the UI or
 * the BFF. `viewer` never signs (see docs/security/rbac.md).
 */
export const ROLES = ['owner', 'admin', 'buyer', 'finance', 'viewer'] as const
export type Role = (typeof ROLES)[number]

const ROLE_SET: ReadonlySet<string> = new Set(ROLES)

/** Keeps only known roles, de-duplicated, preserving the issuer's order. */
export function toRoles(value: unknown): Role[] {
  if (!Array.isArray(value)) return []
  const out: Role[] = []
  for (const item of value) {
    if (typeof item === 'string' && ROLE_SET.has(item) && !out.includes(item as Role)) {
      out.push(item as Role)
    }
  }
  return out
}

/** Claims Auth.js copies from the Keycloak ID token (`profile`). */
export interface KeycloakClaims {
  sub?: string
  email?: string
  tenant_id?: string
  roles?: unknown
  auth_time?: number
}

/**
 * What the browser is allowed to see. Tokens live only in the encrypted, httpOnly Auth.js cookie
 * and in the JWT; they are never copied into this object (D1-05b design item 2).
 */
export interface WebSessionUser {
  /** Keycloak `sub`. Kept for compatibility; the same value is exposed as `WebSession.user_id`. */
  id: string
  /** Keycloak `sub` in the flat shape DEV-6 consumes. Equal to `user.id`. */
  user_id: string
  tenantId: string | null
  roles: Role[]
  authTime: number | null
}

export interface WebSession {
  /** Keycloak `sub` of the signed-in user. Flat alias of `user.id` (DEV-6 contract). */
  user_id: string
  user: WebSessionUser
}

declare module 'next-auth' {
  interface Session {
    user: WebSessionUser
  }

  interface User {
    tenantId?: string
    roles?: Role[]
    authTime?: number
  }
}

// Kept so `DefaultSession` is part of the module graph of this augmentation file.
export type SessionUser = WebSessionUser & DefaultSession['user']
