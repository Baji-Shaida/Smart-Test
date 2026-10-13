import type { FunctionStatus, LogLine, ServerEvent, StageName } from '../types'

export const STAGES: { key: StageName; label: string }[] = [
  { key: 'parse', label: 'Parse' },
  { key: 'coverage', label: 'Coverage' },
  { key: 'prioritize', label: 'Prioritize' },
  { key: 'generate', label: 'Generate' },
  { key: 'validate', label: 'Validate' },
  { key: 'report', label: 'Report' },
]

export interface FeedState {
  lastId: number
  logs: LogLine[]
  stages: Partial<Record<StageName, 'start' | 'done'>>
  progress: { done: number; total: number }
  statuses: Record<string, FunctionStatus>
  error: { message: string; recoverable: boolean } | null
  analysisComplete: boolean
  generationComplete: boolean
  /** Bumped on events after which the page should re-fetch job/functions/summary. */
  refreshTick: number
}

export const initialFeed: FeedState = {
  lastId: 0,
  logs: [],
  stages: {},
  progress: { done: 0, total: 0 },
  statuses: {},
  error: null,
  analysisComplete: false,
  generationComplete: false,
  refreshTick: 0,
}

/** Apply one SSE event. Events with an id we have already seen are ignored (replay after reconnect). */
export function applyEvent(state: FeedState, ev: ServerEvent): FeedState {
  if (ev.id <= state.lastId) return state
  const s: FeedState = { ...state, lastId: ev.id }
  const d = ev.data
  switch (ev.event) {
    case 'log':
      s.logs = [...state.logs, { id: ev.id, ts: String(d.ts), level: d.level as LogLine['level'], message: String(d.message) }]
      break
    case 'stage': {
      const stage = d.stage as StageName
      const status = d.status as 'start' | 'done'
      const stages = { ...state.stages, [stage]: status }
      if (stage === 'generate' && status === 'start') {
        delete stages.validate
        delete stages.report
        s.generationComplete = false
        s.error = null
      }
      s.stages = stages
      break
    }
    case 'progress':
      s.progress = { done: Number(d.done), total: Number(d.total) }
      break
    case 'function_update':
      s.statuses = { ...state.statuses, [String(d.function_id)]: d.status as FunctionStatus }
      s.refreshTick = state.refreshTick + 1
      break
    case 'analysis_complete':
      s.analysisComplete = true
      s.refreshTick = state.refreshTick + 1
      break
    case 'generation_complete':
      s.generationComplete = true
      s.refreshTick = state.refreshTick + 1
      break
    case 'error':
      s.error = { message: String(d.message), recoverable: Boolean(d.recoverable) }
      s.refreshTick = state.refreshTick + 1
      break
  }
  return s
}

export function formatTime(ts: string): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
