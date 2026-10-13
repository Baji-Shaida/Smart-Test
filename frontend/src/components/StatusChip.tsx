import type { FunctionStatus } from '../types'

const STYLES: Record<FunctionStatus, { label: string; cls: string; icon: string }> = {
  accepted: { label: 'ACCEPTED', icon: '✓', cls: 'bg-emerald-100 text-emerald-800 ring-emerald-300 dark:bg-emerald-900/40 dark:text-emerald-200 dark:ring-emerald-700' },
  possible_bug: { label: 'POSSIBLE BUG FOUND', icon: '!', cls: 'bg-orange-100 text-orange-800 ring-orange-300 dark:bg-orange-900/40 dark:text-orange-200 dark:ring-orange-700' },
  needs_review: { label: 'NEEDS REVIEW', icon: '?', cls: 'bg-yellow-100 text-yellow-900 ring-yellow-300 dark:bg-yellow-900/40 dark:text-yellow-100 dark:ring-yellow-700' },
  rejected: { label: 'REJECTED', icon: '×', cls: 'bg-slate-200 text-slate-700 ring-slate-300 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-600' },
  pending: { label: 'PENDING', icon: '•', cls: 'bg-sky-100 text-sky-800 ring-sky-300 dark:bg-sky-900/40 dark:text-sky-200 dark:ring-sky-700' },
  generating: { label: 'GENERATING', icon: '↻', cls: 'bg-sky-100 text-sky-800 ring-sky-300 dark:bg-sky-900/40 dark:text-sky-200 dark:ring-sky-700' },
}

export default function StatusChip({ status, small }: { status: FunctionStatus; small?: boolean }) {
  const s = STYLES[status] ?? STYLES.pending
  return (
    <span
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full font-semibold ring-1 ring-inset ${s.cls} ${
        small ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-0.5 text-xs'
      }`}
    >
      <span aria-hidden className={status === 'generating' ? 'inline-block animate-spin' : ''}>
        {s.icon}
      </span>
      {s.label}
      {status === 'generating' && <span aria-hidden className="animate-pulse">…</span>}
    </span>
  )
}

export function RiskBadge({ label }: { label: string | null }) {
  if (!label) return <span className="text-slate-400">—</span>
  const cls =
    label === 'High'
      ? 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200'
      : label === 'Medium'
        ? 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-100'
        : 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>
}
