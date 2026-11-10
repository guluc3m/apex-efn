import type { MissionEvent, MissionState } from '@apex/shared-types/contracts'

export type PhaseId = 'search' | 'filter' | 'negotiation' | 'valuation'
export type PhaseState = 'done' | 'running' | 'pending'

export const PHASES: readonly PhaseId[] = ['search', 'filter', 'negotiation', 'valuation']

/** Index of the phase a mission state is in. `null`: the mission is over without finishing (no phase runs). */
const RUNNING: Record<MissionState, number | null> = {
  created: 0,
  planning: 0,
  sourcing: 0,
  enriching: 0,
  evaluating: 1,
  negotiating: 2,
  awaiting_decision: 3,
  completed: PHASES.length,
  cancelled: null,
  failed: null,
}

/** Display-only mapping of the API state onto the four phase tiles. */
export function phaseStates(state: MissionState): PhaseState[] {
  const at = RUNNING[state]
  return PHASES.map((_, i) => (at === null ? 'pending' : i < at ? 'done' : i === at ? 'running' : 'pending'))
}

export const MAX_EVENTS = 50

/** Newest first, no keepalives, no duplicates (the browser replays from Last-Event-ID), capped. */
export function pushEvent(events: readonly MissionEvent[], event: MissionEvent): MissionEvent[] {
  if (event.type === 'keepalive' || events.some((e) => e.id === event.id)) return events.slice()
  return [event, ...events].slice(0, MAX_EVENTS)
}
