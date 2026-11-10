import { NextRequest } from 'next/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ signIn: vi.fn() }))

vi.mock('@/auth', () => ({ signIn: mocks.signIn }))

import { STEP_UP_ACR } from '@/lib/signing/step-up-acr'

import { GET } from './route'

const KEYCLOAK_REDIRECT =
  'http://localhost:8080/realms/apex/protocol/openid-connect/auth?client_id=apex-web'

function request(query: string) {
  return new NextRequest(`http://localhost:3000/api/auth/signin${query}`)
}

beforeEach(() => {
  mocks.signIn.mockReset()
  mocks.signIn.mockResolvedValue(KEYCLOAK_REDIRECT)
})

describe('GET /api/auth/signin', () => {
  it('forwards the step-up authorization parameters to Keycloak', async () => {
    const response = await GET(request('?stepUp=1&callbackUrl=%2Fes%2Fempresa%2Ffirma'))

    expect(mocks.signIn).toHaveBeenCalledExactlyOnceWith(
      'keycloak',
      { redirect: false, redirectTo: '/es/empresa/firma' },
      { acr_values: STEP_UP_ACR, max_age: '0', prompt: 'login' }
    )
    expect(response.status).toBe(302)
    expect(response.headers.get('location')).toBe(KEYCLOAK_REDIRECT)
  })

  it('keeps a normal sign-in free of step-up parameters', async () => {
    await GET(request('?callbackUrl=%2Fes%2Fdashboard'))

    expect(mocks.signIn).toHaveBeenCalledExactlyOnceWith('keycloak', {
      redirect: false,
      redirectTo: '/es/dashboard',
    })
  })

  it('refuses protocol-relative callback URLs and falls back to the root', async () => {
    await GET(request('?stepUp=1&callbackUrl=%2F%2Fevil.example'))

    expect(mocks.signIn).toHaveBeenCalledExactlyOnceWith(
      'keycloak',
      { redirect: false, redirectTo: '/' },
      { acr_values: STEP_UP_ACR, max_age: '0', prompt: 'login' }
    )
  })
})
