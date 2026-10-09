import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { ComparisonPage } from '../pages/ComparisonPage'
import { VersionComparisonView } from '../components/VersionComparisonView'
import { normalizeVersionComparison } from '../utils/versionComparison'
import { api } from '../services/api'
import type { VersionComparison } from '../types/remediation'
import type { Dataset, DatasetListItem } from '../types/dataset'

vi.mock('../services/api')

describe('Versions Page & VersionComparisonView Regression Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mockDatasetItem: DatasetListItem = {
    dataset_id: 'ds-test-1',
    name: 'Customer Churn Data',
    description: null,
    latest_version_number: 2,
    latest_row_count: 500,
    latest_column_count: 5,
    created_at: '2026-10-09T10:00:00Z',
    updated_at: '2026-10-09T10:00:00Z',
  }

  const mockDataset: Dataset = {
    id: 'ds-test-1',
    name: 'Customer Churn Data',
    description: null,
    created_at: '2026-10-09T10:00:00Z',
    updated_at: '2026-10-09T10:00:00Z',
    versions: [
      {
        id: 'ver-source-1',
        dataset_id: 'ds-test-1',
        version_number: 1,
        file_name: 'churn_v1.csv',
        file_size_bytes: 12000,
        sha256_hash: 'hash-v1',
        row_count: 500,
        column_count: 5,
        raw_schema: { columns: [] },
        created_at: '2026-10-09T10:00:00Z',
      },
      {
        id: 'ver-target-2',
        dataset_id: 'ds-test-1',
        version_number: 2,
        file_name: 'churn_v2.parquet',
        file_size_bytes: 11000,
        sha256_hash: 'hash-v2',
        row_count: 495,
        column_count: 5,
        raw_schema: { columns: [] },
        created_at: '2026-10-09T11:00:00Z',
      },
    ],
  }

  // 1. Exact raw response returned by the backend ComparisonService
  const actualBackendComparisonResponse: any = {
    dataset_id: 'ds-test-1',
    before: {
      version_id: 'ver-source-1',
      version_number: 1,
      file_name: 'churn_v1.csv',
      created_at: '2026-10-09T10:00:00Z',
      analysis_run_id: 'run-v1',
    },
    after: {
      version_id: 'ver-target-2',
      version_number: 2,
      file_name: 'churn_v2.parquet',
      created_at: '2026-10-09T11:00:00Z',
      analysis_run_id: 'run-v2',
    },
    dataset_metrics: {
      rows: { before: 500, after: 495, delta: -5 },
      columns: { before: 5, after: 5, delta: 0 },
      missing_cells: { before: 20, after: 0, delta: -20 },
      missing_percentage: { before: 0.8, after: 0.0, delta: -0.8 },
      duplicate_rows: { before: 5, after: 0, delta: -5 },
      total_issues: { before: 4, after: 1, delta: -3 },
      critical_issues: { before: 1, after: 0, delta: -1 },
    },
    quality: {
      issues_resolved: 3,
      issues_changed: 0,
      issues_unchanged: 1,
      new_issues: 0,
      items: [
        {
          semantic_key: 'missing_analyzer:MISSING_VALUES:income',
          module: 'missing_analyzer',
          category: 'MISSING_VALUES',
          column: 'income',
          status: 'RESOLVED',
          before_severity: 'HIGH',
          after_severity: null,
          details: { resolution: 'Defect successfully resolved in remediated version' },
        },
        {
          semantic_key: 'duplicate_analyzer:DUPLICATES:',
          module: 'duplicate_analyzer',
          category: 'DUPLICATES',
          column: null,
          status: 'RESOLVED',
          before_severity: 'CRITICAL',
          after_severity: null,
          details: { resolution: 'Defect successfully resolved in remediated version' },
        },
        {
          semantic_key: 'outlier_analyzer:OUTLIERS:age',
          module: 'outlier_analyzer',
          category: 'OUTLIERS',
          column: 'age',
          status: 'RESOLVED',
          before_severity: 'MEDIUM',
          after_severity: null,
          details: { resolution: 'Defect successfully resolved in remediated version' },
        },
        {
          semantic_key: 'imbalance_analyzer:CLASS_IMBALANCE:churn',
          module: 'imbalance_analyzer',
          category: 'CLASS_IMBALANCE',
          column: 'churn',
          status: 'UNCHANGED',
          before_severity: 'LOW',
          after_severity: 'LOW',
          details: { note: 'Defect remains present with unchanged severity' },
        },
      ],
    },
    heuristic: {
      before_score: 55.0,
      after_score: 85.0,
      delta: 30.0,
      before_rating: 'MODERATE',
      after_rating: 'EXCELLENT',
      note: 'The heuristic measures data quality/readiness signals, not actual model performance.',
    },
  }

  it('normalizes actual backend response shape without throwing quality.issues error', () => {
    const normalized = normalizeVersionComparison(actualBackendComparisonResponse)

    expect(Array.isArray(normalized.quality.issues)).toBe(true)
    expect(normalized.quality.issues!.length).toBe(4)
    expect(normalized.quality.summary!.resolved_count).toBe(3)
    expect(normalized.quality.summary!.unchanged_count).toBe(1)
    expect(normalized.dataset_metrics.row_count!.after).toBe(495)
    expect(normalized.dataset_metrics.column_count!.after).toBe(5)
  })

  it('1. renders Versions page with valid issue data from actual backend schema', async () => {
    vi.mocked(api.listDatasets).mockResolvedValue([mockDatasetItem])
    vi.mocked(api.getDataset).mockResolvedValue(mockDataset)
    vi.mocked(api.compareVersions).mockResolvedValue(
      normalizeVersionComparison(actualBackendComparisonResponse),
    )

    render(
      <MemoryRouter initialEntries={['/versions?datasetId=ds-test-1&v1=ver-source-1&v2=ver-target-2']}>
        <Routes>
          <Route path="/versions" element={<ComparisonPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('VERSION 1')).toBeInTheDocument()
      expect(screen.getByText('VERSION 2')).toBeInTheDocument()
      expect(screen.getByText('3')).toBeInTheDocument() // resolved_count
      expect(screen.getByText('1')).toBeInTheDocument() // unchanged_count
      expect(screen.getByText('income')).toBeInTheDocument()
      expect(screen.getByText('churn')).toBeInTheDocument()
      expect(
        screen.getAllByText('Defect successfully resolved in remediated version').length,
      ).toBe(3)
    })
  })

  it('2. renders Versions page with an empty issue array without crashing', async () => {
    const emptyIssuesComparison: VersionComparison = normalizeVersionComparison({
      ...actualBackendComparisonResponse,
      quality: {
        issues_resolved: 0,
        issues_changed: 0,
        issues_unchanged: 0,
        new_issues: 0,
        items: [],
      },
    })

    vi.mocked(api.listDatasets).mockResolvedValue([mockDatasetItem])
    vi.mocked(api.getDataset).mockResolvedValue(mockDataset)
    vi.mocked(api.compareVersions).mockResolvedValue(emptyIssuesComparison)

    render(
      <MemoryRouter initialEntries={['/versions?datasetId=ds-test-1&v1=ver-source-1&v2=ver-target-2']}>
        <Routes>
          <Route path="/versions" element={<ComparisonPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText("No issues matching filter 'ALL'.")).toBeInTheDocument()
      expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(1)
    })
  })


  it('3. renders informative banner when versions do not have completed analysis runs', async () => {
    const unanalyzedComparison: VersionComparison = normalizeVersionComparison({
      ...actualBackendComparisonResponse,
      before: {
        ...actualBackendComparisonResponse.before,
        analysis_run_id: null,
      },
      after: {
        ...actualBackendComparisonResponse.after,
        analysis_run_id: null,
      },
      heuristic: {
        before_score: null,
        after_score: null,
        delta: null,
        before_rating: null,
        after_rating: null,
        note: 'The heuristic measures data quality/readiness signals, not actual model performance.',
      },
      quality: {
        issues_resolved: 0,
        issues_changed: 0,
        issues_unchanged: 0,
        new_issues: 0,
        items: [],
      },
    })

    vi.mocked(api.listDatasets).mockResolvedValue([mockDatasetItem])
    vi.mocked(api.getDataset).mockResolvedValue(mockDataset)
    vi.mocked(api.compareVersions).mockResolvedValue(unanalyzedComparison)

    render(
      <MemoryRouter initialEntries={['/versions?datasetId=ds-test-1&v1=ver-source-1&v2=ver-target-2']}>
        <Routes>
          <Route path="/versions" element={<ComparisonPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(
        screen.getByText(/Neither version has a completed analysis run/i),
      ).toBeInTheDocument()
      expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('4. gracefully handles missing/incomplete quality and metrics response data', () => {
    const minimalResponse: any = {
      dataset_id: 'ds-min',
      before: { version_id: 'v1', version_number: 1 },
      after: { version_id: 'v2', version_number: 2 },
      dataset_metrics: {},
      quality: {},
      heuristic: {},
    }

    const normalized = normalizeVersionComparison(minimalResponse)
    expect(normalized.quality.issues).toEqual([])
    expect(normalized.quality.summary?.resolved_count).toBe(0)

    render(<VersionComparisonView comparison={minimalResponse} />)
    expect(screen.getByText('VERSION 1')).toBeInTheDocument()
    expect(screen.getByText('VERSION 2')).toBeInTheDocument()
    expect(screen.getByText("No issues matching filter 'ALL'.")).toBeInTheDocument()
  })

  it('5. filters issues list dynamically when filter pills are clicked', async () => {
    render(<VersionComparisonView comparison={actualBackendComparisonResponse} />)

    expect(screen.getByText('income')).toBeInTheDocument()
    expect(screen.getByText('churn')).toBeInTheDocument()

    // Filter to RESOLVED issues only
    const resolvedBtn = screen.getByRole('button', { name: 'RESOLVED' })
    fireEvent.click(resolvedBtn)

    expect(screen.getByText('income')).toBeInTheDocument()
    expect(screen.queryByText('churn')).not.toBeInTheDocument()

    // Filter to NEW issues only (there are 0 NEW issues)
    const newBtn = screen.getByRole('button', { name: 'NEW' })
    fireEvent.click(newBtn)

    expect(screen.getByText("No issues matching filter 'NEW'.")).toBeInTheDocument()
  })

  it('6. handles direct navigation to /versions with automatic multi-version dataset selection', async () => {
    vi.mocked(api.listDatasets).mockResolvedValue([mockDatasetItem])
    vi.mocked(api.getDataset).mockResolvedValue(mockDataset)
    vi.mocked(api.compareVersions).mockResolvedValue(
      normalizeVersionComparison(actualBackendComparisonResponse),
    )

    render(
      <MemoryRouter initialEntries={['/versions']}>
        <Routes>
          <Route path="/versions" element={<ComparisonPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('Version Comparison & Audit')).toBeInTheDocument()
      expect(screen.getByText('VERSION 1')).toBeInTheDocument()
      expect(screen.getByText('VERSION 2')).toBeInTheDocument()
    })
  })

  it('7. navigates with v1 and v2 params without datasetId and resolves parent dataset', async () => {
    vi.mocked(api.listDatasets).mockResolvedValue([mockDatasetItem])
    vi.mocked(api.getDataset).mockResolvedValue(mockDataset)
    vi.mocked(api.compareVersions).mockResolvedValue(
      normalizeVersionComparison(actualBackendComparisonResponse),
    )

    render(
      <MemoryRouter initialEntries={['/versions?v1=ver-source-1&v2=ver-target-2']}>
        <Routes>
          <Route path="/versions" element={<ComparisonPage />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(api.compareVersions).toHaveBeenCalledWith(
        'ds-test-1',
        'ver-source-1',
        'ver-target-2',
      )
      expect(screen.getByText('VERSION 1')).toBeInTheDocument()
      expect(screen.getByText('VERSION 2')).toBeInTheDocument()
    })
  })
})
