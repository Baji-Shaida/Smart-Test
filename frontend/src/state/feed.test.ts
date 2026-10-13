import { describe, expect, it } from 'vitest'
import { applyEvent, initialFeed } from './feed'

describe('applyEvent', () => {
  it('appends logs and ignores replayed ids', () => {
    let s = applyEvent(initialFeed, { id: 1, event: 'log', data: { ts: 't', level: 'info', message: 'a' } })
    s = applyEvent(s, { id: 1, event: 'log', data: { ts: 't', level: 'info', message: 'a' } })
    s = applyEvent(s, { id: 2, event: 'log', data: { ts: 't', level: 'warn', message: 'b' } })
    expect(s.logs.map((l) => l.message)).toEqual(['a', 'b'])
    expect(s.lastId).toBe(2)
  })

  it('tracks stages, progress, statuses and completion', () => {
    let s = applyEvent(initialFeed, { id: 1, event: 'stage', data: { stage: 'parse', status: 'start' } })
    s = applyEvent(s, { id: 2, event: 'stage', data: { stage: 'parse', status: 'done' } })
    s = applyEvent(s, { id: 3, event: 'progress', data: { done: 1, total: 4 } })
    s = applyEvent(s, { id: 4, event: 'function_update', data: { function_id: 'a.py::f', status: 'possible_bug' } })
    s = applyEvent(s, { id: 5, event: 'generation_complete', data: { summary: {} } })
    expect(s.stages.parse).toBe('done')
    expect(s.progress).toEqual({ done: 1, total: 4 })
    expect(s.statuses['a.py::f']).toBe('possible_bug')
    expect(s.generationComplete).toBe(true)
    expect(s.refreshTick).toBe(2)
  })

  it('resets validate/report when a new generation starts', () => {
    let s = applyEvent(initialFeed, { id: 1, event: 'stage', data: { stage: 'report', status: 'done' } })
    s = applyEvent(s, { id: 2, event: 'stage', data: { stage: 'generate', status: 'start' } })
    expect(s.stages.report).toBeUndefined()
  })
})
