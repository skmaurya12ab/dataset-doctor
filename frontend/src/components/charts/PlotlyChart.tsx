import React, { useMemo } from 'react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

export const Plot = createPlotlyComponent(Plotly)

export type Data = Plotly.Data
export type Layout = Plotly.Layout
export type Config = Plotly.Config

interface PlotlyChartProps {
  data: Plotly.Data[]
  layout?: Partial<Plotly.Layout>
  config?: Partial<Plotly.Config>
  style?: React.CSSProperties
  className?: string
}

export const PlotlyChart: React.FC<PlotlyChartProps> = ({
  data,
  layout = {},
  config = {},
  style = {},
  className = '',
}) => {
  const mergedLayout: Partial<Layout> = useMemo(() => {
    return {
      autosize: true,
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: {
        family: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        size: 11,
        color: '#949ca9',
      },
      margin: { l: 45, r: 25, t: 30, b: 40 },
      hoverlabel: {
        bgcolor: '#1e222c',
        bordercolor: '#2a303d',
        font: { color: '#f1f3f7', size: 12 },
      },
      xaxis: {
        gridcolor: '#20242e',
        zerolinecolor: '#2a303d',
        tickcolor: '#20242e',
        ...layout.xaxis,
      },
      yaxis: {
        gridcolor: '#20242e',
        zerolinecolor: '#2a303d',
        tickcolor: '#20242e',
        ...layout.yaxis,
      },
      ...layout,
    }
  }, [layout])

  const mergedConfig: Partial<Config> = useMemo(() => {
    return {
      responsive: true,
      displayModeBar: false,
      ...config,
    }
  }, [config])

  return (
    <div style={{ width: '100%', height: '100%', minHeight: '260px', ...style }} className={className}>
      <Plot
        data={data}
        layout={mergedLayout as Layout}
        config={mergedConfig as Config}
        useResizeHandler
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  )
}
