import { STAGES } from '../state/feed'
import type { StageName } from '../types'

export default function Stepper({ stages }: { stages: Partial<Record<StageName, 'start' | 'done'>> }) {
  return (
    <ol className="flex flex-wrap items-center gap-2 text-xs" aria-label="Pipeline stages">
      {STAGES.map((s, i) => {
        const st = stages[s.key]
        const cls =
          st === 'done'
            ? 'border-emerald-500 bg-emerald-500 text-white'
            : st === 'start'
              ? 'border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200'
              : 'border-slate-300 text-slate-500 dark:border-slate-700'
        return (
          <li key={s.key} className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-medium ${cls}`}
              aria-current={st === 'start' ? 'step' : undefined}
            >
              <span aria-hidden>{st === 'done' ? '✓' : st === 'start' ? <span className="inline-block animate-spin">◌</span> : i + 1}</span>
              {s.label}
              <span className="sr-only">{st === 'done' ? ' (done)' : st === 'start' ? ' (running)' : ' (waiting)'}</span>
            </span>
            {i < STAGES.length - 1 && <span aria-hidden className="h-px w-4 bg-slate-300 dark:bg-slate-700" />}
          </li>
        )
      })}
    </ol>
  )
}

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const p = total > 0 ? Math.round((done / total) * 100) : 0
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-slate-500 dark:text-slate-400">
        <span>Progress</span>
        <span>
          {done} / {total} functions ({p}%)
        </span>
      </div>
      <div
        className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
      >
        <div className="h-full rounded-full bg-indigo-500 transition-all duration-500" style={{ width: `${p}%` }} />
      </div>
    </div>
  )
}
