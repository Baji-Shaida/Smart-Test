import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import type { Connection } from '../hooks/useEventStream'
import { formatTime } from '../state/feed'
import type { LogLine } from '../types'

const LEVEL: Record<LogLine['level'], { tag: string; cls: string }> = {
  info: { tag: 'INFO', cls: 'text-slate-300' },
  success: { tag: ' OK ', cls: 'text-emerald-400' },
  warn: { tag: 'WARN', cls: 'text-amber-300' },
  error: { tag: 'ERR ', cls: 'text-red-400' },
}

function renderMessage(msg: string) {
  return msg.split(/(`[^`]+`)/g).map((part, i) =>
    part.startsWith('`') && part.endsWith('`') ? (
      <span key={i} className="text-sky-300">
        {part.slice(1, -1)}
      </span>
    ) : (
      part
    ),
  )
}

export default function LiveFeed({ logs, connection, height = 'h-80' }: { logs: LogLine[]; connection: Connection; height?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [follow, setFollow] = useState(true)
  const programmatic = useRef(false)

  useLayoutEffect(() => {
    const el = ref.current
    if (el && follow) {
      programmatic.current = true
      el.scrollTop = el.scrollHeight
    }
  }, [logs.length, follow])

  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onScroll = () => {
      if (programmatic.current) {
        programmatic.current = false
        return
      }
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24
      setFollow(atBottom)
    }
    el.addEventListener('scroll', onScroll)
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  const dot =
    connection === 'live' ? 'bg-emerald-400 animate-pulse' : connection === 'idle' ? 'bg-slate-500' : 'bg-amber-400 animate-pulse'
  return (
    <section aria-label="Live progress feed" className="relative overflow-hidden rounded-xl border border-slate-800 bg-slate-950 shadow-inner">
      <div className="flex items-center justify-between border-b border-slate-800 px-3 py-1.5 text-xs text-slate-400">
        <span className="font-mono">smarttest — live feed</span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className={`h-2 w-2 rounded-full ${dot}`} />
          {connection === 'live' ? 'Live' : connection === 'idle' ? 'Idle' : connection === 'connecting' ? 'Connecting…' : 'Reconnecting…'}
        </span>
      </div>
      <div ref={ref} className={`${height} overflow-y-auto px-3 py-2 font-mono text-[13px] leading-relaxed`} role="log" aria-live="polite" tabIndex={0}>
        {logs.length === 0 && <div className="text-slate-500">Waiting for events…</div>}
        {logs.map((l) => (
          <div key={l.id} className={`whitespace-pre-wrap break-words ${LEVEL[l.level]?.cls ?? 'text-slate-300'}`}>
            <span className="text-slate-500">[{formatTime(l.ts)}]</span>{' '}
            <span className="font-semibold">{LEVEL[l.level]?.tag ?? l.level}</span> {renderMessage(l.message)}
          </div>
        ))}
      </div>
      {!follow && (
        <button
          type="button"
          onClick={() => setFollow(true)}
          className="absolute bottom-3 right-4 rounded-full bg-indigo-600 px-3 py-1 text-xs font-medium text-white shadow-lg hover:bg-indigo-500"
        >
          ↓ Jump to latest
        </button>
      )}
    </section>
  )
}
