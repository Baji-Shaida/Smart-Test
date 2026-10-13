import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { FunctionRecord, JobState, Summary } from '../types'
import { Connection, useEventStream } from './useEventStream'
import type { FeedState } from '../state/feed'

interface JobCtx {
  jobId: string
  job: JobState | null
  functions: FunctionRecord[] | null
  summary: Summary | null
  feed: FeedState
  connection: Connection
  loadError: string | null
  running: boolean
  refresh: () => void
  generate: (body: { function_ids?: string[]; all?: boolean }) => Promise<void>
}

const Ctx = createContext<JobCtx | null>(null)

export function JobProvider({ jobId, children }: { jobId: string; children: React.ReactNode }) {
  const { feed, connection, resume } = useEventStream(jobId)
  const [job, setJob] = useState<JobState | null>(null)
  const [functions, setFunctions] = useState<FunctionRecord[] | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  const refresh = useCallback(() => {
    Promise.all([api.job(jobId), api.functions(jobId), api.summary(jobId)])
      .then(([j, f, s]) => {
        setJob(j)
        setFunctions(f)
        setSummary(s)
        setLoadError(null)
      })
      .catch((e) => setLoadError(e.message))
  }, [jobId])

  useEffect(() => {
    setJob(null)
    setFunctions(null)
    setSummary(null)
    refresh()
  }, [refresh])

  // Re-fetch (debounced) whenever the stream reports something that changes job data.
  useEffect(() => {
    if (feed.refreshTick === 0) return
    if (timer.current) window.clearTimeout(timer.current)
    timer.current = window.setTimeout(refresh, 250)
  }, [feed.refreshTick, refresh])

  // Keep the job status in sync with stage events (cheap).
  useEffect(() => {
    if (feed.lastId === 0) return
    api.job(jobId).then(setJob).catch(() => {})
  }, [feed.stages, jobId])

  const generate = useCallback(
    async (body: { function_ids?: string[]; all?: boolean }) => {
      await api.generate(jobId, body)
      setJob((j) => (j ? { ...j, status: 'generating' } : j))
      resume()
    },
    [jobId, resume],
  )

  const running = !!job && ['queued', 'analyzing', 'generating'].includes(job.status)

  return (
    <Ctx.Provider value={{ jobId, job, functions, summary, feed, connection, loadError, running, refresh, generate }}>
      {children}
    </Ctx.Provider>
  )
}

export function useJob(): JobCtx {
  const c = useContext(Ctx)
  if (!c) throw new Error('useJob outside JobProvider')
  return c
}

/** Live status: prefer the SSE value, fall back to the fetched record. */
export function liveStatus(f: FunctionRecord, feed: FeedState) {
  return feed.statuses[f.id] ?? f.status
}
