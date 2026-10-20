import React from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { DatasetDetailPage } from '../pages/DatasetDetailPage'
import { api } from '../services/api'
import type { Dataset, DatasetVersion } from '../types/dataset'

vi.mock('../services/api')

const columnsV1 = [
  { name: 'legacy_label', dtype: 'string' },
]
const columnsV2 = [
  { name: ' renewal status ', dtype: 'boolean' },
  { name: 'amount', dtype: 'float64' },
]

function makeVersion(
  id: string,
  versionNumber: number,
  columns?: Array<{ name: string; dtype: string }> | null,
): DatasetVersion {
  return {
    id,
    dataset_id: 'dataset-1',
    parent_version_id: versionNumber > 1 ? 'version-1' : null,
    version_number: versionNumber,
    change_summary: null,
    file_name: `data-v${versionNumber}.csv`,
    file_size_bytes: 100,
    sha256_hash: 'a'.repeat(64),
    row_count: 20,
    column_count: columns?.length ?? 0,
    raw_schema: columns === null
      ? undefined as unknown as DatasetVersion['raw_schema']
      : columns === undefined
        ? {}
        : { columns },
    created_at: '2026-10-20T00:00:00Z',
  }
}

function makeDataset(latestVersion = makeVersion('version-2', 2, columnsV2)): Dataset {
  return {
    id: 'dataset-1',
    name: 'Customer dataset',
    description: null,
    created_at: '2026-10-20T00:00:00Z',
    updated_at: '2026-10-20T00:00:00Z',
    versions: [makeVersion('version-1', 1, columnsV1), latestVersion],
  }
}

function renderDatasetDetail(dataset = makeDataset()) {
  vi.mocked(api.getDataset).mockResolvedValue(dataset)
  vi.mocked(api.listVersionAnalyses).mockResolvedValue([])
  vi.mocked(api.triggerAnalysis).mockResolvedValue({
    analysis_run_id: 'analysis-1',
    status: 'PENDING',
  })

  return render(
    <MemoryRouter initialEntries={['/datasets/dataset-1']}>
      <Routes>
        <Route path="/datasets/:id" element={<DatasetDetailPage />} />
        <Route path="/analysis" element={<div>Analysis destination</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

async function openAnalysisModal() {
  await screen.findByText('Customer dataset')
  fireEvent.click(screen.getByRole('button', { name: /Run Analysis/i }))
  await screen.findByRole('heading', { name: 'Trigger Dataset Analysis' })
}

describe('DatasetDetailPage target-aware analysis', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('lists only latest-version schema columns and shows their dtypes', async () => {
    renderDatasetDetail()
    await openAnalysisModal()

    const select = screen.getByRole('combobox', { name: 'Target Column' })
    const options = Array.from(select.querySelectorAll('option')).map((option) => ({
      value: option.value,
      label: option.textContent,
    }))

    expect(options).toEqual([
      { value: '__dataset_doctor_no_target__', label: 'No target (unsupervised analysis)' },
      { value: ' renewal status ', label: ' renewal status  · boolean' },
      { value: 'amount', label: 'amount · float64' },
    ])
    expect(options.some((option) => option.value === 'legacy_label')).toBe(false)
  })

  it('defaults to no target and submits a target-free audit request', async () => {
    renderDatasetDetail()
    await openAnalysisModal()

    const targetSelect = screen.getByRole('combobox', { name: 'Target Column' })
    expect(targetSelect).toHaveDisplayValue('No target (unsupervised analysis)')
    expect(screen.queryByRole('combobox', { name: 'Problem Type' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Start Analysis' }))

    await waitFor(() => {
      expect(api.triggerAnalysis).toHaveBeenCalledWith('dataset-1', 'version-2', {})
    })
    expect(await screen.findByText('Analysis destination')).toBeInTheDocument()
  })

  it.each(['classification', 'regression'])(
    'submits the exact schema target and %s problem type',
    async (problemType) => {
      renderDatasetDetail()
      await openAnalysisModal()

      fireEvent.change(screen.getByRole('combobox', { name: 'Target Column' }), {
        target: { value: ' renewal status ' },
      })
      fireEvent.change(screen.getByRole('combobox', { name: 'Problem Type' }), {
        target: { value: problemType },
      })
      fireEvent.click(screen.getByRole('button', { name: 'Start Analysis' }))

      await waitFor(() => {
        expect(api.triggerAnalysis).toHaveBeenCalledWith('dataset-1', 'version-2', {
          target_column: ' renewal status ',
          problem_type: problemType,
        })
      })
    },
  )

  it('does not submit a column that is absent from the latest schema', async () => {
    renderDatasetDetail()
    await openAnalysisModal()

    const select = screen.getByRole('combobox', { name: 'Target Column' })
    fireEvent.change(select, { target: { value: 'not-in-schema' } })
    expect(select).toHaveDisplayValue('No target (unsupervised analysis)')
    expect(screen.queryByRole('option', { name: 'not-in-schema' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Start Analysis' }))
    await waitFor(() => {
      expect(api.triggerAnalysis).toHaveBeenCalledWith('dataset-1', 'version-2', {})
    })
  })

  it.each([
    { label: 'missing schema', version: makeVersion('version-2', 2, null) },
    { label: 'empty schema', version: makeVersion('version-2', 2, []) },
  ])('handles $label with clear guidance and keeps target-free analysis available', async ({ version }) => {
    renderDatasetDetail(makeDataset(version))
    await openAnalysisModal()

    expect(screen.getByText(/No columns are available for this version/i)).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Target Column' })).toHaveDisplayValue('No target (unsupervised analysis)')
    expect(screen.getByRole('button', { name: 'Start Analysis' })).toBeEnabled()
  })

  it('shows a string FastAPI validation detail instead of Axios status text', async () => {
    renderDatasetDetail()
    await openAnalysisModal()
    vi.mocked(api.triggerAnalysis).mockRejectedValueOnce({
      response: { status: 422, data: { detail: 'The selected target is not valid.' } },
      message: 'Request failed with status code 422',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Start Analysis' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('The selected target is not valid.')
    expect(screen.getByRole('alert')).not.toHaveTextContent('Request failed with status code 422')
  })

  it('formats validation detail arrays without displaying raw input or object values', async () => {
    renderDatasetDetail()
    await openAnalysisModal()
    vi.mocked(api.triggerAnalysis).mockRejectedValueOnce({
      response: {
        status: 422,
        data: {
          detail: [
            {
              type: 'value_error',
              loc: ['body', 'target_column'],
              msg: 'Unknown target column',
              input: { private: 'unneeded detail' },
            },
          ],
        },
      },
      message: 'Request failed with status code 422',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Start Analysis' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('target column: Unknown target column')
    expect(alert).not.toHaveTextContent('[object Object]')
    expect(alert).not.toHaveTextContent('unneeded detail')
  })

  it('uses a safe fallback for unexpected Axios error shapes', async () => {
    renderDatasetDetail()
    await openAnalysisModal()
    vi.mocked(api.triggerAnalysis).mockRejectedValueOnce({
      response: { status: 422, data: { detail: { unexpected: { nested: true } } } },
      message: 'Request failed with status code 422',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Start Analysis' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Could not start analysis. Check the selected target and try again.')
    expect(alert).not.toHaveTextContent('[object Object]')
    expect(alert).not.toHaveTextContent('422')
  })
})
