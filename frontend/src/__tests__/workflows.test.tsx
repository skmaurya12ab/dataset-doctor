import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { OverviewPage } from '../pages/OverviewPage'
import { DatasetsPage } from '../pages/DatasetsPage'
import { VersionDetailPage } from '../pages/VersionDetailPage'
import { RemediationPage } from '../pages/RemediationPage'
import { api } from '../services/api'
import type { OverviewStats, AnalysisRun } from '../types/analysis'
import type { DatasetListItem, DatasetVersion } from '../types/dataset'
import type { AIReport } from '../types/ai'

vi.mock('../services/api')

describe('OverviewPage Workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state initially', () => {
    vi.mocked(api.getOverviewStats).mockReturnValue(new Promise(() => {}))
    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    )
    expect(screen.getByText(/Loading system overview/i)).toBeInTheDocument()
  })

  it('renders overview telemetry when API resolves', async () => {
    const mockStats: OverviewStats = {
      total_datasets: 3,
      total_versions: 7,
      running_analyses_count: 1,
      latest_analyses: [],
      recent_remediations: [],
      unresolved_critical_issues_count: 2,
      unresolved_high_issues_count: 4,
      average_readiness_score: 72.5,
    }
    vi.mocked(api.getOverviewStats).mockResolvedValue(mockStats)

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('System Overview')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument() // Total datasets
      expect(screen.getByText('7')).toBeInTheDocument() // Immutable versions
    })
  })
})

describe('DatasetsPage Workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders dataset list table and version numbers', async () => {
    const mockDatasets: DatasetListItem[] = [
      {
        dataset_id: 'ds-123',
        name: 'Credit Risk 2026',
        description: 'Loan default records',
        latest_version_number: 2,
        latest_row_count: 5000,
        latest_column_count: 14,
        created_at: '2026-10-06T10:00:00Z',
        updated_at: '2026-10-06T11:00:00Z',
      },
    ]
    vi.mocked(api.listDatasets).mockResolvedValue(mockDatasets)

    render(
      <MemoryRouter>
        <DatasetsPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Credit Risk 2026')).toBeInTheDocument()
      expect(screen.getByText('v2')).toBeInTheDocument()
      expect(screen.getByText('5,000')).toBeInTheDocument()
    })
  })
})

describe('VersionDetailPage Workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders version metadata, checksum, and tabular schema', async () => {
    const mockVersion: DatasetVersion = {
      id: 'ver-999',
      dataset_id: 'ds-123',
      parent_version_id: null,
      version_number: 1,
      change_summary: 'Initial parquet ingestion',
      file_name: 'credit_risk_v1.parquet',
      file_size_bytes: 45000,
      sha256_hash: 'a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0',
      row_count: 2400,
      column_count: 3,
      raw_schema: {
        columns: [
          { name: 'user_id', dtype: 'int64' },
          { name: 'income', dtype: 'float64' },
          { name: 'defaulted', dtype: 'boolean' },
        ],
      },
      created_at: '2026-10-06T10:00:00Z',
    }

    vi.mocked(api.getDatasetVersion).mockResolvedValue(mockVersion)
    vi.mocked(api.previewDatasetVersion).mockResolvedValue({
      dataset_id: 'ds-123',
      version_number: 1,
      total_rows: 2400,
      total_columns: 3,
      file_size_bytes: 45000,
      columns: ['user_id', 'income', 'defaulted'],
      dtypes: { user_id: 'int64', income: 'float64', defaulted: 'boolean' },
      rows: [{ user_id: 1, income: 55000, defaulted: false }],
      limit: 10,
      offset: 0,
    })

    render(
      <MemoryRouter initialEntries={['/datasets/ds-123/versions/ver-999']}>
        <Routes>
          <Route
            path="/datasets/:datasetId/versions/:versionId"
            element={<VersionDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText(/Dataset Version v1/)).toBeInTheDocument()
      expect(screen.getAllByText('user_id').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('income').length).toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('defaulted').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText(/a1b2c3d4e5f67890123456789abcdef0/)).toBeInTheDocument()
    })
  })
})

