import React, { useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import {
  Database,
  Layers,
  Activity,
  AlertTriangle,
  PlayCircle,
  Wrench,
  ArrowRight,
} from 'lucide-react'
import { api } from '../services/api'
import type { OverviewStats } from '../types/analysis'
import { MetricCard } from '../components/MetricCard'
import { EmptyState } from '../components/EmptyState'
import { LoadingSpinner } from '../components/LoadingSpinner'

export const OverviewPage: React.FC = () => {
  const [stats, setStats] = useState<OverviewStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const context = useOutletContext<{ openUpload?: () => void }>()
  const openUpload = context?.openUpload

  useEffect(() => {
    let mounted = true
    const fetchStats = async () => {
      try {
        setIsLoading(true)
        const data = await api.getOverviewStats()
        if (mounted) setStats(data)
      } catch (err: unknown) {
        if (mounted) {
          const errObj = err as { message?: string }
          setError(errObj.message || 'Failed to load overview data.')
        }
      } finally {
        if (mounted) setIsLoading(false)
      }
    }
    fetchStats()
    return () => {
      mounted = false
    }
  }, [])

  if (isLoading) return <LoadingSpinner message="Loading system overview..." />

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--severity-critical-border)' }}>
        <div style={{ color: 'var(--severity-critical)', fontSize: '14px' }}>
          Unable to load overview statistics: {error}
        </div>
      </div>
    )
  }

  if (!stats || stats.total_datasets === 0) {
    return (
      <EmptyState
        title="No datasets ingested yet"
        description="Dataset Doctor ingests CSV, XLSX, JSON, and Parquet files into immutable Parquet versions for deterministic analysis."
        actionLabel="Upload First Dataset"
        onAction={openUpload}
      />
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Page Title */}
      <div>
        <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
          System Overview
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
          Real-time dataset health, deterministic analyses, and remediation telemetry.
        </p>
      </div>

      {/* High-Level Metrics Grid */}
      <div className="grid-cols-4">
        <MetricCard
          label="Total Datasets"
          value={stats.total_datasets}
          icon={<Database size={16} />}
          subtext="Managed repositories"
        />
        <MetricCard
          label="Immutable Versions"
          value={stats.total_versions}
          icon={<Layers size={16} />}
          subtext="Deterministic snapshots"
        />
        <MetricCard
          label="Running Analyses"
          value={stats.running_analyses_count}
          icon={<PlayCircle size={16} />}
          variant={stats.running_analyses_count > 0 ? 'warning' : 'default'}
          subtext="Active background runs"
        />
        <MetricCard
          label="Unresolved Critical"
          value={stats.unresolved_critical_issues_count}
          icon={<AlertTriangle size={16} />}
          variant={stats.unresolved_critical_issues_count > 0 ? 'danger' : 'default'}
          subtext={`+${stats.unresolved_high_issues_count} high issues`}
        />
      </div>

      {/* Secondary Row: Recent Activity */}
      <div className="grid-cols-2">
        {/* Recent Analyses Card */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Activity size={16} color="var(--accent-primary)" />
              <span className="card-title">Recent Analysis Runs</span>
            </div>
            <Link
              to="/analysis"
              style={{
                fontSize: '12px',
                color: 'var(--accent-primary)',
                textDecoration: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <span>View all</span>
              <ArrowRight size={12} />
            </Link>
          </div>

          {stats.latest_analyses && stats.latest_analyses.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {stats.latest_analyses.map((run) => (
                <Link
                  key={run.id}
                  to={`/analysis?runId=${run.id}`}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 12px',
                    backgroundColor: 'var(--bg-elevated)',
                    borderRadius: 'var(--radius-sm)',
                    textDecoration: 'none',
                    color: 'inherit',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span
                        className="badge font-mono"
                        style={{
                          backgroundColor:
                            run.status === 'COMPLETED'
                              ? 'var(--status-success-bg)'
                              : run.status === 'FAILED'
                              ? 'var(--severity-critical-bg)'
                              : 'var(--severity-medium-bg)',
                          color:
                            run.status === 'COMPLETED'
                              ? 'var(--status-success)'
                              : run.status === 'FAILED'
                              ? 'var(--severity-critical)'
                              : 'var(--severity-medium)',
                        }}
                      >
                        {run.status}
                      </span>
                      <span className="font-mono" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {new Date(run.created_at).toLocaleTimeString()}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                      {run.target_column ? `Target: ${run.target_column}` : 'Full dataset analysis'}
                    </div>
                  </div>

                  <div style={{ textAlign: 'right' }}>
                    <div className="font-mono" style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>
                      {run.ml_readiness_score !== null ? `${Math.round(run.ml_readiness_score!)}/100` : '—'}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {run.total_issues_count} findings ({run.critical_issues_count} crit)
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              No analyses executed yet.
            </div>
          )}
        </div>

        {/* Recent Remediations Card */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Wrench size={16} color="var(--accent-primary)" />
              <span className="card-title">Recent Remediations</span>
            </div>
            <Link
              to="/remediation"
              style={{
                fontSize: '12px',
                color: 'var(--accent-primary)',
                textDecoration: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <span>View all</span>
              <ArrowRight size={12} />
            </Link>
          </div>

          {stats.recent_remediations && stats.recent_remediations.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {stats.recent_remediations.map((rem: Record<string, unknown>, idx: number) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 12px',
                    backgroundColor: 'var(--bg-elevated)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <span className="badge badge-success font-mono">
                        {String(rem.status || 'COMPLETED')}
                      </span>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        By {String(rem.approved_by || 'reviewer')}
                      </span>
                    </div>
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                      {new Date(String(rem.created_at)).toLocaleString()}
                    </div>
                  </div>
                  <div className="font-mono" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    Execution ID: {String(rem.id || '').slice(0, 8)}...
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              No remediation pipelines executed yet.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
