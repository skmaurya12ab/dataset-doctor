import React from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SeverityBadge } from '../components/SeverityBadge'
import { MetricCard } from '../components/MetricCard'
import { ReadinessCard } from '../components/ReadinessCard'
import { IssueTable } from '../components/IssueTable'
import { AIExplanationModal } from '../components/AIExplanationModal'
import { RemediationStatusBadge } from '../components/RemediationStatusBadge'
import { ApprovalModal } from '../components/ApprovalModal'
import { VersionComparisonView } from '../components/VersionComparisonView'
import type { QualityIssue, HeuristicBreakdown } from '../types/analysis'
import type { FindingExplanationResponse, TransformationSpec } from '../types/ai'
import type { VersionComparison } from '../types/remediation'

describe('SeverityBadge', () => {
  it('renders CRITICAL severity with accessible label', () => {
    render(<SeverityBadge severity="CRITICAL" />)
    const badge = screen.getByRole('status')
    expect(badge).toHaveTextContent('CRITICAL')
    expect(badge).toHaveAttribute('aria-label', 'Severity: CRITICAL')
  })

  it('renders HIGH and LOW severity accurately', () => {
    const { rerender } = render(<SeverityBadge severity="HIGH" />)
    expect(screen.getByText('HIGH')).toBeInTheDocument()

    rerender(<SeverityBadge severity="LOW" />)
    expect(screen.getByText('LOW')).toBeInTheDocument()
  })
})

describe('MetricCard', () => {
  it('renders metric label, value, and positive delta', () => {
    render(
      <MetricCard
        label="Dataset Rows"
        value="12,500"
        delta={250}
        deltaLabel="rows"
        subtext="Total instances"
      />,
    )
    expect(screen.getByText('Dataset Rows')).toBeInTheDocument()
    expect(screen.getByText('12,500')).toBeInTheDocument()
    expect(screen.getByText('+250 rows')).toBeInTheDocument()
    expect(screen.getByText('Total instances')).toBeInTheDocument()
  })
})

describe('ReadinessCard', () => {
  it('renders score, rating, itemized deductions, and disclaimer', () => {
    const breakdown: HeuristicBreakdown = {
      heuristic_score: 58.0,
      rating: 'Poor',
      base_score: 100.0,
      total_penalties: 42.0,
      disclaimer: 'The heuristic measures data quality/readiness signals, not actual model performance.',
      itemized_penalties: [
        {
          module: 'missing_analyzer',
          severity: 'CRITICAL',
          reason: 'Severe null percentage in target feature',
          penalty: 25.0,
          column_name: 'income',
        },
      ],
    }

    render(<ReadinessCard score={58.0} breakdown={breakdown} />)
    expect(screen.getByText('58')).toBeInTheDocument()
    expect(screen.getByText('/ 100')).toBeInTheDocument()
    expect(screen.getByText('POOR')).toBeInTheDocument()
    expect(screen.getByText(/income: Severe null percentage/)).toBeInTheDocument()
    expect(screen.getByText('-25 pts')).toBeInTheDocument()
    expect(screen.getByText(/The heuristic measures data quality\/readiness signals/)).toBeInTheDocument()
  })
})

