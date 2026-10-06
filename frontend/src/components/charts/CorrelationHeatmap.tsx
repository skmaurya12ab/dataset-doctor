import React, { useState } from 'react'
import type { CorrelationVizData } from '../../types/analysis'
import { PlotlyChart } from './PlotlyChart'

interface CorrelationHeatmapProps {
  correlations: CorrelationVizData
}

export const CorrelationHeatmap: React.FC<CorrelationHeatmapProps> = ({
  correlations,
}) => {
  const [method, setMethod] = useState<'pearson' | 'spearman'>('pearson')

  if (!correlations || !correlations.columns || correlations.columns.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
        Insufficient numerical features to compute pairwise correlation.
      </div>
    )
  }

  const { columns, pearson_matrix, spearman_matrix, high_correlation_pairs } = correlations
  const matrix = method === 'pearson' ? pearson_matrix : spearman_matrix

  const plotData = [
    {
      type: 'heatmap' as const,
      z: matrix,
      x: columns,
      y: columns,
      colorscale: [
        [0.0, '#3b82f6'],
        [0.5, '#15181f'],
        [1.0, '#f43f5e'],
      ] as [number, string][],
      zmin: -1.0,
      zmax: 1.0,
      hoverongaps: false,
      colorbar: {
        title: { text: 'Corr', font: { size: 10, color: '#949ca9' } },
        tickfont: { color: '#949ca9', size: 10 },
        thickness: 12,
        len: 0.8,
      },
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Method:</span>
          <button
            className={`btn btn-sm ${method === 'pearson' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setMethod('pearson')}
          >
            Pearson (Linear)
          </button>
          <button
            className={`btn btn-sm ${method === 'spearman' ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setMethod('spearman')}
          >
            Spearman (Rank)
          </button>
        </div>

        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          {columns.length} × {columns.length} feature matrix
        </span>
      </div>

      <div style={{ width: '100%', height: Math.max(300, columns.length * 32 + 80) }}>
        <PlotlyChart
          data={plotData}
          layout={{
            margin: { l: 80, r: 40, t: 20, b: 80 },
            xaxis: {
              tickangle: -45,
              automargin: true,
            },
            yaxis: {
              automargin: true,
            },
          }}
        />
      </div>

      {high_correlation_pairs && high_correlation_pairs.length > 0 && (
        <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '10px' }}>
          <span
            style={{
              fontSize: '11px',
              textTransform: 'uppercase',
              color: 'var(--text-secondary)',
              fontWeight: 600,
              display: 'block',
              marginBottom: '6px',
            }}
          >
            High Correlation Alerts (|r| &gt; 0.85)
          </span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {high_correlation_pairs.slice(0, 5).map((pair, idx) => (
              <span
                key={idx}
                className="badge font-mono"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--severity-high)',
                  borderColor: 'var(--severity-high-border)',
                }}
              >
                {pair.col1} ↔ {pair.col2} (r = {Number(pair.pearson).toFixed(2)})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
