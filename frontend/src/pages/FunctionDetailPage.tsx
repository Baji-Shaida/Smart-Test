import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import CodePanel, { Code, CopyButton } from '../components/CodePanel'
import ErrorBanner, { EmptyState, Spinner } from '../components/ErrorBanner'
import StatusChip, { RiskBadge } from '../components/StatusChip'
import { liveStatus, useJob } from '../hooks/useJob'
import type { FunctionRecord, TestRecord } from '../types'

export function BugBlock({ test }: { test: TestRecord }) {
  return (
    <section aria-label="Possible bug details" className="rounded-xl border-2 border-orange-400 bg-orange-50 p-4 dark:border-orange-700 dark:bg-orange-950/40">
      <h3 className="flex items-center gap-2 font-semibold text-orange-800 dark:text-orange-200">
        <span aria-hidden>⚠</span> Possible bug found by <code className="font-mono text-sm">{test.name}</code>
      </h3>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-xs font-semibold uppercase text-orange-700 dark:text-orange-300">Expected</dt>
          <dd className="mt-0.5 rounded bg-white px-2 py-1 font-mono dark:bg-slate-900">{test.expected ?? '—'}</dd>
        </div>
        <div>
          <dt className="text-xs font-semibold uppercase text-orange-700 dark:text-orange-300">Actual</dt>
          <dd className="mt-0.5 rounded bg-white px-2 py-1 font-mono dark:bg-slate-900">{test.actual ?? '—'}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-xs font-semibold uppercase text-orange-700 dark:text-orange-300">Why the LLM thinks this is a bug</dt>
          <dd className="mt-0.5">{test.verdict?.reason || test.reason}</dd>
        </div>
      </dl>
      {test.traceback && (
        <details className="mt-3" open>
          <summary className="cursor-pointer text-xs font-semibold uppercase text-orange-700 dark:text-orange-300">Traceback (trimmed)</summary>
          <pre className="mt-1 max-h-64 overflow-auto rounded bg-slate-950 p-3 font-mono text-xs text-slate-200">{test.traceback}</pre>
        </details>
      )}
      <p className="mt-3 text-xs text-orange-800 dark:text-orange-300">"Possible bug" means worth a human look, not proof of a bug.</p>
    </section>
  )
}

