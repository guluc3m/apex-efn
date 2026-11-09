import { PrismaClient } from '@prisma/client'
import { afterAll, describe, expect, it } from 'vitest'

import { forTenant } from './tenant-extension'

// A database migrated and seeded (`prisma migrate deploy && prisma db seed`), reached through a login role that
// is a member of `apex_app`. Without it the database checks are skipped.
const appDatabaseUrl = process.env.APEX_TEST_APP_DATABASE_URL

describe('forTenant', () => {
  it('rejects an empty tenant', () => {
    const prisma = new PrismaClient({ datasourceUrl: 'postgresql://unused@localhost:1/unused' })
    expect(() => forTenant(prisma, '')).toThrow('non-empty')
    expect(() => forTenant(prisma, '   ')).toThrow('non-empty')
  })
})

describe.skipIf(!appDatabaseUrl)('forTenant against Postgres', () => {
  const prisma = new PrismaClient({ datasourceUrl: appDatabaseUrl })
  afterAll(async () => {
    await prisma.$disconnect()
  })

  it('sees only the rows of its tenant', async () => {
    const a = await forTenant(prisma, 'tenant-a').membership.findMany({
      select: { tenantId: true },
    })
    const b = await forTenant(prisma, 'tenant-b').membership.findMany({
      select: { tenantId: true },
    })
    expect(a.length).toBeGreaterThan(0)
    expect(new Set(a.map((m) => m.tenantId))).toEqual(new Set(['tenant-a']))
    expect(new Set(b.map((m) => m.tenantId))).toEqual(new Set(['tenant-b']))
  })

  it('sees nothing without a tenant', async () => {
    expect(await prisma.membership.count()).toBe(0)
    expect(await prisma.tenant.count()).toBe(0)
  })

  it('cannot write rows for another tenant', async () => {
    await expect(
      forTenant(prisma, 'tenant-b').tenant.update({
        where: { id: 'tenant-a' },
        data: { name: 'renamed' },
      })
    ).rejects.toThrow()
  })
})
