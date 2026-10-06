import type { IssueSeverity } from './analysis'

export type AllowedAction =
  | 'DROP_COLUMN'
  | 'REMOVE_DUPLICATES'
  | 'IMPUTE'
  | 'CAST_TYPE'
  | 'CLIP_OUTLIERS'

export interface TransformationSpec {
  action: AllowedAction
  column?: string | null
  columns?: string[] | null
  parameters: Record<string, unknown>
  rationale: string
  source_issue_ids: string[]
}

export interface RiskAssessmentItem {
  risk_type: string
  severity: IssueSeverity
  summary: string
  ml_impact: string
}

export interface RemediationStep {
  priority: number
  issue_reference: string
  problem: string
  recommendation: string
  reason: string
  risk: string
}

export interface FindingExplanation {
  explanation: string
  why_it_matters: string
  practical_impact: string
  recommended_actions: string[]
  limitations: string[]
}

export interface FindingExplanationResponse {
  issue_id: string
  provider: string
  model: string
  prompt_version: string
  explanation: string
  why_it_matters: string
  practical_impact: string
  recommended_actions: string[]
  limitations: string[]
  created_at: string
}

export interface AIReportContent {
  executive_summary: string
  risk_assessment: RiskAssessmentItem[]
  prioritized_remediation_steps: RemediationStep[]
  ml_preparation_plan: string[]
  transformation_specs: TransformationSpec[]
  generated_python_code?: string | null
}

export interface AIReport {
  id: string
  analysis_run_id: string
  provider: string
  model: string
  prompt_version: string
  report_type: string
  content: AIReportContent
  created_at: string
}