export default function FunctionDetailPage() {
  const { fid = '' } = useParams()
  const { jobId, job, feed, running, generate } = useJob()
  const navigate = useNavigate()
  const [fn, setFn] = useState<FunctionRecord | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState(0)
  const [busy, setBusy] = useState(false)
  const statusTick = feed.statuses[fid]

  useEffect(() => {
    api
      .func(jobId, fid)
      .then((f) => {
        setFn(f)
        setError(null)
        const order = ['possible_bug', 'needs_review', 'rejected', 'accepted']
        const tests = f.tests as TestRecord[]
        const best = order.map((st) => tests.findIndex((t) => t.status === st)).find((i) => i >= 0)
        setTab(best ?? 0)
      })
      .catch((e) => setError(e.message))
  }, [jobId, fid, statusTick])

  if (error) return <ErrorBanner message={error} />
  if (!fn) return <Spinner label="Loading function…" />

  const tests = (fn.tests as TestRecord[]).filter((t) => t.code !== undefined)
  const current = tests[Math.min(tab, Math.max(tests.length - 1, 0))]
  const status = liveStatus(fn, feed)
  const canRegen = !!job && ['analyzed', 'completed'].includes(job.status) && !running && !busy

  const regenerate = async () => {
    setBusy(true)
    try {
      await generate({ function_ids: [fn.id] })
      navigate(`/jobs/${jobId}/generate`)
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to={`/jobs/${jobId}`} className="text-xs text-indigo-700 hover:underline dark:text-indigo-300">
            ← Back to analysis
          </Link>
          <h3 className="mt-1 flex flex-wrap items-center gap-2 text-lg font-semibold">
            <span className="font-mono">{fn.qualname}</span> <StatusChip status={status} />
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            coverage {Math.round(fn.coverage_pct)}%{fn.coverage_after_pct != null ? ` → ${Math.round(fn.coverage_after_pct)}%` : ''} · risk{' '}
            <RiskBadge label={fn.risk_label} /> · used {fn.usage_count ?? 0}× · changed {fn.last_modified_days ?? '—'} days ago
            {fn.attempts ? ` · ${fn.attempts} attempt(s)` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={regenerate}
          disabled={!canRegen}
          className="rounded-lg border border-indigo-600 px-3 py-1.5 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-indigo-300 dark:hover:bg-indigo-950"
        >
          {busy ? 'Starting…' : 'Regenerate'}
        </button>
      </div>

      {fn.error && <ErrorBanner message={fn.error} />}

      <div className="grid gap-4 lg:grid-cols-2">
        <CodePanel
          title={<span className="font-mono">{fn.file}</span>}
          subtitle={`lines ${fn.line_start}-${fn.line_end} · ${fn.signature}`}
          actions={<CopyButton text={fn.source ?? ''} />}
        >
          <Code code={fn.source ?? ''} startingLineNumber={fn.line_start} />
        </CodePanel>
        <CodePanel
          title={current ? <span className="font-mono">{current.name}</span> : 'Generated test'}
          subtitle={current ? current.reason : undefined}
          actions={
            current && (
              <>
                <StatusChip status={current.status} small />
                <CopyButton text={current.code} label="Copy test" />
              </>
            )
          }
        >
          {tests.length > 1 && (
            <div role="tablist" aria-label="Generated tests" className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-2 pt-2 dark:border-slate-800 dark:bg-slate-900">
              {tests.map((t, i) => (
                <button
                  key={t.name + i}
                  role="tab"
                  type="button"
                  aria-selected={i === tab}
                  onClick={() => setTab(i)}
                  className={`whitespace-nowrap rounded-t-md border-b-2 px-2 py-1 font-mono text-xs ${
                    i === tab ? 'border-indigo-500 text-indigo-700 dark:text-indigo-300' : 'border-transparent text-slate-500'
                  }`}
                >
                  <span aria-hidden className="mr-1">
                    {t.status === 'accepted' ? '✓' : t.status === 'possible_bug' ? '⚠' : t.status === 'needs_review' ? '?' : '×'}
                  </span>
                  {t.name.replace(/^test_/, '')}
                </button>
              ))}
            </div>
          )}
          {current ? (
            <Code code={current.code || '# no code'} />
          ) : (
            <div className="p-4">
              <EmptyState title={status === 'generating' ? 'Generating…' : 'No generated tests yet'}>
                {status === 'generating' ? 'Watch the live feed on the Generation tab.' : 'Select this function and press Generate Tests.'}
              </EmptyState>
            </div>
          )}
        </CodePanel>
      </div>

      {current?.status === 'possible_bug' && <BugBlock test={current} />}
      {current && current.status !== 'possible_bug' && current.status !== 'accepted' && (current.traceback || current.verdict) && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
          <h4 className="font-semibold">Details</h4>
          {current.verdict && (
            <p className="mt-1">
              Verification verdict: <strong>{current.verdict.verdict}</strong> — {current.verdict.reason}
            </p>
          )}
          {current.expected != null && (
            <p className="mt-1 font-mono text-xs">
              expected {current.expected} · actual {current.actual}
            </p>
          )}
          {current.traceback && <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-950 p-3 font-mono text-xs text-slate-200">{current.traceback}</pre>}
        </section>
      )}

      {tests.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <h4 className="border-b border-slate-200 px-4 py-2 text-sm font-semibold dark:border-slate-800">All test results</h4>
          <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
            {tests.map((t, i) => (
              <li key={t.name + i} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2">
                <button type="button" className="font-mono text-indigo-700 hover:underline dark:text-indigo-300" onClick={() => setTab(i)}>
                  {t.name}
                </button>
                <span className="flex items-center gap-2 text-xs text-slate-500">
                  <span className="max-w-md truncate">{t.reason}</span>
                  <StatusChip status={t.status} small />
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
