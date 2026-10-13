export type FunctionStatus = 'pending' | 'generating' | 'accepted' | 'needs_review' | 'rejected' | 'possible_bug'
export type TestStatus = 'accepted' | 'needs_review' | 'rejected' | 'possible_bug'
export type JobStatus = 'queued' | 'analyzing' | 'analyzed' | 'generating' | 'completed' | 'failed'
export type StageName = 'parse' | 'coverage' | 'prioritize' | 'generate' | 'validate' | 'report'
export type LogLevel = 'info' | 'warn' | 'error' | 'success'

export interface Verdict {
  verdict: 'likely_bug' | 'test_wrong' | 'unclear'
  reason: string
}

export interface TestRecord {
  name: string
  status: TestStatus
  code: string
  attempts: number
  reason: string
  expected: string | null
  actual: string | null
  traceback: string
  verdict: Verdict | null
}

export interface FunctionRecord {
  id: string
  file: string
  module: string
  name: string
  qualname: string
  line_start: number
  line_end: number
  is_method: boolean
  signature: string
  docstring: string
  source?: string
  coverage_pct: number
  coverage_label: 'untested' | 'partial' | 'tested'
  coverage_after_pct?: number | null
  coverage_after_label?: string | null
  candidate: boolean
  rank?: number
  last_modified_days: number | null
  usage_count: number | null
  risk_score: number | null
  risk_label: 'High' | 'Medium' | 'Low' | null
  status: FunctionStatus
  processed: boolean
  attempts?: number
  error?: string | null
  test_file?: string | null
  test_code?: string
  tests: TestRecord[] | { name: string; status: TestStatus }[]
}

export interface JobSettings {
  model: string
  max_functions: number
  coverage_threshold: number
}

export interface JobState {
  job_id: string
  status: JobStatus
  stage: StageName | null
  stages: Partial<Record<StageName, 'start' | 'done'>>
  source: { type: 'zip' | 'github'; name: string; url?: string; filename?: string }
  project_name: string
  settings: JobSettings
  llm_provider: string
  model_used?: string
  created_at: string
  updated_at: string
  coverage_before: number | null
  coverage_after: number | null
  progress: { done: number; total: number }
  error: string | null
  counts: { files: number; functions: number; candidates: number; processed: number }
  last_event_id: number
}

export interface Bug {
  function_id: string
  file: string
  line_start: number
  line_end: number
  qualname: string
  test: string
  expected: string | null
  actual: string | null
  reason: string
}

export interface Summary {
  project_name: string
  model: string
  generated: boolean
  coverage_before: number | null
  coverage_after: number | null
  coverage_delta: number | null
  untested_before: number
  untested_after: number | null
  functions_total: number
  functions_processed: number
  tests_generated: number
  accepted: number
  needs_review: number
  rejected: number
  possible_bugs: number
  newly_covered: string[]
  bugs: Bug[]
}

export interface LogLine {
  id: number
  ts: string
  level: LogLevel
  message: string
}

export interface ServerEvent {
  id: number
  event: string
  data: Record<string, unknown>
}

export interface Models {
  reachable: boolean
  models: string[]
  default: string
}
