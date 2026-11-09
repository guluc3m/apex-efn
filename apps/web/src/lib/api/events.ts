import type { MissionEvent } from '@apex/shared-types/contracts'

import { BFF_PREFIX } from './client'

export interface MissionEventsHandle {
  close: () => void
}

/**
 * Subscribes to `GET /v1/missions/{id}/events` through the BFF (SSE passthrough).
 *
 * The browser reconnects by itself and replays from `Last-Event-ID`; the orchestrator closes the
 * stream when planning ends, so `onError` fires on every normal close as well.
 */
export function subscribeMissionEvents(
  missionId: string,
  handlers: { onEvent: (event: MissionEvent) => void; onError?: (event: Event) => void },
  factory: (url: string) => EventSource = (url) => new EventSource(url),
): MissionEventsHandle {
  const source = factory(`${BFF_PREFIX}/v1/missions/${encodeURIComponent(missionId)}/events`)
  source.onmessage = (message: MessageEvent<string>) => {
    handlers.onEvent(JSON.parse(message.data) as MissionEvent)
  }
  // The SSE `event:` field equals the event type, so named events need explicit listeners.
  source.addEventListener('error', (event) => handlers.onError?.(event))
  return { close: () => source.close() }
}
