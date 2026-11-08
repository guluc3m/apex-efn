export interface Clock {
  now(): Date
}

export const systemClock: Clock = { now: () => new Date() }

/** Deterministic clock for tests: starts at `start` and advances `stepMs` on every read. */
export function steppingClock(start: Date, stepMs = 1000): Clock {
  let t = start.getTime()
  return {
    now() {
      const d = new Date(t)
      t += stepMs
      return d
    },
  }
}