describe('IssueTable', () => {
  const mockIssues: QualityIssue[] = [
    {
      id: 'issue-1',
      analysis_run_id: 'run-1',
      dataset_version_id: 'ver-1',
      module: 'missing_analyzer',
      analyzer_version: '1.0.0',
      parameters_used: {},
      category: 'HIGH_NULL_RATE',
      severity: 'CRITICAL',
      column_name: 'age',
      title: 'High missingness in age',
      description: 'Over 40% missing values detected in column age',
      evidence: { null_count: 400 },
      remediation_hint: 'Impute median value',
      detected_at: '2026-10-06T12:00:00Z',
    },
    {
      id: 'issue-2',
      analysis_run_id: 'run-1',
      dataset_version_id: 'ver-1',
      module: 'duplicate_analyzer',
      analyzer_version: '1.0.0',
      parameters_used: {},
      category: 'DUPLICATE_ROWS',
      severity: 'HIGH',
      column_name: null,
      title: 'Duplicate rows found',
      description: 'Found 12 duplicate records',
      evidence: { duplicate_count: 12 },
      remediation_hint: 'Deduplicate rows',
      detected_at: '2026-10-06T12:00:00Z',
    },
  ]

  it('renders issues and triggers onExplainIssue callback', () => {
    const handleExplain = vi.fn()
    render(<IssueTable issues={mockIssues} onExplainIssue={handleExplain} />)

    expect(screen.getByText('High missingness in age')).toBeInTheDocument()
    expect(screen.getByText('Duplicate rows found')).toBeInTheDocument()

    const explainButtons = screen.getAllByRole('button', { name: /Explain/i })
    fireEvent.click(explainButtons[0])
    expect(handleExplain).toHaveBeenCalledWith(mockIssues[0])
  })

  it('filters issues by search query', () => {
    render(<IssueTable issues={mockIssues} />)
    const searchInput = screen.getByPlaceholderText(/Search issues/i)
    fireEvent.change(searchInput, { target: { value: 'duplicate' } })

    expect(screen.getByText('Duplicate rows found')).toBeInTheDocument()
    expect(screen.queryByText('High missingness in age')).not.toBeInTheDocument()
  })
})

describe('AIExplanationModal', () => {
  const mockIssue: QualityIssue = {
    id: 'iss-1',
    analysis_run_id: 'run-1',
    dataset_version_id: 'ver-1',
    module: 'leakage_analyzer',
    analyzer_version: '1.0.0',
    parameters_used: {},
    category: 'TARGET_IDENTITY',
    severity: 'CRITICAL',
    column_name: 'target_id',
    title: 'Target identity detected',
    description: 'Column is identical to target label',
    evidence: {},
    detected_at: '2026-10-06T12:00:00Z',
  }

  const mockExplanation: FindingExplanationResponse = {
    issue_id: 'iss-1',
    provider: 'openai',
    model: 'gpt-4o-mini',
    prompt_version: 'v1.0.0',
    explanation: 'The feature contains identical information to the target variable.',
    why_it_matters: 'This causes complete data leakage during validation.',
    practical_impact: 'The trained model will severely overfit.',
    recommended_actions: ['Drop the target_id column before training'],
    limitations: ['Deterministic check cannot infer domain causality'],
    created_at: '2026-10-06T12:00:00Z',
  }

  it('renders grounded AI explanation with provenance and disclaimer', () => {
    render(
      <AIExplanationModal
        isOpen={true}
        onClose={vi.fn()}
        issue={mockIssue}
        explanation={mockExplanation}
        isLoading={false}
      />,
    )

    expect(screen.getByText('AI Finding Explanation')).toBeInTheDocument()
    expect(screen.getByText('The feature contains identical information to the target variable.')).toBeInTheDocument()
    expect(screen.getByText('This causes complete data leakage during validation.')).toBeInTheDocument()
    expect(screen.getByText('Drop the target_id column before training')).toBeInTheDocument()
    expect(screen.getByText(/AI-generated explanation:/)).toBeInTheDocument()
    expect(screen.getByText(/Model: gpt-4o-mini/)).toBeInTheDocument()
  })

  it('renders loading spinner while generating explanation', () => {
    render(
      <AIExplanationModal
        isOpen={true}
        onClose={vi.fn()}
        issue={mockIssue}
        explanation={null}
        isLoading={true}
      />,
    )
    expect(screen.getByText(/Generating grounded AI explanation/i)).toBeInTheDocument()
  })
})

