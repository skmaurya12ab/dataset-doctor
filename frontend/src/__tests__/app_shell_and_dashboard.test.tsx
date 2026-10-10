import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { Sidebar } from '../components/Sidebar'
import { Header } from '../components/Header'
import { OverviewPage } from '../pages/OverviewPage'
import { SettingsPage } from '../pages/SettingsPage'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { App } from '../App'
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
    vi.mocked(api.getCurrentUser).mockResolvedValue({
      id: '00000000-0000-0000-0000-000000000001',
      email: 'testuser@example.com',
      is_active: true,
      is_verified: true,
      role: 'user',
      created_at: new Date().toISOString(),
    })
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

describe('ErrorBoundary & Route Consistency', () => {
  beforeEach(() => {
    vi.mocked(api.getCurrentUser).mockResolvedValue({
      id: '00000000-0000-0000-0000-000000000001',
      email: 'testuser@example.com',
      is_active: true,
      is_verified: true,
      role: 'user',
      created_at: new Date().toISOString(),
    })
  })
  it('catches uncaught child rendering exceptions and displays error card rather than blank screen', () => {
    // Suppress React boundary console.error during test
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const CrashingChild = () => {
      throw new Error('Test crash in child component')
    }

    render(
      <ErrorBoundary>
        <CrashingChild />
      </ErrorBoundary>,
    )

    expect(
      screen.getByText('Something went wrong while rendering this page'),
    ).toBeInTheDocument()
    expect(screen.getByText(/Test crash in child component/i)).toBeInTheDocument()
    expect(screen.getByText(/Reload Page/i)).toBeInTheDocument()

    consoleErrorSpy.mockRestore()
  })

  it('redirects from /remediations to /remediation preserving query parameters', async () => {
    vi.mocked(api.getOverviewStats).mockResolvedValue({
      total_datasets: 0,
      total_versions: 0,
      running_analyses_count: 0,
      latest_analyses: [],
      recent_remediations: [],
      unresolved_critical_issues_count: 0,
      unresolved_high_issues_count: 0,
      average_readiness_score: null,
    })

    window.history.pushState({}, '', '/remediations?runId=test-run-123')

    render(<App />)

    await waitFor(() => {
      expect(window.location.pathname).toBe('/remediation')
      expect(window.location.search).toBe('?runId=test-run-123')
    })
  })

  it('navigates to Remediation page via sidebar link and renders without blank screen', async () => {
    vi.mocked(api.getOverviewStats).mockResolvedValue({
      total_datasets: 0,
      total_versions: 0,
      running_analyses_count: 0,
      latest_analyses: [],
      recent_remediations: [],
      unresolved_critical_issues_count: 0,
      unresolved_high_issues_count: 0,
      average_readiness_score: null,
    })

    window.history.pushState({}, '', '/')

    render(<App />)

    await waitFor(() => {
      expect(screen.getByText('Dataset Doctor')).toBeInTheDocument()
    })

    const remediationNav = screen.getByRole('link', { name: /Remediation/i })
    fireEvent.click(remediationNav)

    await waitFor(() => {
      expect(window.location.pathname).toBe('/remediation')
      expect(screen.getByText('Dataset Doctor')).toBeInTheDocument()
      expect(screen.getByText('No Analysis Run Selected')).toBeInTheDocument()
    })
  })
})
