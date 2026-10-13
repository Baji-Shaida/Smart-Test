import { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import ErrorBanner, { EmptyState, Spinner } from '../components/ErrorBanner'
import LiveFeed from '../components/LiveFeed'
import StatusChip, { RiskBadge } from '../components/StatusChip'
import Stepper from '../components/Stepper'
import SummaryCards from '../components/SummaryCards'
import { liveStatus, useJob } from '../hooks/useJob'

export default function DashboardPage() {
  const { jobId, job, functions, summary, feed, connection, running, generate } = useJob()
  const navigate = useNavigate()
  const candidates = useMemo(() => (functions ?? []).filter((f) => f.candidate), [functions])
  const [selected, setSelected] = useState<Set<string> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const maxF = job?.settings.max_functions ?? 10
  const sel = selected ?? new Set(candidates.slice(0, maxF).map((f) => f.id))
  const analyzing = job?.status === 'queued' || job?.status === 'analyzing'
  const canGenerate = !!job && ['analyzed', 'completed'].includes(job.status) && !running && !busy

  const toggle = (id: string) => {
    const next = new Set(sel)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }
  const allChecked = candidates.length > 0 && candidates.every((f) => sel.has(f.id))

  const start = async (body: { function_ids?: string[]; all?: boolean }) => {
    setBusy(true)
    setError(null)
    try {
      await generate(body)
      navigate(`/jobs/${jobId}/generate`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <SummaryCards summary={summary} jobId={jobId} />
      <Stepper stages={feed.stages} />
      <LiveFeed logs={feed.logs} connection={connection} height={analyzing ? 'h-72' : 'h-48'} />
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
          <div>
            <h3 className="font-semibold">Candidate functions, ranked by risk</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Coverage below {job?.settings.coverage_threshold ?? 60}% · risk = 0.5 × recency + 0.5 × usage · top {maxF} preselected
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={!canGenerate || sel.size === 0}
              onClick={() => start({ function_ids: candidates.filter((f) => sel.has(f.id)).map((f) => f.id) })}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Generate Tests ({sel.size})
            </button>
            <button
              type="button"
              disabled={!canGenerate || candidates.length === 0}
              onClick={() => start({ all: true })}
              className="rounded-lg border border-indigo-600 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-indigo-300 dark:hover:bg-indigo-950"
            >
              Generate All ({candidates.length})
            </button>
          </div>
        </div>
        {analyzing || functions === null ? (
          <div className="px-4">
            <Spinner label="Analyzing the project…" />
          </div>
        ) : job?.status === 'failed' ? (
          <div className="p-4">
            <EmptyState title="Analysis failed">See the error above and the live feed for details.</EmptyState>
          </div>
        ) : candidates.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No candidates">Every function is at or above the coverage threshold. Nothing to generate.</EmptyState>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-950/50 dark:text-slate-400">
                <tr>
                  <th scope="col" className="px-4 py-2">
                    <input type="checkbox" aria-label="Select all" checked={allChecked} onChange={() => setSelected(allChecked ? new Set() : new Set(candidates.map((f) => f.id)))} />
                  </th>
                  <th scope="col" className="px-2 py-2">#</th>
                  <th scope="col" className="px-2 py-2">File</th>
                  <th scope="col" className="px-2 py-2">Function</th>
                  <th scope="col" className="px-2 py-2 text-right">Coverage</th>
                  <th scope="col" className="px-2 py-2 text-right">Last modified</th>
                  <th scope="col" className="px-2 py-2 text-right">Usage</th>
                  <th scope="col" className="px-2 py-2">Risk</th>
                  <th scope="col" className="px-2 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {candidates.map((f) => (
                  <tr key={f.id} className="border-t border-slate-100 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40">
                    <td className="px-4 py-2">
                      <input type="checkbox" aria-label={`Select ${f.qualname}`} checked={sel.has(f.id)} onChange={() => toggle(f.id)} />
                    </td>
                    <td className="px-2 py-2 text-slate-500">{f.rank}</td>
                    <td className="px-2 py-2 font-mono text-xs">{f.file}</td>
                    <td className="px-2 py-2">
                      <Link to={`/jobs/${jobId}/functions/${encodeURIComponent(f.id)}`} className="font-mono text-indigo-700 hover:underline dark:text-indigo-300">
                        {f.qualname}
                      </Link>
                    </td>
                    <td className="px-2 py-2 text-right">
                      {Math.round(f.coverage_pct)}%{' '}
                      <span className="text-xs text-slate-500">{f.coverage_label === 'untested' ? 'Untested' : 'Partial'}</span>
                    </td>
                    <td className="px-2 py-2 text-right">{f.last_modified_days ?? '—'}d ago</td>
                    <td className="px-2 py-2 text-right">{f.usage_count ?? 0}</td>
                    <td className="px-2 py-2">
                      <RiskBadge label={f.risk_label} /> <span className="text-xs text-slate-500">{f.risk_score?.toFixed(2)}</span>
                    </td>
                    <td className="px-2 py-2">
                      <StatusChip status={liveStatus(f, feed)} small />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
