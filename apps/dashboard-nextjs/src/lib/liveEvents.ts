// Shared live-event bus for dashboard realtime updates.
// Fed by DashboardShell's WebSocket (/ws/dashboard) which forwards
// GlobalEventBus platform events from the FastAPI backend.

export interface LiveEvent {
  event: string
  data: Record<string, unknown>
  timestamp?: number
}

type LiveHandler = (evt: LiveEvent) => void

const handlers = new Set<LiveHandler>()

export function onLiveEvent(handler: LiveHandler): () => void {
  handlers.add(handler)
  return () => {
    handlers.delete(handler)
  }
}

export function emitLiveEvent(evt: LiveEvent): void {
  handlers.forEach((h) => {
    try {
      h(evt)
    } catch {
      // listener errors must not break the stream
    }
  })
}
