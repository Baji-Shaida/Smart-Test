import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, Health } from '../api/client'
import ErrorBanner from '../components/ErrorBanner'
import type { Models } from '../types'

export default function HomePage() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<'zip' | 'url'>('zip')
  const [file, setFile] = useState<File | null>(null)
  const [url, setUrl] = useState('')
  const [drag, setDrag] = useState(false)
  const [models, setModels] = useState<Models | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [model, setModel] = useState('')
  const [maxFunctions, setMaxFunctions] = useState(10)
  const [threshold, setThreshold] = useState(60)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
    api
      .models()
      .then((m) => {
        setModels(m)
        setModel((cur) => cur || m.default)
      })
      .catch(() => setModels(null))
  }, [])

  const pick = (f: File | undefined | null) => {
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.zip')) {
      setError('Please choose a .zip file')
      return
    }
    setError(null)
    setFile(f)
  }

  const canSubmit = !busy && (mode === 'zip' ? !!file : url.trim().length > 0)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setError(null)
    const form = new FormData()
    if (mode === 'zip' && file) form.append('file', file)
    else form.append('repo_url', url.trim())
    form.append('settings', JSON.stringify({ model: model || undefined, max_functions: maxFunctions, coverage_threshold: threshold }))
    try {
      const { job_id } = await api.createJob(form)
      navigate(`/jobs/${job_id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const modelOptions = Array.from(new Set([...(models?.models ?? []), models?.default ?? 'qwen2.5-coder:7b']))
  const ollamaDown = health && health.llm_provider !== 'mock' && !health.ollama_reachable
  const modelMissing = health && health.llm_provider !== 'mock' && health.ollama_reachable && !health.model_installed

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Find untested code and let a local LLM write the tests</h2>
        <p className="mt-1 text-slate-600 dark:text-slate-400">
          Upload a Python project or paste a public GitHub URL. SmartTest measures coverage, ranks risky functions using git history
          and usage, generates pytest tests with Ollama, runs them and flags possible bugs.
        </p>
      </div>

      {ollamaDown && (
        <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          <strong>Ollama is not running</strong> at {health?.ollama_base_url}. Analysis still works, but test generation needs it. Start it with{' '}
          <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">ollama serve</code> and pull the model with{' '}
          <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">ollama pull {health?.model}</code>.
        </div>
      )}
      {modelMissing && (
        <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100">
          The default model <strong>{health?.model}</strong> is not installed. Run{' '}
          <code className="rounded bg-amber-100 px-1 dark:bg-amber-900">ollama pull {health?.model}</code> or pick an installed model below.
        </div>
      )}

      <form onSubmit={submit} className="space-y-5 rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div role="tablist" aria-label="Input type" className="inline-flex rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
          {(['zip', 'url'] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              onClick={() => setMode(m)}
              className={`rounded-md px-4 py-1.5 text-sm font-medium ${mode === m ? 'bg-white shadow dark:bg-slate-700' : 'text-slate-600 dark:text-slate-300'}`}
            >
              {m === 'zip' ? 'Upload zip' : 'GitHub URL'}
            </button>
          ))}
        </div>

        {mode === 'zip' ? (
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDrag(true)
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDrag(false)
              pick(e.dataTransfer.files?.[0])
            }}
            className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${
              drag ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40' : 'border-slate-300 dark:border-slate-700'
            }`}
          >
            <div className="text-3xl" aria-hidden>
              📦
            </div>
            {file ? (
              <p className="mt-2 text-sm">
                <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
              </p>
            ) : (
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">Drag and drop a .zip of a Python project here</p>
            )}
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              className="mt-3 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              {file ? 'Choose another file' : 'Browse…'}
            </button>
            <input ref={inputRef} type="file" accept=".zip,application/zip" className="sr-only" aria-label="Project zip file" onChange={(e) => pick(e.target.files?.[0])} />
            <p className="mt-3 text-xs text-slate-500">
              Tip: run <code>python scripts/create_sample_repo.py --zip</code> and upload <code>sample_repo.zip</code> for the demo.
            </p>
          </div>
        ) : (
          <label className="block">
            <span className="text-sm font-medium">Public GitHub repository URL</span>
            <input
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            />
            <span className="mt-1 block text-xs text-slate-500">Cloned with full history so recency can be scored.</span>
          </label>
        )}

        <details className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
          <summary className="cursor-pointer text-sm font-medium">Advanced settings</summary>
          <div className="mt-3 grid gap-4 sm:grid-cols-3">
            <label className="block text-sm">
              <span className="font-medium">Model</span>
              {models?.reachable && modelOptions.length > 0 ? (
                <select value={model} onChange={(e) => setModel(e.target.value)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-950">
                  {modelOptions.map((m) => (
                    <option key={m} value={m}>
                      {m}
                      {models.models.includes(m) ? '' : ' (not pulled)'}
                    </option>
                  ))}
                </select>
              ) : (
                <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="qwen2.5-coder:7b" className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-950" />
              )}
            </label>
            <label className="block text-sm">
              <span className="font-medium">Max functions</span>
              <input type="number" min={1} max={500} value={maxFunctions} onChange={(e) => setMaxFunctions(Number(e.target.value) || 1)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-950" />
            </label>
            <label className="block text-sm">
              <span className="font-medium">Coverage threshold (%)</span>
              <input type="number" min={1} max={100} value={threshold} onChange={(e) => setThreshold(Number(e.target.value) || 60)} className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-950" />
            </label>
          </div>
        </details>

        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        <button
          type="submit"
          disabled={!canSubmit}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-semibold text-white shadow hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Uploading…' : 'Analyze'}
        </button>
      </form>
      <p className="text-xs text-slate-500">
        Safety: uploaded code and generated tests are executed locally in subprocesses with timeouts. Only analyze code you trust.
      </p>
    </div>
  )
}
