import type { MissionEvent } from '@apex/shared-types/contracts'
import { describe, expect, it } from 'vitest'

import { MAX_EVENTS, phaseStates, pushEvent } from './missions'

const ev = (id: string, type: MissionEvent['type'] = 'state_changed'): MissionEvent => ({ id, mission_id: 'm', type, at: '2026-11-10T10:00:00Z' })

describe('phaseStates', () => {
  it('marks earlier phases done and the current one running', () => {
    expect(phaseStates('negotiating')).toEqual(['done', 'done', 'running', 'pending'])
    expect(phaseStates('sourcing')).toEqual(['running', 'pending', 'pending', 'pending'])
  })
  it('finishes everything on completed and nothing on cancelled', () => {
    expect(phaseStates('completed')).toEqual(['done', 'done', 'done', 'done'])
    expect(phaseStates('cancelled')).toEqual(['pending', 'pending', 'pending', 'pending'])
  })
})

describe('pushEvent', () => {
  it('puts the newest first and drops keepalives and replays', () => {
    let list = pushEvent([], ev('1'))
    list = pushEvent(list, ev('2'))
    list = pushEvent(list, ev('2'))
    list = pushEvent(list, ev('3', 'keepalive'))
    expect(list.map((e) => e.id)).toEqual(['2', '1'])
  })
  it('caps the list', () => {
    let list: MissionEvent[] = []
    for (let i = 0; i < MAX_EVENTS + 5; i++) list = pushEvent(list, ev(String(i)))
    expect(list).toHaveLength(MAX_EVENTS)
  })
})
