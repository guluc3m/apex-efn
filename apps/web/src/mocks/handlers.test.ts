import {
  zEffectiveConfig,
  zMission,
  zNegotiationMessageTranslation,
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
  translationFixture,
} from './handlers'

// The contract has no examples yet, so the fixtures are validated against the generated schemas.
describe('MSW fixtures match the generated contract schemas', () => {
  it.each([
    ['SourcingRequest', zSourcingRequest, sourcingRequestFixture],
    ['Mission', zMission, missionFixture],
    ['EffectiveConfig', zEffectiveConfig, effectiveConfigFixture],
    ['SigningSession', zSigningSession, signingSessionFixture],
    ['NegotiationMessageTranslation', zNegotiationMessageTranslation, translationFixture],
    ['OnboardingSession', zOnboardingSession, onboardingSessionFixture],
  ])('%s', (_name, schema, fixture) => {
    expect(schema.safeParse(fixture).success).toBe(true)
  })
})
