import React from 'react'
import { Activity, AlertTriangle, ShieldCheck } from 'lucide-react'
import type { HeuristicBreakdown } from '../types/analysis'
import { SeverityBadge } from './SeverityBadge'

interface ReadinessCardProps {
  score?: number | null
  breakdown?: HeuristicBreakdown | null
  className?: string
}

export const ReadinessCard: React.FC<ReadinessCardProps> = ({
  score,
  breakdown,
  className = '',
}) => {
  const displayScore = score ?? breakdown?.heuristic_score ?? null
  const rating = breakdown?.rating ?? (displayScore !== null && displayScore >= 80 ? 'GOOD' : displayScore !== null && displayScore >= 60 ? 'FAIR' : 'POOR')

  let scoreColor = 'var(--text-secondary)'
  if (displayScore !== null) {
    if (displayScore >= 80) scoreColor = 'var(--status-success)'
    else if (displayScore >= 60) scoreColor = 'var(--severity-medium)'
    else scoreColor = 'var(--severity-critical)'
  }

  return (
    <div className={`card ${className}`} style={{ position: 'relative' }}>
      <div className="card-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={16} color="var(--accent-primary)" />
          <span className="card-title">ML Readiness Heuristic</span>
        </div>
        <span
          className="badge font-mono"
          style={{
            backgroundColor: 'var(--bg-elevated)',
            color: scoreColor,
            borderColor: 'var(--border-default)',
          }}
        >
          {rating.toUpperCase()}
        </span>
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', marginBottom: '16px' }}>
        <span
          className="font-mono"
          style={{
            fontSize: '42px',
            fontWeight: 800,
            color: scoreColor,
            letterSpacing: '-0.03em',
          }}
        >
          {displayScore !== null ? Math.round(displayScore) : '—'}
        </span>
        <span style={{ fontSize: '18px', color: 'var(--text-muted)', fontWeight: 500 }}>
          / 100
        </span>
      </div>

      {breakdown && breakdown.itemized_penalties && breakdown.itemized_penalties.length > 0 ? (
        <div style={{ marginTop: '12px', borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}>
          <span
            style={{
              fontSize: '11px',
              textTransform: 'uppercase',
              color: 'var(--text-secondary)',
              fontWeight: 600,
              letterSpacing: '0.05em',
              display: 'block',
              marginBottom: '8px',
            }}
          >
            Major Deductions ({breakdown.itemized_penalties.length})
          </span>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {breakdown.itemized_penalties.slice(0, 4).map((penalty, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '12px',
                  backgroundColor: 'var(--bg-elevated)',
                  padding: '6px 10px',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                  <SeverityBadge severity={penalty.severity} showIcon={false} />
                  <span
                    style={{
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      maxWidth: '280px',
                    }}
                    title={penalty.reason}
                  >
                    {penalty.column_name ? `${penalty.column_name}: ` : ''}
                    {penalty.reason}
                  </span>
                </div>
                <span className="font-mono" style={{ color: 'var(--severity-critical)', fontWeight: 600, flexShrink: 0 }}>
                  -{penalty.penalty} pts
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)', fontSize: '13px' }}>
          <ShieldCheck size={16} color="var(--status-success)" />
          <span>No critical heuristic penalties detected.</span>
        </div>
      )}

      <div
        style={{
          marginTop: '16px',
          paddingTop: '10px',
          borderTop: '1px solid var(--border-subtle)',
          fontSize: '11px',
          color: 'var(--text-muted)',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '6px',
          lineHeight: '1.4',
        }}
      >
        <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: '2px', color: 'var(--text-muted)' }} />
        <span>
          {breakdown?.disclaimer ||
            'The heuristic measures data quality/readiness signals, not actual model performance.'}
        </span>
      </div>
    </div>
  )
}
