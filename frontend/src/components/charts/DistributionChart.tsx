import React, { useState } from 'react'
import type { DistributionVizItem } from '../../types/analysis'
import { PlotlyChart } from './PlotlyChart'

interface DistributionChartProps {
  distributions: DistributionVizItem[]
}

export const DistributionChart: React.FC<DistributionChartProps> = ({
  distributions,
}) => {
  const [selectedColIndex, setSelectedColIndex] = useState<number>(0)

  if (!distributions || distributions.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
        No numerical features available for distribution analysis.
      </div>
    )
  }

  const current = distributions[selectedColIndex] || distributions[0]

  const plotData = [
    {
      type: 'box' as const,
      name: current.column,
      q1: [current.q25],
      median: [current.median],
      q3: [current.q75],
      mean: [current.mean],
      boxmean: true as const,
      lowerfence: [current.min],
      upperfence: [current.max],
      marker: { color: '#3b82f6' },
      line: { color: '#38bdf8', width: 2 },
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      {/* Column selector */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Select Feature:</span>
          <select
            className="select-input font-mono"
            value={selectedColIndex}
            onChange={(e) => setSelectedColIndex(Number(e.target.value))}
          >
            {distributions.map((item, idx) => (
              <option key={item.column} value={idx}>
                {item.column}
              </option>
            ))}
          </select>
        </div>

        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Showing deterministic distribution metrics
        </span>
      </div>

      {/* Metrics breakdown pills */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
          gap: '8px',
          backgroundColor: 'var(--bg-elevated)',
          padding: '10px 14px',
          borderRadius: 'var(--radius-sm)',
        }}
      >
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Mean</div>
          <div className="font-mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {Number(current.mean).toFixed(2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Median</div>
          <div className="font-mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {Number(current.median).toFixed(2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Std Dev</div>
          <div className="font-mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {Number(current.std).toFixed(2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>IQR [Q1 - Q3]</div>
          <div className="font-mono" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            {Number(current.q25).toFixed(1)} - {Number(current.q75).toFixed(1)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Skewness</div>
          <div className="font-mono" style={{ fontSize: '13px', fontWeight: 600, color: Math.abs(current.skewness) > 1 ? 'var(--severity-high)' : 'var(--text-primary)' }}>
            {Number(current.skewness).toFixed(2)}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', textTransform: 'uppercase' }}>Kurtosis</div>
          <div className="font-mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {Number(current.kurtosis).toFixed(2)}
          </div>
        </div>
      </div>

      {/* Plotly Box Plot */}
      <div style={{ width: '100%', height: '220px' }}>
        <PlotlyChart
          data={plotData}
          layout={{
            margin: { l: 60, r: 30, t: 15, b: 35 },
            yaxis: {
              title: { text: current.column, font: { size: 11, color: '#949ca9' } },
            },
          }}
        />
      </div>
    </div>
  )
}
