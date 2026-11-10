/**
 * Linking a Keycloak user to the local `users` row on first sign-in (issue #270).
 *
 * The seed creates users with `email` and leaves `external_subject` null. The first time a user
 * signs in, the Auth.js `jwt` callback writes the token `sub` into that column once. The update is
 * conditional on `external_subject` still being null, so an existing link is never overwritten: a
 * different Keycloak subject that claims the same email cannot take over the account.
 *
 * Timing and RLS: this runs during sign-in, **before** any tenant context exists, under the web
 * app's owner DSN. Row-level security is therefore not in play here; see `docs/security/rbac.md`.
 * Once DEV-2/DEV-6's Prisma tenant extension is used by the web app, this call must move to a
 * bootstrap/admin path explicitly documented as pre-tenant, because `tenant_session()` fails closed
 * without `app.tenant_id`.
 */

/** The tiny slice of the Prisma client this module needs, so tests inject a fake without a DB. */
export interface ExternalSubjectClient {
  user: {
    updateMany(args: {
      where: { email: string; externalSubject: null }
      data: { externalSubject: string }
    }): Promise<{ count: number }>
  }
}

export interface ExternalSubjectLink {
  sub: string
  email: string | null | undefined
}

let defaultClient: ExternalSubjectClient | null = null

/**
 * Registers the process-wide Prisma client. Called once from the Node.js instrumentation hook
 * (`src/instrumentation.ts`), which is the only place allowed to import `@prisma/client`: the
 * Auth.js config is also part of the edge middleware bundle, and Prisma cannot run there. Tests
 * inject a fake client per call instead.
 */
export function setDefaultExternalSubjectClient(client: ExternalSubjectClient | null): void {
  defaultClient = client
}

/**
 * Sets `users.external_subject = sub` when `email` matches a row whose subject is still null.
 * Returns the number of rows updated (0 when there is nothing to link).
 *
 * Never throws: a database or configuration failure must not block a login. The failure is logged
 * without the email or the subject (no PII in logs) and the session continues with the token as
 * the only source of identity.
 */
export async function linkExternalSubject(
  { sub, email }: ExternalSubjectLink,
  client?: ExternalSubjectClient
): Promise<number> {
  if (!sub || !email) return 0
  const prisma = client ?? defaultClient
  if (!prisma) {
    // No client registered (instrumentation did not run or no DATABASE_URL). The login continues.
    console.warn('[auth] no database client registered; skipping the external subject link')
    return 0
  }
  try {
    const { count } = await prisma.user.updateMany({
      where: { email, externalSubject: null },
      data: { externalSubject: sub },
    })
    return count
  } catch (error) {
    const reason = error instanceof Error ? error.message : 'unknown error'
    console.error('[auth] could not link the external subject on sign-in:', reason)
    return 0
  }
}
