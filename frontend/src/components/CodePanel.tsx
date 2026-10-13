import { useState } from 'react'
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter'
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python'
import oneDark from 'react-syntax-highlighter/dist/esm/styles/prism/one-dark'
import oneLight from 'react-syntax-highlighter/dist/esm/styles/prism/one-light'
import { useTheme } from '../hooks/useTheme'

SyntaxHighlighter.registerLanguage('python', python)

export function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text)
    } catch {
      const ta = document.createElement('textarea')
      ta.value = text
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      ta.remove()
    }
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
    >
      {copied ? 'Copied ✓' : label}
    </button>
  )
}

export function Code({ code, startingLineNumber = 1 }: { code: string; startingLineNumber?: number }) {
  const { dark } = useTheme()
  return (
    <SyntaxHighlighter
      language="python"
      style={dark ? oneDark : oneLight}
      showLineNumbers
      startingLineNumber={startingLineNumber}
      wrapLongLines={false}
      customStyle={{ margin: 0, borderRadius: 0, fontSize: '13px', minHeight: '100%', background: 'transparent' }}
      codeTagProps={{ style: { fontFamily: '"JetBrains Mono", "Fira Code", ui-monospace, Menlo, Consolas, monospace' } }}
    >
      {code}
    </SyntaxHighlighter>
  )
}

export default function CodePanel({
  title,
  subtitle,
  actions,
  children,
}: {
  title: React.ReactNode
  subtitle?: React.ReactNode
  actions?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <section className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-800">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{title}</div>
          {subtitle && <div className="truncate text-xs text-slate-500 dark:text-slate-400">{subtitle}</div>}
        </div>
        <div className="flex items-center gap-2">{actions}</div>
      </header>
      <div className="max-h-[32rem] flex-1 overflow-auto bg-slate-50 dark:bg-slate-950/60">{children}</div>
    </section>
  )
}
