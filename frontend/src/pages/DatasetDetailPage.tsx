import React, { useEffect, useState, useCallback } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  Play,
  Upload,
  BarChart2,
  GitCompare,
  Wrench,
  ArrowRight,
} from 'lucide-react'
import { api } from '../services/api'
import type { Dataset } from '../types/dataset'
import type { AnalysisRun } from '../types/analysis'
import { MetricCard } from '../components/MetricCard'
import { VersionTimeline } from '../components/VersionTimeline'
import { UploadModal } from '../components/UploadModal'
import { LoadingSpinner } from '../components/LoadingSpinner'

export const DatasetDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [latestAnalysis, setLatestAnalysis] = useState<AnalysisRun | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Modals & Triggers
  const [isUploadNewVersionOpen, setIsUploadNewVersionOpen] = useState(false)
  const [isTriggerAnalysisOpen, setIsTriggerAnalysisOpen] = useState(false)
  const [targetColumn, setTargetColumn] = useState('')
  const [problemType, setProblemType] = useState('classification')
  const [isStartingAnalysis, setIsStartingAnalysis] = useState(false)

  const loadData = useCallback(async () => {
    if (!id) return
    try {
      setIsLoading(true)
      const ds = await api.getDataset(id)
      setDataset(ds)

      // Fetch latest analysis if versions exist
      if (ds.versions && ds.versions.length > 0) {
        const latestVer = ds.versions[ds.versions.length - 1]
        try {
          const runs = await api.listVersionAnalyses(id, latestVer.id)
          if (runs && runs.length > 0) {
            setLatestAnalysis(runs[0])
          }
        } catch {
          // If no analyses exist yet, that's fine
        }
      }
    } catch (err: unknown) {
      const errObj = err as { message?: string }
      setError(errObj.message || 'Failed to load dataset details.')
    } finally {
      setIsLoading(false)
    }
  }, [id])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleStartAnalysis = async () => {
    if (!dataset || dataset.versions.length === 0) return
    const latestVer = dataset.versions[dataset.versions.length - 1]

    try {
      setIsStartingAnalysis(true)
      const res = await api.triggerAnalysis(dataset.id, latestVer.id, {
        target_column: targetColumn.trim() || undefined,
        problem_type: targetColumn.trim() ? problemType : undefined,
      })
      setIsTriggerAnalysisOpen(false)
      // Navigate straight to analysis page with this run id
      navigate(`/analysis?runId=${res.analysis_run_id}`)
    } catch (err: unknown) {
      const errObj = err as { message?: string }
      alert(`Failed to trigger analysis: ${errObj.message}`)
    } finally {
      setIsStartingAnalysis(false)
    }
  }

  if (isLoading) return <LoadingSpinner message="Loading dataset..." />

  if (error || !dataset) {
    return (
      <div className="card" style={{ borderColor: 'var(--severity-critical-border)' }}>
        <div style={{ color: 'var(--severity-critical)' }}>
          {error || 'Dataset not found.'}
        </div>
      </div>
    )
  }

  const latestVersion = dataset.versions[dataset.versions.length - 1]
  const hasMultipleVersions = dataset.versions.length >= 2

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header Banner */}
      <div
        className="card"
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h1 style={{ fontSize: '22px', fontWeight: 700, color: 'var(--text-primary)' }}>
                {dataset.name}
              </h1>
              {latestVersion && (
                <span className="badge font-mono" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--accent-primary)' }}>
                  Latest: v{latestVersion.version_number}
                </span>
              )}
            </div>
            {dataset.description && (
              <p style={{ fontSize: '14px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                {dataset.description}
              </p>
            )}
            <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)' }}>
              <span>Created: {new Date(dataset.created_at).toLocaleDateString()}</span>
              <span>Updated: {new Date(dataset.updated_at).toLocaleDateString()}</span>
              <span className="font-mono">ID: {dataset.id.slice(0, 8)}...</span>
            </div>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => setIsUploadNewVersionOpen(true)}
            >
              <Upload size={14} />
              <span>Upload Version</span>
            </button>

            <button
              className="btn btn-primary btn-sm"
              onClick={() => setIsTriggerAnalysisOpen(true)}
            >
              <Play size={14} />
              <span>Run Analysis</span>
            </button>

            {latestAnalysis && (
              <Link
                to={`/analysis?runId=${latestAnalysis.id}`}
                className="btn btn-secondary btn-sm"
              >
                <BarChart2 size={14} />
                <span>View Findings</span>
              </Link>
            )}

            {hasMultipleVersions && (
              <Link
                to={`/versions?datasetId=${dataset.id}&v1=${dataset.versions[dataset.versions.length - 2].id}&v2=${latestVersion.id}`}
                className="btn btn-secondary btn-sm"
              >
                <GitCompare size={14} />
                <span>Compare Versions</span>
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Summary Metrics Grid */}
      {latestVersion && (
        <div className="grid-cols-4">
          <MetricCard
            label="Total Rows"
            value={latestVersion.row_count.toLocaleString()}
            subtext={`v${latestVersion.version_number} parquet storage`}
          />
          <MetricCard
            label="Total Columns"
            value={latestVersion.column_count}
            subtext="Tabular features"
          />
          <MetricCard
            label="ML Readiness"
            value={
              latestAnalysis?.ml_readiness_score !== null && latestAnalysis?.ml_readiness_score !== undefined
                ? `${Math.round(latestAnalysis.ml_readiness_score)}/100`
                : 'Not analyzed'
            }
            variant={
              latestAnalysis?.ml_readiness_score && latestAnalysis.ml_readiness_score >= 80
                ? 'success'
                : 'default'
            }
            subtext={latestAnalysis?.heuristic_breakdown?.rating || 'Run analysis to score'}
          />
          <MetricCard
            label="Issues Found"
            value={latestAnalysis ? latestAnalysis.total_issues_count : '—'}
            variant={latestAnalysis && latestAnalysis.critical_issues_count > 0 ? 'danger' : 'default'}
            subtext={
              latestAnalysis
                ? `${latestAnalysis.critical_issues_count} critical, ${latestAnalysis.status}`
                : 'Pending analysis run'
            }
          />
        </div>
      )}

      {/* Main Two-Column View: Latest Analysis & Version History */}
      <div className="grid-cols-2">
        {/* Latest Analysis Summary */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Latest Analysis Summary</span>
            {latestAnalysis && (
              <span
                className="badge font-mono"
                style={{
                  backgroundColor:
                    latestAnalysis.status === 'COMPLETED'
                      ? 'var(--status-success-bg)'
                      : 'var(--bg-elevated)',
                  color:
                    latestAnalysis.status === 'COMPLETED'
                      ? 'var(--status-success)'
                      : 'var(--text-secondary)',
                }}
              >
                {latestAnalysis.status}
              </span>
            )}
          </div>

          {latestAnalysis ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Completed:</span>
                <span className="font-mono">
                  {latestAnalysis.completed_at
                    ? new Date(latestAnalysis.completed_at).toLocaleString()
                    : 'Running...'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Target Column:</span>
                <span className="font-mono">
                  {latestAnalysis.target_column || '(None specified - Unsupervised)'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Problem Type:</span>
                <span className="font-mono">
                  {latestAnalysis.problem_type || 'General Tabular'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Deterministic Engine:</span>
                <span className="font-mono">v{latestAnalysis.engine_version}</span>
              </div>

              <div
                style={{
                  marginTop: '12px',
                  paddingTop: '12px',
                  borderTop: '1px solid var(--border-subtle)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <Link
                  to={`/analysis?runId=${latestAnalysis.id}`}
                  className="btn btn-secondary btn-sm"
                >
                  <span>Open Full Analysis</span>
                  <ArrowRight size={12} />
                </Link>

                <Link
                  to={`/remediation?runId=${latestAnalysis.id}`}
                  className="btn btn-primary btn-sm"
                >
                  <Wrench size={13} />
                  <span>Remediation Plan</span>
                </Link>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: '13px' }}>
              No analysis run has been executed on the latest version yet.
              <div style={{ marginTop: '12px' }}>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => setIsTriggerAnalysisOpen(true)}
                >
                  <Play size={13} />
                  <span>Execute Analysis</span>
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Version History Lineage */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Version History & Lineage</span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              {dataset.versions.length} immutable snapshots
            </span>
          </div>

          <VersionTimeline
            versions={dataset.versions}
            selectedVersionId={latestVersion?.id}
            onSelectVersion={(ver) => navigate(`/datasets/${dataset.id}/versions/${ver.id}`)}
            onCompareWithParent={(v1Id, v2Id) =>
              navigate(`/versions?datasetId=${dataset.id}&v1=${v1Id}&v2=${v2Id}`)
            }
          />
        </div>
      </div>

      {/* Upload New Version Modal */}
      {latestVersion && (
        <UploadModal
          isOpen={isUploadNewVersionOpen}
          onClose={() => setIsUploadNewVersionOpen(false)}
          onSuccess={() => loadData()}
          datasetId={dataset.id}
          parentVersionId={latestVersion.id}
        />
      )}

      {/* Trigger Analysis Modal */}
      {isTriggerAnalysisOpen && (
        <div className="modal-overlay" onClick={() => setIsTriggerAnalysisOpen(false)}>
          <div
            className="modal-dialog"
            style={{ maxWidth: '480px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-header">
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Trigger Dataset Analysis</h3>
            </div>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                Runs the 11 deterministic analysis modules on immutable version{' '}
                <strong>v{latestVersion?.version_number}</strong>.
              </p>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                  Target Column (Optional)
                </label>
                <input
                  type="text"
                  className="input-text"
                  style={{ width: '100%' }}
                  placeholder="e.g. churn, label, price"
                  value={targetColumn}
                  onChange={(e) => setTargetColumn(e.target.value)}
                />
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', display: 'block' }}>
                  Specifying a target enables class imbalance and target data leakage analyzers.
                </span>
              </div>

              {targetColumn.trim() && (
                <div>
                  <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
                    Problem Type
                  </label>
                  <select
                    className="select-input"
                    style={{ width: '100%' }}
                    value={problemType}
                    onChange={(e) => setProblemType(e.target.value)}
                  >
                    <option value="classification">Classification</option>
                    <option value="regression">Regression</option>
                  </select>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setIsTriggerAnalysisOpen(false)}
                disabled={isStartingAnalysis}
              >
                Cancel
              </button>
              <button
                className="btn btn-primary"
                onClick={handleStartAnalysis}
                disabled={isStartingAnalysis}
              >
                {isStartingAnalysis ? 'Submitting Run...' : 'Start Analysis'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
