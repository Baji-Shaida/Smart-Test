import { Link } from 'react-router-dom'
import { EmptyState } from '../components/ErrorBanner'
import LiveFeed from '../components/LiveFeed'
import StatusChip from '../components/StatusChip'
import Stepper, { ProgressBar } from '../components/Stepper'
import SummaryCards from '../components/SummaryCards'
import { liveStatus, useJob } from '../hooks/useJob'

export default function GenerationPage() {
  const { jobId, job, functions, summary, feed, connection } = useJob()
  const involved = (functions ?? []).filter((f) => f.processed || feed.statuses[f.id] !== undefined || ['generating'].includes(f.status))
  const progress = feed.progress.total ? feed.progress : job?.progress ?? { done: 0, total: 0 }
  const done = job?.status === 'completed'
  return (
    <div className="space-y-5">
      <SummaryCards summary={summary} jobId={jobId} />
      <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
        <Stepper stages={feed.stages} />
        <ProgressBar done={progress.done} total={progress.total} />
      </div>
      {done && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-100">
          <span>Generation complete.</span>
          <Link to={`/jobs/${jobId}/summary`} className="rounded-md bg-emerald-600 px-3 py-1.5 font-medium text-white hover:bg-emerald-500">
            Open Summary Report →
          </Link>
        </div>
      )}
      <div className="grid gap-5 lg:grid-cols-5">
        <div className="lg:col-span-3">
          <LiveFeed logs={feed.logs} connection={connection} height="h-[28rem]" />
        </div>
        <section className="rounded-xl border border-slate-200 bg-white lg:col-span-2 dark:border-slate-800 dark:bg-slate-900" aria-label="Functions">
          <h3 className="border-b border-slate-200 px-4 py-2 text-sm font-semibold dark:border-slate-800">Functions</h3>
          {involved.length === 0 ? (
            <div className="p-4">
              <EmptyState title="Nothing generated yet">
                Choose functions on the <Link className="underline" to={`/jobs/${jobId}`}>Analysis</Link> tab and press Generate Tests.
              </EmptyState>
            </div>
          ) : (
            <ul className="max-h-[28rem] divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
              {involved.map((f) => (
                <li key={f.id}>
                  <Link to={`/jobs/${jobId}/functions/${encodeURIComponent(f.id)}`} className="flex items-center justify-between gap-2 px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-800/40">
                    <span className="min-w-0">
                      <span className="block truncate font-mono text-sm">{f.qualname}</span>
                      <span className="block truncate text-xs text-slate-500">{f.file}</span>
                    </span>
                    <StatusChip status={liveStatus(f, feed)} small />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
