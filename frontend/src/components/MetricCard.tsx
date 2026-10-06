import React from 'react'

interface MetricCardProps {
  label: string
  value: string | number
  delta?: number | string | null
  deltaLabel?: string
  subtext?: string
  icon?: React.ReactNode
  variant?: 'default' | 'success' | 'warning' | 'danger'
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  delta,
  deltaLabel,
  subtext,
  icon,
  variant = 'default',
}) => {
  let deltaColor = 'var(--text-secondary)'
  let deltaPrefix = ''

  if (typeof delta === 'number') {
    if (delta > 0) {
      deltaColor = 'var(--status-success)'
      deltaPrefix = '+'
    } else if (delta < 0) {
      deltaColor = 'var(--severity-critical)'
      deltaPrefix = ''
    }
  }

  let cardBorder = 'var(--border-subtle)'
  if (variant === 'danger') cardBorder = 'var(--severity-critical-border)'
  if (variant === 'warning') cardBorder = 'var(--severity-high-border)'
  if (variant === 'success') cardBorder = 'var(--status-success-border)'

  return (
    <div
      className="card"
      style={{
        borderColor: cardBorder,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
        <span
          style={{
            fontSize: '12px',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            color: 'var(--text-secondary)',
            fontWeight: 600,
          }}
        >
          {label}
        </span>
        {icon && (
          <span style={{ color: 'var(--text-muted)', display: 'flex' }}>
            {icon}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', margin: '4px 0' }}>
        <span
          className="font-mono"
          style={{
            fontSize: '24px',
            fontWeight: 700,
            color: 'var(--text-primary)',
            letterSpacing: '-0.02em',
          }}
        >
          {value}
        </span>

        {delta !== undefined && delta !== null && (
          <span
            className="font-mono"
            style={{
              fontSize: '12px',
              fontWeight: 600,
              color: deltaColor,
            }}
          >
            {deltaPrefix}{delta} {deltaLabel}
          </span>
        )}
      </div>

      {subtext && (
        <span
          style={{
            fontSize: '12px',
            color: 'var(--text-muted)',
            marginTop: '4px',
          }}
        >
          {subtext}
        </span>
      )}
    </div>
  )
}
