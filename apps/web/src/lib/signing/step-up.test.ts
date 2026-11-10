import { afterEach, describe, expect, it, vi } from 'vitest'

import { setStepUp, startStepUp } from './step-up'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('startStepUp', () => {
  it('sends the browser to the sign-in entry with the step-up flag and the current page', async () => {
    const assign = vi.fn()
    vi.stubGlobal('window', {
      location: { pathname: '/es/empresa/firma', search: '?deal=7', assign },
    })

    await expect(startStepUp('step_up_required')).resolves.toBe(true)

    expect(assign).toHaveBeenCalledExactlyOnceWith(
      '/api/auth/signin?stepUp=1&callbackUrl=%2Fes%2Fempresa%2Ffirma%3Fdeal%3D7'
    )
  })

  it('fails closed outside a browser instead of pretending a step-up happened', async () => {
    await expect(startStepUp()).resolves.toBe(false)
  })

  it('fails closed when the browser refuses the navigation', async () => {
    vi.stubGlobal('window', {
      location: {
        pathname: '/es/empresa/firma',
        search: '',
        assign: () => {
          throw new Error('navigation blocked')
        },
      },
    })

    await expect(startStepUp()).resolves.toBe(false)
  })

  it('can be replaced (tests, alternative step-up flows)', async () => {
    setStepUp(() => Promise.resolve(true))
    await expect(startStepUp()).resolves.toBe(true)
  })
})