describe('RemediationPage Workflow & Blank Screen Regression', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mockRun: AnalysisRun = {
    id: 'run-987',
    dataset_version_id: 'ver-abc',
    status: 'COMPLETED',
    target_column: 'target',
    problem_type: 'classification',
    engine_version: '1.0.0',
    analyzer_versions: {},
    ml_readiness_score: 48.0,
    heuristic_breakdown: {
      rating: 'High risk / substantial remediation',
      base_score: 100,
      disclaimer: 'test disclaimer',
      heuristic_score: 48,
      total_penalties: 52,
      itemized_penalties: [],
    },
    total_issues_count: 4,
    critical_issues_count: 1,
    execution_time_ms: 150,
    summary_metrics: {
      row_count: 500,
      column_count: 6,
      overall_missing_percentage: 1.5,
      ml_readiness_score: 48,
      ml_readiness_rating: 'High risk / substantial remediation',
    },
    error_message: null,
    created_at: '2026-10-09T10:00:00Z',
    completed_at: '2026-10-09T10:00:01Z',
  }

  const rawBackendAIReport = {
    id: 'rep-999',
    analysis_run_id: 'run-987',
    provider: 'mock-provider',
    model: 'gpt-4o-2024-08-06',
    prompt_version: '1.0.0',
    executive_summary: 'Comprehensive remediation plan synthesized from deterministic quality findings.',
    risk_assessment: [
      {
        category: 'Missingness Risk',
        severity: 'HIGH' as const,
        summary: 'Detected high missing percentage in age',
        ml_impact: 'Reduces estimator statistical efficiency',
      },
    ],
    remediation_plan: [
      {
        priority: 1,
        issue_reference: 'missing_age',
        problem: 'Null entries in age',
        recommendation: 'Impute median',
        reason: 'Preserves variance',
        risk: 'Underestimated tails',
      },
    ],
    transformation_specs: [
      {
        action: 'IMPUTE' as const,
        column: 'age',
        parameters: { strategy: 'median' },
        rationale: 'Impute missing age centrally',
        source_issue_ids: ['iss-1'],
      },
    ],
    ml_preparation_plan: ['Step 1: Impute missing numerical columns.'],
    generated_python_code: '# Python snippet',
    cached: true,
    created_at: '2026-10-09T10:00:00Z',
  }

  it('renders RemediationPage without crashing when API returns top-level backend payload (blank screen prevention)', async () => {
    vi.mocked(api.getAnalysisRun).mockResolvedValue(mockRun)
    // Return raw backend structure (without pre-existing nested .content)
    vi.mocked(api.getAIPlan).mockResolvedValue(rawBackendAIReport as unknown as AIReport)

    render(
      <MemoryRouter initialEntries={['/remediation?runId=run-987']}>
        <Routes>
          <Route path="/remediation" element={<RemediationPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Remediation & Execution Workflow')).toBeInTheDocument()
      expect(screen.getByText(/Comprehensive remediation plan synthesized/i)).toBeInTheDocument()
      expect(screen.getByText(/Proposed Transformations \(1\)/i)).toBeInTheDocument()
      expect(screen.getByText(/#1 IMPUTE/i)).toBeInTheDocument()
      expect(screen.getAllByText(/Review & Approve Plan/i).length).toBeGreaterThanOrEqual(1)
    })
  })

  it('renders RemediationPage on direct /remediation without runId by falling back to latest completed analysis', async () => {
    const mockOverview: OverviewStats = {
      total_datasets: 1,
      total_versions: 2,
      running_analyses_count: 0,
      latest_analyses: [mockRun],
      recent_remediations: [],
      unresolved_critical_issues_count: 1,
      unresolved_high_issues_count: 2,
      average_readiness_score: 48,
    }
    vi.mocked(api.getOverviewStats).mockResolvedValue(mockOverview)
    vi.mocked(api.getAnalysisRun).mockResolvedValue(mockRun)
    vi.mocked(api.getAIPlan).mockResolvedValue(rawBackendAIReport as unknown as AIReport)

    render(
      <MemoryRouter initialEntries={['/remediation']}>
        <Routes>
          <Route path="/remediation" element={<RemediationPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Remediation & Execution Workflow')).toBeInTheDocument()
      expect(screen.getByText(/Proposed Transformations \(1\)/i)).toBeInTheDocument()
    })
  })

  it('renders meaningful error card inside layout when analysis run fetch fails', async () => {
    vi.mocked(api.getAnalysisRun).mockRejectedValue(new Error('Network error 502 Bad Gateway'))

    render(
      <MemoryRouter initialEntries={['/remediation?runId=invalid-run']}>
        <Routes>
          <Route path="/remediation" element={<RemediationPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText(/Failed to load analysis for remediation/i)).toBeInTheDocument()
      expect(screen.getByText(/Network error 502 Bad Gateway/i)).toBeInTheDocument()
    })
  })

  it('renders empty prompt CTA when analysis run has no AI plan yet', async () => {
    vi.mocked(api.getAnalysisRun).mockResolvedValue(mockRun)
    vi.mocked(api.getAIPlan).mockRejectedValue(new Error('404 Not Found'))

    render(
      <MemoryRouter initialEntries={['/remediation?runId=run-987']}>
        <Routes>
          <Route path="/remediation" element={<RemediationPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('No Remediation Plan Synthesized Yet')).toBeInTheDocument()
      expect(screen.getByText(/Synthesize Advisory Plan/i)).toBeInTheDocument()
    })
  })
})
