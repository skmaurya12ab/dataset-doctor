import type { TransformationSpec } from './ai'
import type { IssueSeverity } from './analysis'

export type RemediationStatus =
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'VALIDATING'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'REJECTED'

export interface RemediationApplyRequest {
  ai_report_id: string
  approval: boolean
  approved_by: string
}

export interface MetricDelta<T = number | string> {
  before: T
  after: T
  delta: T extends number ? number : string | null
}

export interface IssueComparisonItem {
  semantic_key: string
  module: string
  category: string
  column?: string | null
  status: 'RESOLVED' | 'CHANGED' | 'UNCHANGED' | 'NEW'
  before_severity?: IssueSeverity | null
  after_severity?: IssueSeverity | null
  details: Record<string, unknown>
}

export interface HeuristicComparison {
  before_score?: number | null
  after_score?: number | null
  delta?: number | null
  before_rating?: string | null
  after_rating?: string | null
  note: string
}

export interface TransformationProvenanceItem {
  action: string
  column?: string | null
  columns?: string[] | null
  parameters: Record<string, unknown>
  source_issue_ids: string[]
  reason: string
  applied_order: number
  rows_changed: number
  columns_changed: number
  before_metrics: Record<string, unknown>
  after_metrics: Record<string, unknown>
  executor_version: string
  executed_at: string
}

export interface RemediationExecution {
  id: string
  analysis_run_id: string
  ai_report_id: string
  source_dataset_version_id: string
  approved_by: string
  approved_at: string
  status: RemediationStatus
  transformation_plan: TransformationSpec[]
  pre_metrics: Record<string, unknown>
  post_metrics: Record<string, unknown>
  transformation_provenance: TransformationProvenanceItem[]
  result_dataset_version_id?: string | null
  error_message?: string | null
  created_at: string
  completed_at?: string | null
}

export interface VersionComparison {
  dataset_id: string
  before: {
    version_id: string
    version_number: number
    analysis_run_id?: string | null
    [key: string]: unknown
  }
  after: {
    version_id: string
    version_number: number
    analysis_run_id?: string | null
    [key: string]: unknown
  }
  dataset_metrics: {
    row_count: MetricDelta<number>
    column_count: MetricDelta<number>
    missing_percentage: MetricDelta<number>
    duplicate_rows: MetricDelta<number>
    [key: string]: MetricDelta<number | string>
  }
  quality: {
    summary: {
      total_before: number
      total_after: number
      resolved_count: number
      changed_count: number
      unchanged_count: number
      new_count: number
      critical_before: number
      critical_after: number
    }
    issues: IssueComparisonItem[]
  }
  heuristic: HeuristicComparison
}
