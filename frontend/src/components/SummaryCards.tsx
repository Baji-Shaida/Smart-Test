import { Link } from 'react-router-dom'
import type { Summary } from '../types'

function pct(v: number | null | undefined) {
  return v == null ? '—' : `${Math.round(v)}%`
}

function Card({ label, children, sub }: { label: string; children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="text-2xl font-bold tracking-tight">{children}</div>
      <div className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      {sub && <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{sub}</div>}
    </div>
  )
}

export default function SummaryCards({ summary, jobId }: { summary: Summary | null; jobId: string }) {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-busy="true">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-slate-200 dark:bg-slate-800" />
        ))}
      </div>
    )
  }
  const s = summary
  const delta = s.coverage_delta
  return (
    <section aria-label="Summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Card label="Coverage">
        {s.generated ? (
          <>
            {pct(s.coverage_before)} <span className="text-slate-400">→</span> {pct(s.coverage_after)}{' '}
            <span className={`text-base ${delta != null && delta >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600'}`}>
              ({delta != null && delta >= 0 ? '+' : ''}
              {delta != null ? Math.round(delta) : 0}%)
            </span>
          </>
        ) : (
          pct(s.coverage_before)
        )}
      </Card>
      <Card label="Untested functions" sub={s.generated ? 'below the coverage threshold' : 'candidates for generation'}>
        {s.generated && s.untested_after != null ? (
          <>
            {s.untested_before} <span className="text-slate-400">→</span> {s.untested_after}{' '}
            <span className="text-base font-medium text-slate-500">remaining</span>
          </>
        ) : (
          s.untested_before
        )}
      </Card>
      <Card label="Tests generated">
        {s.tests_generated} <span className="text-base font-medium text-slate-500">generated,</span> {s.accepted}{' '}
        <span className="text-base font-medium text-slate-500">accepted</span>
      </Card>
      <Link
        to={`/jobs/${jobId}/bugs`}
        className="rounded-xl border border-orange-300 bg-orange-50 p-4 shadow-sm transition hover:bg-orange-100 dark:border-orange-800 dark:bg-orange-950/40 dark:hover:bg-orange-900/40"
        aria-label={`${s.possible_bugs} possible bugs found. Open the bug report`}
      >
        <div className="text-2xl font-bold tracking-tight text-orange-700 dark:text-orange-300">
          <span aria-hidden>⚠ </span>
          {s.possible_bugs}
        </div>
        <div className="mt-1 text-xs font-medium uppercase tracking-wide text-orange-800 dark:text-orange-300">
          Possible bugs found
        </div>
        <div className="mt-1 text-xs text-orange-700 underline dark:text-orange-300">View bug report</div>
      </Link>
    </section>
  )
}
