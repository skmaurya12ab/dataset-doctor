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
      colorway: ['#f5f5f5', '#d4d4d4', '#a3a3a3', '#737373', '#525252'],
      font: {
        family: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
        size: 11,
        color: '#a3a3a3',
      },
      margin: { l: 45, r: 25, t: 30, b: 40 },
      hoverlabel: {
        bgcolor: '#202020',
        bordercolor: '#353535',
        font: { color: '#f5f5f5', size: 12 },
      },
      xaxis: {
        gridcolor: '#262626',
        zerolinecolor: '#353535',
        tickcolor: '#262626',
        ...layout.xaxis,
      },
      yaxis: {
        gridcolor: '#262626',
        zerolinecolor: '#353535',
        tickcolor: '#262626',
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
