export type IssueSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'

export interface QualityIssue {
  id: string
  analysis_run_id: string
  dataset_version_id: string
  module: string
  analyzer_version: string
  parameters_used: Record<string, unknown>
  category: string
  severity: IssueSeverity
  column_name?: string | null
  title: string
  description: string
  evidence: Record<string, unknown>
  remediation_hint?: string | null
  detected_at: string
}

export interface ItemizedPenalty {
  module: string
  severity: IssueSeverity
  reason: string
  penalty: number
  column_name?: string | null
}

export interface HeuristicBreakdown {
  heuristic_score: number
  rating: string
  base_score: number
  total_penalties: number
  disclaimer: string
  itemized_penalties: ItemizedPenalty[]
}

export interface AnalysisRun {
  id: string
  dataset_version_id: string
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  target_column?: string | null
  problem_type?: string | null
  engine_version: string
  analyzer_versions: Record<string, unknown>
  ml_readiness_score?: number | null
  heuristic_breakdown?: HeuristicBreakdown | null
  total_issues_count: number
  critical_issues_count: number
  execution_time_ms?: number | null
  summary_metrics: Record<string, unknown>
  error_message?: string | null
  created_at: string
  completed_at?: string | null
}

export interface QualityIssueListResponse {
  total: number
  limit: number
  offset: number
  items: QualityIssue[]
}

export interface MissingValueVizItem {
  column: string
  missing_count: number
  missing_percentage: number
  severity: IssueSeverity
}

export interface CardinalityVizItem {
  column: string
  unique_count: number
  unique_ratio: number
  classification: string
  severity: IssueSeverity
}

export interface OutlierVizItem {
  column: string
  outlier_count: number
  outlier_percentage: number
  lower_bound?: number | null
  upper_bound?: number | null
  severity: IssueSeverity
}

export interface DistributionVizItem {
  column: string
  mean: number
  std: number
  median: number
  min: number
  max: number
  q25: number
  q75: number
  skewness: number
  kurtosis: number
  sample_points?: number[]
}

export interface CorrelationVizData {
  columns: string[]
  pearson_matrix: number[][]
  spearman_matrix: number[][]
  high_correlation_pairs: Array<{
    col1: string
    col2: string
    pearson: number
    spearman: number
    severity: IssueSeverity
  }>
}

export interface ClassImbalanceVizData {
  target_column: string
  classes: Array<{
    class_name: string
    count: number
    percentage: number
  }>
  imbalance_ratio: number
  severity: IssueSeverity
}

export interface VisualizationData {
  missing_values: MissingValueVizItem[]
  cardinality: CardinalityVizItem[]
  outliers: OutlierVizItem[]
  distributions: DistributionVizItem[]
  correlations: CorrelationVizData
  class_imbalance?: ClassImbalanceVizData | null
  summary: {
    score?: number | null
    rating?: string | null
    critical_issues?: number
    high_issues?: number
    total_issues?: number
    leakage_risks?: Array<{
      column: string
      type: string
      severity: IssueSeverity
      detail: string
    }>
  }
}

export interface OverviewStats {
  total_datasets: number
  total_versions: number
  running_analyses_count: number
  latest_analyses: AnalysisRun[]
  recent_remediations: Array<Record<string, unknown>>
  unresolved_critical_issues_count: number
  unresolved_high_issues_count: number
  average_readiness_score?: number | null
}
