import type { FunctionRecord, JobState, Models, Summary } from '../types'

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? ''

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const body = await res.json()
      msg = body.error || body.detail || msg
    } catch {
      /* ignore */
    }
    throw new ApiError(msg, res.status)
  }
  return res.json() as Promise<T>
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch {
    throw new ApiError('Cannot reach the SmartTest backend. Is it running on port 8000?', 0)
  }
  return handle<T>(res)
}

export const getJson = <T>(path: string) => request<T>(path)

export const postJson = <T>(path: string, body: unknown) =>
  request<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const postForm = <T>(path: string, form: FormData) => request<T>(path, { method: 'POST', body: form })

export interface Health {
  status: string
  llm_provider: string
  ollama_reachable: boolean
  ollama_base_url: string
  model: string
  model_installed: boolean
  error: string | null
}

const enc = encodeURIComponent

export const api = {
  health: () => getJson<Health>('/api/health'),
  models: () => getJson<Models>('/api/models'),
  createJob: (form: FormData) => postForm<{ job_id: string }>('/api/jobs', form),
  job: (id: string) => getJson<JobState>(`/api/jobs/${enc(id)}`),
  functions: (id: string) => getJson<FunctionRecord[]>(`/api/jobs/${enc(id)}/functions`),
  func: (id: string, fid: string) => getJson<FunctionRecord>(`/api/jobs/${enc(id)}/functions/${enc(fid)}`),
  summary: (id: string) => getJson<Summary>(`/api/jobs/${enc(id)}/summary`),
  generate: (id: string, body: { function_ids?: string[]; all?: boolean }) =>
    postJson<{ function_ids: string[] }>(`/api/jobs/${enc(id)}/generate`, body),
  eventsUrl: (id: string, lastId: number) => `${API_BASE}/api/jobs/${enc(id)}/events?last_event_id=${lastId}`,
  reportUrl: (id: string) => `${API_BASE}/api/jobs/${enc(id)}/report.pdf`,
  testsZipUrl: (id: string) => `${API_BASE}/api/jobs/${enc(id)}/tests.zip`,
}
