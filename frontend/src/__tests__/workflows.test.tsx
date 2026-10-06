import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { OverviewPage } from '../pages/OverviewPage'
import { DatasetsPage } from '../pages/DatasetsPage'
import { VersionDetailPage } from '../pages/VersionDetailPage'
import { api } from '../services/api'
import type { OverviewStats } from '../types/analysis'
import type { DatasetListItem, DatasetVersion } from '../types/dataset'

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
