import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { api } from '../api/client'
import { applyEvent, FeedState, initialFeed } from '../state/feed'
import type { ServerEvent } from '../types'

const EVENT_TYPES = ['log', 'stage', 'progress', 'function_update', 'analysis_complete', 'generation_complete', 'error']
const RUNNING = ['queued', 'analyzing', 'generating']

export type Connection = 'connecting' | 'live' | 'reconnecting' | 'idle'

type Action = { type: 'event'; ev: ServerEvent } | { type: 'reset' }

function reducer(state: FeedState, action: Action): FeedState {
  return action.type === 'reset' ? initialFeed : applyEvent(state, action.ev)
}

/**
 * Follows GET /api/jobs/{id}/events. The server replays everything after last_event_id and closes the
 * stream when the job is idle; we then check the job status and reconnect (with the last seen id) only
 * while a phase is running. Call `resume()` after starting a new phase.
 */
export function useEventStream(jobId: string | undefined) {
  const [feed, dispatch] = useReducer(reducer, initialFeed)
  const [connection, setConnection] = useState<Connection>('connecting')
  const lastIdRef = useRef(0)
  const esRef = useRef<EventSource | null>(null)
  const timerRef = useRef<number | null>(null)
  const aliveRef = useRef(true)

  lastIdRef.current = feed.lastId

  const close = () => {
    esRef.current?.close()
    esRef.current = null
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = null
  }

  const open = useCallback(() => {
    if (!jobId || !aliveRef.current) return
    close()
    const es = new EventSource(api.eventsUrl(jobId, lastIdRef.current))
    esRef.current = es
    es.onopen = () => setConnection('live')
    for (const type of EVENT_TYPES) {
      es.addEventListener(type, (e) => {
        const me = e as MessageEvent
        const id = Number(me.lastEventId)
        try {
          dispatch({ type: 'event', ev: { id, event: type, data: JSON.parse(me.data) } })
          lastIdRef.current = Math.max(lastIdRef.current, id)
        } catch {
          /* ignore malformed */
        }
      })
    }
    es.onerror = () => {
      es.close()
      if (esRef.current !== es) return
      esRef.current = null
      api
        .job(jobId)
        .then((job) => {
          if (!aliveRef.current) return
          if (RUNNING.includes(job.status) || job.last_event_id > lastIdRef.current) {
            setConnection('reconnecting')
            timerRef.current = window.setTimeout(open, 1000)
          } else {
            setConnection('idle')
          }
        })
        .catch(() => {
          if (!aliveRef.current) return
          setConnection('reconnecting')
          timerRef.current = window.setTimeout(open, 3000)
        })
    }
  }, [jobId])

  useEffect(() => {
    aliveRef.current = true
    dispatch({ type: 'reset' })
    lastIdRef.current = 0
    setConnection('connecting')
    open()
    return () => {
      aliveRef.current = false
      close()
    }
  }, [open])

  const resume = useCallback(() => {
    setConnection('connecting')
    open()
  }, [open])

  return { feed, connection, resume }
}
