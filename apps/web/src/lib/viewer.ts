import { getSession } from '@/server/auth/session'
import { ROLES, type Role } from '@/server/auth/types'

export interface Viewer {
  role: Role
  userId: string | null
  tenantId: string | null
}

/** Highest-privilege role of the session (ROLES is ordered most to least). No session or no role means viewer, which never signs. */
export async function getViewer(): Promise<Viewer> {
  const session = await getSession()
  const roles = session?.user.roles ?? []
  return { userId: session?.user_id ?? null, role: ROLES.find((r) => roles.includes(r)) ?? 'viewer', tenantId: session?.user.tenantId ?? null }
}
