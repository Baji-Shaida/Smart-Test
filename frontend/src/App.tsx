import { BrowserRouter, Link, Route, Routes } from 'react-router-dom'
import HealthBadge from './components/HealthBadge'
import { ThemeProvider, useTheme } from './hooks/useTheme'
import BugReportPage from './pages/BugReportPage'
import DashboardPage from './pages/DashboardPage'
import FunctionDetailPage from './pages/FunctionDetailPage'
import GenerationPage from './pages/GenerationPage'
import HomePage from './pages/HomePage'
import JobLayout from './pages/JobLayout'
import SummaryPage from './pages/SummaryPage'

function ThemeToggle() {
  const { dark, toggle } = useTheme()
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? 'Switch to light theme' : 'Switch to dark theme'}
      className="rounded-md border border-slate-300 px-2 py-1 text-xs dark:border-slate-700"
    >
      {dark ? '☀ Light' : '☾ Dark'}
    </button>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <BrowserRouter>
        <div className="min-h-full">
          <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/90 px-6 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
            <Link to="/" className="flex items-baseline gap-2">
              <h1 className="text-lg font-bold text-indigo-700 dark:text-indigo-300">SmartTest</h1>
              <span className="hidden text-xs text-slate-500 sm:inline">AI-powered code coverage and test automation</span>
            </Link>
            <div className="flex items-center gap-2">
              <HealthBadge />
              <ThemeToggle />
            </div>
          </header>
          <main className="mx-auto max-w-7xl p-4 sm:p-6">
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/jobs/:jobId" element={<JobLayout />}>
                <Route index element={<DashboardPage />} />
                <Route path="generate" element={<GenerationPage />} />
                <Route path="functions/:fid" element={<FunctionDetailPage />} />
                <Route path="bugs" element={<BugReportPage />} />
                <Route path="summary" element={<SummaryPage />} />
              </Route>
              <Route path="*" element={<div className="py-10 text-center">Page not found. <Link className="underline" to="/">Go home</Link></div>} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </ThemeProvider>
  )
}
