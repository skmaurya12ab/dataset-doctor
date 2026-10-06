import React from 'react'
import type { ClassImbalanceVizData } from '../../types/analysis'
import { SeverityBadge } from '../SeverityBadge'
import { PlotlyChart } from './PlotlyChart'

interface ClassDistributionChartProps {
  data: ClassImbalanceVizData | null | undefined
}

export const ClassDistributionChart: React.FC<ClassDistributionChartProps> = ({
  data,
}) => {
  if (!data || !data.classes || data.classes.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
        No target classification analysis specified or detected.
      </div>
    )
  }

  const { target_column, classes, imbalance_ratio, severity } = data

  const xLabels = classes.map((c) => String(c.class_name))
  const yCounts = classes.map((c) => c.count)
  const hoverText = classes.map(
    (c) => `Class: ${c.class_name}<br>Count: ${c.count}<br>Share: ${c.percentage}%`,
  )

  const plotData = [
    {
      type: 'bar' as const,
      x: xLabels,
      y: yCounts,
      text: classes.map((c) => `${c.percentage}%`),
      textposition: 'auto' as const,
      hoverinfo: 'text' as const,
      hovertext: hoverText,
      marker: {
        color: '#3b82f6',
      },
    },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Target Column:</span>
          <span className="font-mono" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
            {target_column}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="font-mono" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Ratio: {imbalance_ratio}:1
          </span>
          <SeverityBadge severity={severity} />
        </div>
      </div>

      <div style={{ width: '100%', height: '220px' }}>
        <PlotlyChart
          data={plotData}
          layout={{
            margin: { l: 50, r: 20, t: 10, b: 40 },
            xaxis: {
              title: { text: 'Class Labels', font: { size: 11, color: '#949ca9' } },
            },
            yaxis: {
              title: { text: 'Sample Count', font: { size: 11, color: '#949ca9' } },
            },
          }}
        />
      </div>
    </div>
  )
}
