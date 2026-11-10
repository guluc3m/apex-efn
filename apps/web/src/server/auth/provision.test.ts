import { describe, expect, it, vi } from 'vitest'

import { linkExternalSubject, type ExternalSubjectClient } from './provision'

interface Row {
  email: string
  externalSubject: string | null
}

/** In-memory stand-in for the only Prisma call the module makes. */
function fakeClient(rows: Row[]) {
  return {
    rows,
    user: {
      updateMany: vi.fn(
        ({
          where,
          data,
        }: {
          where: { email: string; externalSubject: null }
          data: { externalSubject: string }
        }) => {
          let count = 0
          for (const row of rows) {
            if (row.email === where.email && row.externalSubject === where.externalSubject) {
              row.externalSubject = data.externalSubject
              count += 1
            }
          }
          return Promise.resolve({ count })
        }
      ),
    },
  } satisfies ExternalSubjectClient & { rows: Row[] }
}

describe('linkExternalSubject', () => {
  it('links a matching email whose subject is still null', async () => {
    const client = fakeClient([{ email: 'buyer-a@apex.local', externalSubject: null }])

    await expect(
      linkExternalSubject({ sub: 'kc-sub-1', email: 'buyer-a@apex.local' }, client)
    ).resolves.toBe(1)

    expect(client.user.updateMany).toHaveBeenCalledWith({
      where: { email: 'buyer-a@apex.local', externalSubject: null },
      data: { externalSubject: 'kc-sub-1' },
    })
    expect(client.rows[0]?.externalSubject).toBe('kc-sub-1')
  })

  it('never overwrites a subject that is already linked', async () => {
    const client = fakeClient([{ email: 'buyer-a@apex.local', externalSubject: 'kc-sub-old' }])

    await expect(
      linkExternalSubject({ sub: 'kc-sub-new', email: 'buyer-a@apex.local' }, client)
    ).resolves.toBe(0)

    expect(client.rows[0]?.externalSubject).toBe('kc-sub-old')
  })

  it('does nothing when the user has no email', async () => {
    const client = fakeClient([{ email: 'buyer-a@apex.local', externalSubject: null }])

    await expect(linkExternalSubject({ sub: 'kc-sub-1', email: null }, client)).resolves.toBe(0)
    await expect(linkExternalSubject({ sub: 'kc-sub-1', email: '' }, client)).resolves.toBe(0)
    expect(client.user.updateMany).not.toHaveBeenCalled()
  })

  it('swallows a database failure so the login can continue', async () => {
    const client = fakeClient([])
    client.user.updateMany.mockRejectedValueOnce(new Error('connection refused'))
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    await expect(
      linkExternalSubject({ sub: 'kc-sub-1', email: 'buyer-a@apex.local' }, client)
    ).resolves.toBe(0)

    expect(error).toHaveBeenCalledOnce()
    error.mockRestore()
  })
})
