import React from 'react'
import type { MissingValueVizItem } from '../../types/analysis'
import { PlotlyChart } from './PlotlyChart'

interface MissingnessChartProps {
  items: MissingValueVizItem[]
}

const SEVERITY_COLOR_MAP: Record<string, string> = {
  CRITICAL: '#f43f5e',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#38bdf8',
  INFO: '#94a3b8',
}

export const MissingnessChart: React.FC<MissingnessChartProps> = ({ items }) => {
  if (!items || items.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
        No missing values detected across dataset columns.
      </div>
    )
  }

  // Sort descending by missing_percentage, take top 15 for readability
  // For Plotly horizontal bar chart, reverse array so highest is on top
  const sorted = [...items]
    .sort((a, b) => b.missing_percentage - a.missing_percentage)
    .slice(0, 15)
    .reverse()

  const yCols = sorted.map((item) => item.column)
  const xVals = sorted.map((item) => item.missing_percentage)
  const colors = sorted.map(
    (item) => SEVERITY_COLOR_MAP[item.severity] || '#38bdf8',
  )
  const hoverText = sorted.map(
    (item) =>
      `Column: ${item.column}<br>Missing: ${item.missing_percentage}% (${item.missing_count} rows)<br>Severity: ${item.severity}`,
  )

  const plotData = [
    {
      type: 'bar' as const,
      orientation: 'h' as const,
      x: xVals,
      y: yCols,
      text: xVals.map((v) => `${v}%`),
      textposition: 'outside' as const,
      hoverinfo: 'text' as const,
      hovertext: hoverText,
      marker: {
        color: colors,
        line: { width: 0 },
      },
    },
  ]

  return (
    <div style={{ width: '100%', height: Math.max(260, sorted.length * 28 + 60) }}>
      <PlotlyChart
        data={plotData}
        layout={{
          margin: { l: 120, r: 40, t: 10, b: 35 },
          xaxis: {
            title: { text: 'Missing Percentage (%)', font: { size: 11, color: '#949ca9' } },
            range: [0, Math.max(100, Math.max(...xVals) * 1.15)],
            ticksuffix: '%',
          },
          yaxis: {
            automargin: true,
          },
        }}
      />
    </div>
  )
}
