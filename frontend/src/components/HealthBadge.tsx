import { useEffect, useState } from 'react'
import { api, Health } from '../api/client'

export default function HealthBadge() {
  const [health, setHealth] = useState<Health | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    const load = () =>
      api
        .health()
        .then((h) => alive && (setHealth(h), setError(null)))
        .catch((e) => alive && setError(String(e.message || e)))
    load()
    const t = setInterval(load, 15000)
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  let label = 'Checking...'
  let cls = 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
  let title = ''
  if (error) {
    label = 'Backend offline'
    cls = 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200'
    title = error
  } else if (health) {
    if (health.llm_provider === 'mock') {
      label = 'Mock LLM'
      cls = 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200'
      title = 'LLM_PROVIDER=mock: deterministic canned tests'
    } else if (health.ollama_reachable) {
      label = `Ollama: ${health.model}${health.model_installed ? '' : ' (not pulled)'}`
      cls = health.model_installed
        ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200'
        : 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200'
      title = health.model_installed ? 'Ollama reachable' : `Run: ollama pull ${health.model}`
    } else {
      label = 'Ollama offline'
      cls = 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200'
      title = 'Start Ollama with `ollama serve`'
    }
  }
  return (
    <span
      role="status"
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${cls}`}
    >
      <span aria-hidden className="h-2 w-2 rounded-full bg-current opacity-70" />
      {label}
    </span>
  )
}
