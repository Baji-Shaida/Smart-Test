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

export async function getJson<T>(path: string): Promise<T> {
  return handle<T>(await fetch(`${API_BASE}${path}`))
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

export async function postForm<T>(path: string, form: FormData): Promise<T> {
  return handle<T>(await fetch(`${API_BASE}${path}`, { method: 'POST', body: form }))
}

export interface Health {
  status: string
  llm_provider: string
  ollama_reachable: boolean
  ollama_base_url: string
  model: string
  model_installed: boolean
  error: string | null
}

export const api = {
  health: () => getJson<Health>('/api/health'),
}
