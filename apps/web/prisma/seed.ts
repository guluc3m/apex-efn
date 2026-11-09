// Development seed (D2-03): the two tenants and ten users of the Keycloak realm (infra/keycloak/realm-apex.json).
// Tenant IDs match the `tenant_id` claim. Users are matched to Keycloak by email; `external_subject` is filled on
// first sign-in. Tenant configuration is not seeded here: `python -m apex.tenant_config.load_defaults` runs after
// this script (D4-03). The seed is idempotent and uses a fixed timestamp, so reruns produce the same rows.
import { PrismaClient, type Currency, type Role } from '@prisma/client'

const SEEDED_AT = new Date('2026-01-01T00:00:00.000Z')
const ROLES: readonly Role[] = ['owner', 'admin', 'buyer', 'finance', 'viewer']

interface SeedTenant {
  id: string
  suffix: string
  name: string
  country: string
  baseCurrency: Currency
}

const TENANTS: readonly SeedTenant[] = [
  { id: 'tenant-a', suffix: 'a', name: 'Tenant A (dev)', country: 'ES', baseCurrency: 'EUR' },
  { id: 'tenant-b', suffix: 'b', name: 'Tenant B (dev)', country: 'ES', baseCurrency: 'EUR' },
]

async function main(): Promise<void> {
  const prisma = new PrismaClient()
  try {
    for (const tenant of TENANTS) {
      await prisma.tenant.upsert({
        where: { id: tenant.id },
        update: {},
        create: {
          id: tenant.id,
          name: tenant.name,
          country: tenant.country,
          baseCurrency: tenant.baseCurrency,
          createdAt: SEEDED_AT,
          updatedAt: SEEDED_AT,
        },
      })
      for (const role of ROLES) {
        const email = `${role}-${tenant.suffix}@apex.local`
        const userId = `user-${role}-${tenant.suffix}`
        await prisma.user.upsert({
          where: { email },
          update: {},
          create: {
            id: userId,
            email,
            displayName: `${role} ${tenant.suffix.toUpperCase()}`,
            createdAt: SEEDED_AT,
            updatedAt: SEEDED_AT,
          },
        })
        await prisma.membership.upsert({
          where: { tenantId_userId: { tenantId: tenant.id, userId } },
          update: {},
          create: {
            id: `membership-${role}-${tenant.suffix}`,
            tenantId: tenant.id,
            userId,
            role,
            createdAt: SEEDED_AT,
          },
        })
      }
    }
  } finally {
    await prisma.$disconnect()
  }
}

main().catch((error: unknown) => {
  console.error(error)
  process.exit(1)
})
