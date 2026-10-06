import React, { useState } from 'react'
import {
  ArrowRight,
  CheckCircle,
  RefreshCw,
  PlusCircle,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react'
import type { VersionComparison } from '../types/remediation'
import { MetricCard } from './MetricCard'
import { SeverityBadge } from './SeverityBadge'

interface VersionComparisonViewProps {
  comparison: VersionComparison
}

export const VersionComparisonView: React.FC<VersionComparisonViewProps> = ({
  comparison,
}) => {
  const [filterStatus, setFilterStatus] = useState<string>('ALL')

  const { before, after, dataset_metrics, quality, heuristic } = comparison
  const summary = quality.summary

  const filteredIssues = quality.issues.filter((item) => {
    if (filterStatus === 'ALL') return true
    return item.status === filterStatus
  })

  // Heuristic color
  const heuristicDelta = heuristic.delta ?? 0
  const isPositiveImprovement = heuristicDelta > 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header Banner */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '16px 20px',
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              className="badge font-mono"
              style={{
                backgroundColor: 'var(--bg-elevated)',
                color: 'var(--text-secondary)',
                fontSize: '13px',
                padding: '4px 10px',
              }}
            >
              VERSION {before.version_number}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>(Source)</span>
          </div>

          <ArrowRight size={20} color="var(--accent-primary)" />

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              className="badge font-mono"
              style={{
                backgroundColor: 'var(--accent-subtle)',
                color: 'var(--accent-primary)',
                fontSize: '13px',
                padding: '4px 10px',
              }}
            >
              VERSION {after.version_number}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--status-success)' }}>(Remediated)</span>
          </div>
        </div>

        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          Deterministic before/after audit report
        </div>
      </div>

      {/* Readiness Heuristic Delta Highlight */}
      <div
        className="card"
        style={{
          borderColor: isPositiveImprovement ? 'var(--status-success-border)' : 'var(--border-default)',
        }}
      >
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TrendingUp size={16} color="var(--accent-primary)" />
            <span className="card-title">ML Readiness Heuristic Impact</span>
          </div>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Comparative Deterministic Heuristic
          </span>
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-around',
            padding: '12px 0',
            flexWrap: 'wrap',
            gap: '16px',
          }}
        >
          {/* Before Score */}
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
              BEFORE (v{before.version_number})
            </div>
            <div className="font-mono" style={{ fontSize: '32px', fontWeight: 700, color: 'var(--text-secondary)' }}>
              {heuristic.before_score !== null ? Math.round(heuristic.before_score!) : '—'}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 600 }}>
              {heuristic.before_rating || 'UNRATED'}
            </div>
          </div>

          {/* Delta Arrow */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
            <div
              className="font-mono"
              style={{
                fontSize: '22px',
                fontWeight: 800,
                color: isPositiveImprovement ? 'var(--status-success)' : 'var(--severity-critical)',
              }}
            >
              {heuristicDelta > 0 ? `+${heuristicDelta}` : heuristicDelta}
            </div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Score Delta</span>
          </div>

          {/* After Score */}
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '12px', color: 'var(--accent-primary)', marginBottom: '4px' }}>
              AFTER (v{after.version_number})
            </div>
            <div
              className="font-mono"
              style={{
                fontSize: '32px',
                fontWeight: 700,
                color: isPositiveImprovement ? 'var(--status-success)' : 'var(--text-primary)',
              }}
            >
              {heuristic.after_score !== null ? Math.round(heuristic.after_score!) : '—'}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--status-success)', fontWeight: 600 }}>
              {heuristic.after_rating || 'UNRATED'}
            </div>
          </div>
        </div>

        <div
          style={{
            marginTop: '12px',
            paddingTop: '10px',
            borderTop: '1px solid var(--border-subtle)',
            fontSize: '11px',
            color: 'var(--text-muted)',
            lineHeight: 1.4,
          }}
        >
          {heuristic.note}
        </div>
      </div>

      {/* Dataset Summary Metrics Deltas Grid */}
      <div className="grid-cols-4">
        <MetricCard
          label="Total Rows"
          value={dataset_metrics.row_count?.after?.toLocaleString() ?? '—'}
          delta={dataset_metrics.row_count?.delta}
          deltaLabel="rows"
          subtext={`Before: ${dataset_metrics.row_count?.before?.toLocaleString() ?? '—'}`}
        />
        <MetricCard
          label="Columns"
          value={dataset_metrics.column_count?.after ?? '—'}
          delta={dataset_metrics.column_count?.delta}
          deltaLabel="cols"
          subtext={`Before: ${dataset_metrics.column_count?.before ?? '—'}`}
        />
        <MetricCard
          label="Missing Values"
          value={`${dataset_metrics.missing_percentage?.after ?? 0}%`}
          delta={dataset_metrics.missing_percentage?.delta}
          deltaLabel="%"
          subtext={`Before: ${dataset_metrics.missing_percentage?.before ?? 0}%`}
        />
        <MetricCard
          label="Duplicate Rows"
          value={dataset_metrics.duplicate_rows?.after ?? '—'}
          delta={dataset_metrics.duplicate_rows?.delta}
          deltaLabel="rows"
          subtext={`Before: ${dataset_metrics.duplicate_rows?.before ?? '—'}`}
        />
      </div>

      {/* Issue Lifecycle Breakdown */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Defect Lifecycle Evolution</span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Matched deterministically across versions
          </span>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
            gap: '12px',
            marginBottom: '16px',
          }}
        >
          <div
            style={{
              padding: '12px',
              backgroundColor: 'var(--status-success-bg)',
              border: '1px solid var(--status-success-border)',
              borderRadius: 'var(--radius-sm)',
              textAlign: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
              <CheckCircle size={14} color="var(--status-success)" />
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--status-success)' }}>RESOLVED</span>
            </div>
            <div className="font-mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--status-success)', marginTop: '4px' }}>
              {summary.resolved_count}
            </div>
          </div>

          <div
            style={{
              padding: '12px',
              backgroundColor: 'var(--severity-low-bg)',
              border: '1px solid var(--severity-low-border)',
              borderRadius: 'var(--radius-sm)',
              textAlign: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
              <RefreshCw size={14} color="var(--severity-low)" />
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--severity-low)' }}>CHANGED</span>
            </div>
            <div className="font-mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--severity-low)', marginTop: '4px' }}>
              {summary.changed_count}
            </div>
          </div>

          <div
            style={{
              padding: '12px',
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-sm)',
              textAlign: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
              <ShieldCheck size={14} color="var(--text-secondary)" />
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>UNCHANGED</span>
            </div>
            <div className="font-mono" style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-secondary)', marginTop: '4px' }}>
              {summary.unchanged_count}
            </div>
          </div>

          <div
            style={{
              padding: '12px',
              backgroundColor: summary.new_count > 0 ? 'var(--severity-critical-bg)' : 'var(--bg-elevated)',
              border: `1px solid ${summary.new_count > 0 ? 'var(--severity-critical-border)' : 'var(--border-default)'}`,
              borderRadius: 'var(--radius-sm)',
              textAlign: 'center',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px' }}>
              <PlusCircle size={14} color={summary.new_count > 0 ? 'var(--severity-critical)' : 'var(--text-muted)'} />
              <span style={{ fontSize: '12px', fontWeight: 600, color: summary.new_count > 0 ? 'var(--severity-critical)' : 'var(--text-muted)' }}>
                NEW
              </span>
            </div>
            <div
              className="font-mono"
              style={{
                fontSize: '24px',
                fontWeight: 700,
                color: summary.new_count > 0 ? 'var(--severity-critical)' : 'var(--text-muted)',
                marginTop: '4px',
              }}
            >
              {summary.new_count}
            </div>
          </div>
        </div>

        {/* Filter Pills */}
        <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Filter issues:</span>
          {['ALL', 'RESOLVED', 'CHANGED', 'UNCHANGED', 'NEW'].map((status) => (
            <button
              key={status}
              className={`btn btn-sm ${filterStatus === status ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setFilterStatus(status)}
            >
              {status}
            </button>
          ))}
        </div>

        {/* Issues List */}
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '120px' }}>Status</th>
                <th style={{ width: '140px' }}>Module</th>
                <th style={{ width: '140px' }}>Column</th>
                <th style={{ width: '130px' }}>Severity Shift</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {filteredIssues.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>
                    No issues matching filter '{filterStatus}'.
                  </td>
                </tr>
              ) : (
                filteredIssues.map((item, idx) => (
                  <tr key={idx}>
                    <td>
                      <span
                        className="badge font-mono"
                        style={{
                          backgroundColor:
                            item.status === 'RESOLVED'
                              ? 'var(--status-success-bg)'
                              : item.status === 'NEW'
                              ? 'var(--severity-critical-bg)'
                              : 'var(--bg-elevated)',
                          color:
                            item.status === 'RESOLVED'
                              ? 'var(--status-success)'
                              : item.status === 'NEW'
                              ? 'var(--severity-critical)'
                              : 'var(--text-secondary)',
                          borderColor:
                            item.status === 'RESOLVED'
                              ? 'var(--status-success-border)'
                              : item.status === 'NEW'
                              ? 'var(--severity-critical-border)'
                              : 'var(--border-default)',
                        }}
                      >
                        {item.status}
                      </span>
                    </td>
                    <td>
                      <span className="font-mono" style={{ fontSize: '12px' }}>
                        {item.module.replace(/_analyzer$/, '')}
                      </span>
                    </td>
                    <td>
                      {item.column ? (
                        <span
                          className="font-mono"
                          style={{
                            fontSize: '12px',
                            backgroundColor: 'var(--bg-elevated)',
                            padding: '2px 6px',
                            borderRadius: 'var(--radius-sm)',
                          }}
                        >
                          {item.column}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>—</span>
                      )}
                    </td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {item.before_severity && <SeverityBadge severity={item.before_severity} showIcon={false} />}
                        {item.before_severity && item.after_severity && <ArrowRight size={12} color="var(--text-muted)" />}
                        {item.after_severity && <SeverityBadge severity={item.after_severity} showIcon={false} />}
                      </div>
                    </td>
                    <td>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {item.details?.note ? String(item.details.note) : item.category}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
