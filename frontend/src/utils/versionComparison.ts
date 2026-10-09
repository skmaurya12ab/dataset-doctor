import type {
  VersionComparison,
  IssueComparisonItem,
  QualityComparisonSummary,
  MetricDelta,
} from '../types/remediation'

/**
 * Normalizes a VersionComparison response from the backend.
 * Reconciles the backend's deterministic contract:
 *   - quality: { issues_resolved, issues_changed, issues_unchanged, new_issues, items }
 *   - dataset_metrics: { rows, columns, missing_cells, missing_percentage, duplicate_rows, ... }
 * with the frontend's expected properties:
 *   - quality: { summary, issues, items, ... }
 *   - dataset_metrics: { row_count, column_count, ... }
 */
export function normalizeVersionComparison(raw: any): VersionComparison {
  if (!raw) return raw

  const rawQuality = raw.quality || {}
  const rawMetrics = raw.dataset_metrics || {}

  // 1. Resolve granular issue items array
  const items: IssueComparisonItem[] = Array.isArray(rawQuality.items)
    ? rawQuality.items
    : Array.isArray(rawQuality.issues)
    ? rawQuality.issues
    : []

  // 2. Resolve lifecycle counts
  const resolved = Number(rawQuality.issues_resolved ?? rawQuality.summary?.resolved_count ?? 0)
  const changed = Number(rawQuality.issues_changed ?? rawQuality.summary?.changed_count ?? 0)
  const unchanged = Number(rawQuality.issues_unchanged ?? rawQuality.summary?.unchanged_count ?? 0)
  const newCount = Number(rawQuality.new_issues ?? rawQuality.summary?.new_count ?? 0)

  const criticalBefore = Number(
    rawQuality.summary?.critical_before ??
    rawMetrics.critical_issues?.before ??
    0
  )
  const criticalAfter = Number(
    rawQuality.summary?.critical_after ??
    rawMetrics.critical_issues?.after ??
    0
  )

  const summary: QualityComparisonSummary = {
    total_before: Number(
      rawQuality.summary?.total_before ??
      rawMetrics.total_issues?.before ??
      (resolved + changed + unchanged)
    ),
    total_after: Number(
      rawQuality.summary?.total_after ??
      rawMetrics.total_issues?.after ??
      (changed + unchanged + newCount)
    ),
    resolved_count: resolved,
    changed_count: changed,
    unchanged_count: unchanged,
    new_count: newCount,
    critical_before: criticalBefore,
    critical_after: criticalAfter,
  }

  // 3. Normalize dataset metrics to guarantee both rows/row_count and columns/column_count
  const rowsDelta: MetricDelta<number> =
    rawMetrics.row_count ?? rawMetrics.rows ?? { before: 0, after: 0, delta: 0 }
  const colsDelta: MetricDelta<number> =
    rawMetrics.column_count ?? rawMetrics.columns ?? { before: 0, after: 0, delta: 0 }
  const missingDelta: MetricDelta<number> =
    rawMetrics.missing_percentage ?? { before: 0, after: 0, delta: 0 }
  const dupsDelta: MetricDelta<number> =
    rawMetrics.duplicate_rows ?? { before: 0, after: 0, delta: 0 }

  const normalizedMetrics = {
    ...rawMetrics,
    rows: rowsDelta,
    row_count: rowsDelta,
    columns: colsDelta,
    column_count: colsDelta,
    missing_percentage: missingDelta,
    duplicate_rows: dupsDelta,
  }

  // 4. Heuristic normalization
  const heuristic = raw.heuristic || {
    before_score: null,
    after_score: null,
    delta: null,
    before_rating: null,
    after_rating: null,
    note: 'The heuristic measures data quality/readiness signals, not actual model performance.',
  }

  return {
    ...raw,
    dataset_metrics: normalizedMetrics,
    quality: {
      ...rawQuality,
      issues_resolved: resolved,
      issues_changed: changed,
      issues_unchanged: unchanged,
      new_issues: newCount,
      items,
      issues: items,
      summary,
    },
    heuristic,
  }
}
