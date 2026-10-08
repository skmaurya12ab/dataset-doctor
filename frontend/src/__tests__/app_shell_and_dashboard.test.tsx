import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar } from '../components/Sidebar'
import { Header } from '../components/Header'
import { OverviewPage } from '../pages/OverviewPage'
import { SettingsPage } from '../pages/SettingsPage'
import { api } from '../services/api'
import type { OverviewStats } from '../types/analysis'

vi.mock('../services/api')

describe('Application Shell - Navigation & Header', () => {
  it('renders all primary navigation links in Sidebar', () => {
    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    expect(screen.getByText('Dataset Doctor')).toBeInTheDocument()
    expect(screen.getByText('Overview')).toBeInTheDocument()
    expect(screen.getByText('Datasets')).toBeInTheDocument()
    expect(screen.getByText('Analysis')).toBeInTheDocument()
    expect(screen.getByText('Remediation')).toBeInTheDocument()
    expect(screen.getByText('Versions')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('renders Header with breadcrumb hierarchy', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <Header />
      </MemoryRouter>,
    )

    expect(screen.getByText('App')).toBeInTheDocument()
    expect(screen.getByText('Overview')).toBeInTheDocument()
  })
})

describe('Dashboard - OverviewPage States', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading spinner initially while fetching telemetry', () => {
    vi.mocked(api.getOverviewStats).mockReturnValue(new Promise(() => {}))
    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Loading system overview/i)).toBeInTheDocument()
  })

  it('renders error banner when Overview API fails with 502 Bad Gateway', async () => {
    vi.mocked(api.getOverviewStats).mockRejectedValue(
      new Error('Request failed with status code 502'),
    )

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText(/Unable to load overview statistics/i)).toBeInTheDocument()
      expect(screen.getByText(/Request failed with status code 502/i)).toBeInTheDocument()
    })
  })

  it('renders empty-state illustration when 0 datasets exist in database', async () => {
    const emptyStats: OverviewStats = {
      total_datasets: 0,
      total_versions: 0,
      running_analyses_count: 0,
      latest_analyses: [],
      recent_remediations: [],
      unresolved_critical_issues_count: 0,
      unresolved_high_issues_count: 0,
      average_readiness_score: null,
    }
    vi.mocked(api.getOverviewStats).mockResolvedValue(emptyStats)

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('No datasets ingested yet')).toBeInTheDocument()
      expect(
        screen.getByText(/Dataset Doctor ingests CSV, XLSX, JSON, and Parquet files/i),
      ).toBeInTheDocument()
    })
  })

  it('renders populated statistics and telemetry cards when resolved', async () => {
    const populatedStats: OverviewStats = {
      total_datasets: 5,
      total_versions: 12,
      running_analyses_count: 2,
      latest_analyses: [],
      recent_remediations: [],
      unresolved_critical_issues_count: 3,
      unresolved_high_issues_count: 8,
      average_readiness_score: 79.4,
    }
    vi.mocked(api.getOverviewStats).mockResolvedValue(populatedStats)

    render(
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(screen.getByText('System Overview')).toBeInTheDocument()
      expect(screen.getByText('5')).toBeInTheDocument() // Datasets
      expect(screen.getByText('12')).toBeInTheDocument() // Versions
      expect(screen.getByText('3')).toBeInTheDocument() // Critical issues
      expect(screen.getByText('+8 high issues')).toBeInTheDocument() // High issues subtext
    })
  })
})

describe('SettingsPage', () => {
  it('renders application settings and environment configurations', () => {
    render(
      <MemoryRouter>
        <SettingsPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('Settings & System Architecture')).toBeInTheDocument()
    expect(screen.getByText('Architectural Principles')).toBeInTheDocument()
    expect(screen.getByText('Security Boundaries')).toBeInTheDocument()
    expect(screen.getByText(/AI Proposes, Human Approves, Python Executes/i)).toBeInTheDocument()
    expect(screen.getByText(/Immutable Versioning/i)).toBeInTheDocument()
  })
})
