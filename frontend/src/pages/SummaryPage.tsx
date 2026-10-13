import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { EmptyState, Spinner } from '../components/ErrorBanner'
import StatusChip, { RiskBadge } from '../components/StatusChip'
import SummaryCards from '../components/SummaryCards'
import { liveStatus, useJob } from '../hooks/useJob'

export default function SummaryPage() {
  const { jobId, job, functions, summary, feed } = useJob()
  if (!summary || !functions) return <Spinner />
  const processed = functions.filter((f) => f.processed)
  const ready = job?.status === 'completed' || job?.status === 'analyzed'
  return (
    <div className="space-y-5">
      <SummaryCards summary={summary} jobId={jobId} />
      <div className="flex flex-wrap gap-2">
        <a
          href={api.reportUrl(jobId)}
          aria-disabled={!ready}
          className={`rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500 ${ready ? '' : 'pointer-events-none opacity-50'}`}
        >
          Download PDF report
        </a>
        <a
          href={api.testsZipUrl(jobId)}
          aria-disabled={summary.accepted === 0}
          className={`rounded-lg border border-indigo-600 px-4 py-2 text-sm font-semibold text-indigo-700 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-indigo-950 ${
            summary.accepted ? '' : 'pointer-events-none opacity-50'
          }`}
        >
          Download accepted tests (.zip)
        </a>
        <Link to={`/jobs/${jobId}/bugs`} className="rounded-lg border border-orange-500 px-4 py-2 text-sm font-semibold text-orange-700 hover:bg-orange-50 dark:text-orange-300 dark:hover:bg-orange-950">
          Bug Report ({summary.possible_bugs})
        </Link>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
        <h3 className="font-semibold">Before / after</h3>
        <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
          <dt className="text-slate-500">Coverage before</dt>
          <dd>{summary.coverage_before?.toFixed(1)}%</dd>
          <dt className="text-slate-500">Coverage after</dt>
          <dd>{summary.coverage_after != null ? `${summary.coverage_after.toFixed(1)}%` : '—'}</dd>
          <dt className="text-slate-500">Functions processed</dt>
          <dd>{summary.functions_processed}</dd>
          <dt className="text-slate-500">Tests: accepted / review / rejected</dt>
          <dd>
            {summary.accepted} / {summary.needs_review} / {summary.rejected}
          </dd>
        </dl>
        {summary.newly_covered.length > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            Newly tested: {summary.newly_covered.map((id) => id.split('::')[1]).join(', ')}
          </p>
        )}
      </section>

      <section className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <h3 className="border-b border-slate-200 px-4 py-2 font-semibold dark:border-slate-800">Per-function results</h3>
        {processed.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No functions processed yet">Generate tests from the Analysis tab.</EmptyState>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500 dark:bg-slate-950/50 dark:text-slate-400">
                <tr>
                  <th scope="col" className="px-4 py-2">Function</th>
                  <th scope="col" className="px-2 py-2">Risk</th>
                  <th scope="col" className="px-2 py-2 text-right">Coverage</th>
                  <th scope="col" className="px-2 py-2 text-right">Tests</th>
                  <th scope="col" className="px-2 py-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {processed.map((f) => {
                  const accepted = f.tests.filter((t) => t.status === 'accepted').length
                  return (
                    <tr key={f.id} className="border-t border-slate-100 dark:border-slate-800">
                      <td className="px-4 py-2">
                        <Link to={`/jobs/${jobId}/functions/${encodeURIComponent(f.id)}`} className="font-mono text-indigo-700 hover:underline dark:text-indigo-300">
                          {f.qualname}
                        </Link>{' '}
                        <span className="text-xs text-slate-500">{f.file}</span>
                      </td>
                      <td className="px-2 py-2">
                        <RiskBadge label={f.risk_label} />
                      </td>
                      <td className="px-2 py-2 text-right">
                        {Math.round(f.coverage_pct)}% → {f.coverage_after_pct != null ? `${Math.round(f.coverage_after_pct)}%` : '—'}
                      </td>
                      <td className="px-2 py-2 text-right">
                        {accepted}/{f.tests.length} accepted
                      </td>
                      <td className="px-2 py-2">
                        <StatusChip status={liveStatus(f, feed)} small />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <p className="text-xs text-slate-500">
        Tests are AI-generated and must be reviewed before you rely on them. "Possible bug" means worth a human look, not proof.
      </p>
    </div>
  )
}
