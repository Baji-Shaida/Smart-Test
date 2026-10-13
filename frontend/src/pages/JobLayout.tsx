import { NavLink, Outlet, useParams } from 'react-router-dom'
import ErrorBanner, { Spinner } from '../components/ErrorBanner'
import { JobProvider, useJob } from '../hooks/useJob'

function JobNav() {
  const { jobId, job, summary, feed, loadError } = useJob()
  const tab = ({ isActive }: { isActive: boolean }) =>
    `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800'}`
  if (loadError && !job) return <ErrorBanner message={loadError} />
  if (!job) return <Spinner label="Loading job…" />
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">{job.project_name}</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Job {job.job_id} · {job.source.type === 'github' ? job.source.url : job.source.filename} · model{' '}
            {job.llm_provider === 'mock' ? 'mock' : job.settings.model} · threshold {job.settings.coverage_threshold}% · status{' '}
            <strong>{job.status}</strong>
          </p>
        </div>
        <nav aria-label="Job sections" className="flex flex-wrap gap-1">
          <NavLink end to={`/jobs/${jobId}`} className={tab}>
            Analysis
          </NavLink>
          <NavLink to={`/jobs/${jobId}/generate`} className={tab}>
            Generation
          </NavLink>
          <NavLink to={`/jobs/${jobId}/bugs`} className={tab}>
            Bug Report{summary ? ` (${summary.possible_bugs})` : ''}
          </NavLink>
          <NavLink to={`/jobs/${jobId}/summary`} className={tab}>
            Summary
          </NavLink>
        </nav>
      </div>
      {job.status === 'failed' && <ErrorBanner message={job.error || 'The job failed'} />}
      {feed.error && feed.error.recoverable && job.status !== 'failed' && <ErrorBanner message={feed.error.message} />}
      <Outlet />
    </div>
  )
}

export default function JobLayout() {
  const { jobId } = useParams()
  if (!jobId) return null
  return (
    <JobProvider jobId={jobId}>
      <JobNav />
    </JobProvider>
  )
}
