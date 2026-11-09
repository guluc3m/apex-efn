import {
  zEffectiveConfig,
  zMission,
  zOnboardingSession,
  zSigningSession,
  zSourcingRequest,
} from '@apex/shared-types/contracts/zod'
import { describe, expect, it } from 'vitest'

import {
  effectiveConfigFixture,
  missionFixture,
  onboardingSessionFixture,
  signingSessionFixture,
  sourcingRequestFixture,
} from './handlers'

// The contract has no examples yet, so the fixtures are validated against the generated schemas.
describe('MSW fixtures match the generated contract schemas', () => {
  it.each([
    ['SourcingRequest', zSourcingRequest, sourcingRequestFixture],
    ['Mission', zMission, missionFixture],
    ['EffectiveConfig', zEffectiveConfig, effectiveConfigFixture],
    ['SigningSession', zSigningSession, signingSessionFixture],
    ['OnboardingSession', zOnboardingSession, onboardingSessionFixture],
  ])('%s', (_name, schema, fixture) => {
    expect(schema.safeParse(fixture).success).toBe(true)
  })
})
