// Tenant-scoped Prisma client (D2-04, ADR-206). Row-level security reads the tenant from the transaction-local
// setting `app.tenant_id`, so every query runs in a batch transaction that sets it first. Without the setting,
// tenant rows are invisible and cannot be written.
//
// Business data is served by the orchestrator (ADR-202); this helper exists for the few web-side reads that need
// the database directly, and for scripts. The client must connect as a member of `apex_app`: the migrator and
// superusers bypass RLS.
import type { PrismaClient } from '@prisma/client'

export function forTenant(prisma: PrismaClient, tenantId: string) {
  if (tenantId.trim() === '') {
    throw new Error('forTenant needs a non-empty tenantId')
  }
  return prisma.$extends({
    name: 'apex-tenant',
    query: {
      $allModels: {
        async $allOperations({ args, query }) {
          const [, result] = await prisma.$transaction([
            prisma.$executeRaw`SELECT set_config('app.tenant_id', ${tenantId}, true)`,
            query(args),
          ])
          return result
        },
      },
    },
  })
}
