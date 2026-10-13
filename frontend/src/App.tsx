import HealthBadge from './components/HealthBadge'

export default function App() {
  return (
    <div className="min-h-full">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3 dark:border-slate-800">
        <h1 className="text-lg font-semibold">SmartTest</h1>
        <HealthBadge />
      </header>
      <main className="p-6">AI-Powered Code Coverage and Test Automation Tool</main>
    </div>
  )
}
