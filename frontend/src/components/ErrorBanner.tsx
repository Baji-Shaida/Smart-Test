export default function ErrorBanner({ message, onDismiss }: { message: string; onDismiss?: () => void }) {
  const ollama = /ollama/i.test(message)
  return (
    <div role="alert" className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950/50 dark:text-red-100">
      <div className="flex items-start justify-between gap-4">
        <div>
          <strong className="font-semibold">Error: </strong>
          {message}
          {ollama && (
            <div className="mt-2 text-xs">
              Start Ollama with <code className="rounded bg-red-100 px-1 dark:bg-red-900">ollama serve</code>, pull the model with{' '}
              <code className="rounded bg-red-100 px-1 dark:bg-red-900">ollama pull qwen2.5-coder:7b</code>, or run the backend with{' '}
              <code className="rounded bg-red-100 px-1 dark:bg-red-900">LLM_PROVIDER=mock</code> for the demo.
            </div>
          )}
        </div>
        {onDismiss && (
          <button type="button" onClick={onDismiss} className="text-xs underline" aria-label="Dismiss error">
            Dismiss
          </button>
        )}
      </div>
    </div>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-slate-500 dark:text-slate-400" role="status">
      <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-indigo-500" />
      {label}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 px-6 py-10 text-center dark:border-slate-700">
      <div className="font-medium">{title}</div>
      {children && <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{children}</div>}
    </div>
  )
}