describe('ApprovalModal', () => {
  const mockSpecs: TransformationSpec[] = [
    {
      action: 'REMOVE_DUPLICATES',
      column: null,
      parameters: { keep: 'first' },
      rationale: 'Remove redundant records',
      source_issue_ids: ['iss-1'],
    },
    {
      action: 'IMPUTE',
      column: 'age',
      parameters: { strategy: 'median' },
      rationale: 'Impute missing values',
      source_issue_ids: ['iss-2'],
    },
  ]

  it('disables apply button until explicit approval checkbox is checked', () => {
    const handleApprove = vi.fn()
    render(
      <ApprovalModal
        isOpen={true}
        onClose={vi.fn()}
        onApprove={handleApprove}
        transformationSpecs={mockSpecs}
        isApplying={false}
      />,
    )

    const applyButton = screen.getByRole('button', { name: /Approve & Apply/i })
    expect(applyButton).toBeDisabled()

    const checkbox = screen.getByRole('checkbox')
    fireEvent.click(checkbox)
    expect(applyButton).toBeEnabled()

    fireEvent.click(applyButton)
    expect(handleApprove).toHaveBeenCalledWith('data-engineer')
  })
})

describe('RemediationStatusBadge', () => {
  it('renders various lifecycle states correctly', () => {
    const { rerender } = render(<RemediationStatusBadge status="PENDING_APPROVAL" />)
    expect(screen.getByText('Pending Approval')).toBeInTheDocument()

    rerender(<RemediationStatusBadge status="RUNNING" />)
    expect(screen.getByText('Applying Transformations...')).toBeInTheDocument()

    rerender(<RemediationStatusBadge status="COMPLETED" />)
    expect(screen.getByText('Completed')).toBeInTheDocument()

    rerender(<RemediationStatusBadge status="FAILED" />)
    expect(screen.getByText('Failed (Data Preserved)')).toBeInTheDocument()
  })
})

describe('VersionComparisonView', () => {
  const mockComparison: VersionComparison = {
    dataset_id: 'ds-1',
    before: { version_id: 'v1-id', version_number: 1 },
    after: { version_id: 'v2-id', version_number: 2 },
    dataset_metrics: {
      row_count: { before: 1000, after: 980, delta: -20 },
      column_count: { before: 10, after: 9, delta: -1 },
      missing_percentage: { before: 23.5, after: 4.1, delta: -19.4 },
      duplicate_rows: { before: 20, after: 0, delta: -20 },
    },
    quality: {
      summary: {
        total_before: 12,
        total_after: 5,
        resolved_count: 7,
        changed_count: 2,
        unchanged_count: 3,
        new_count: 0,
        critical_before: 2,
        critical_after: 0,
      },
      issues: [
        {
          semantic_key: 'missing_analyzer:HIGH_NULL_RATE:age',
          module: 'missing_analyzer',
          category: 'HIGH_NULL_RATE',
          column: 'age',
          status: 'RESOLVED',
          before_severity: 'CRITICAL',
          after_severity: null,
          details: { note: 'Imputed successfully' },
        },
      ],
    },
    heuristic: {
      before_score: 58.0,
      after_score: 84.0,
      delta: 26.0,
      before_rating: 'Poor',
      after_rating: 'Good',
      note: 'The heuristic measures data quality/readiness signals, not actual model performance.',
    },
  }

  it('renders before/after versions, metric deltas, and lifecycle transition counts', () => {
    render(<VersionComparisonView comparison={mockComparison} />)

    expect(screen.getByText('VERSION 1')).toBeInTheDocument()
    expect(screen.getByText('VERSION 2')).toBeInTheDocument()

    // Heuristic scores and delta
    expect(screen.getByText('58')).toBeInTheDocument()
    expect(screen.getByText('84')).toBeInTheDocument()
    expect(screen.getByText('+26')).toBeInTheDocument()

    // Defect lifecycle summary counts
    expect(screen.getAllByText('RESOLVED').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('7')).toBeInTheDocument() // resolved_count
    expect(screen.getAllByText('UNCHANGED').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('3')).toBeInTheDocument() // unchanged_count

    // Metric delta
    expect(screen.getByText('-19.4 %')).toBeInTheDocument()
  })
})
