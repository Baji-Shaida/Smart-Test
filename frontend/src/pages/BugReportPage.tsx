import { Link } from 'react-router-dom'
import { EmptyState, Spinner } from '../components/ErrorBanner'
import { useJob } from '../hooks/useJob'

export default function BugReportPage() {
  const { jobId, summary } = useJob()
  if (!summary) return <Spinner />
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold">Bug Report</h3>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Well-formed generated tests that failed, were re-run to rule out flakiness, and were judged a likely bug by the verification
          step. Worth a human look, not proof of a bug.
        </p>
      </div>
      {summary.bugs.length === 0 ? (
        <EmptyState title={summary.generated ? 'No possible bugs found' : 'No tests generated yet'}>
          {summary.generated ? 'Every failing test was either flaky, unclear or judged to be wrong.' : 'Run Generate Tests first.'}
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {summary.bugs.map((b) => (
            <li key={b.function_id + b.test} className="rounded-xl border-l-4 border-orange-500 bg-white p-4 shadow-sm dark:bg-slate-900">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <span className="font-mono font-semibold">{b.qualname}</span>{' '}
                  <span className="text-xs text-slate-500">
                    {b.file}:{b.line_start}-{b.line_end}
                  </span>
                </div>
                <Link
                  to={`/jobs/${jobId}/functions/${encodeURIComponent(b.function_id)}`}
                  className="rounded-md bg-orange-600 px-3 py-1 text-xs font-medium text-white hover:bg-orange-500"
                >
                  Open side-by-side view →
                </Link>
              </div>
              <div className="mt-2 text-sm">
                Failing test: <code className="font-mono">{b.test}</code>
              </div>
              <div className="mt-1 grid gap-2 text-sm sm:grid-cols-2">
                <div>
                  <span className="text-xs font-semibold uppercase text-slate-500">Expected</span> <code className="font-mono">{b.expected}</code>
                </div>
                <div>
                  <span className="text-xs font-semibold uppercase text-slate-500">Actual</span> <code className="font-mono">{b.actual}</code>
                </div>
              </div>
              <p className="mt-2 text-sm text-slate-700 dark:text-slate-300">{b.reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
