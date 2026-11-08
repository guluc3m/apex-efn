import { steppingClock } from './clock.js'
import { buildServer, type MockMarketplace } from './server.js'

export const FIXED_START = new Date('2026-11-01T09:00:00.000Z')

export function testServer(seed = 42): MockMarketplace {
  return buildServer({ clock: steppingClock(FIXED_START), seed })
}
