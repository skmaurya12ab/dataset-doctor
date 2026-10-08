import '@testing-library/jest-dom'
import { vi } from 'vitest'
import React from 'react'

// Mock react-plotly.js for headless JSDOM environments
vi.mock('react-plotly.js', () => {
  return {
    default: (props: { data?: unknown; layout?: unknown }) => {
      return React.createElement('div', {
        'data-testid': 'plotly-mock',
        'data-plot-data': JSON.stringify(props.data || []),
        'data-plot-layout': JSON.stringify(props.layout || {}),
      })
    },
  }
})

vi.mock('react-plotly.js/factory', () => {
  return {
    default: () => (props: { data?: unknown; layout?: unknown }) => {
      return React.createElement('div', {
        'data-testid': 'plotly-mock',
        'data-plot-data': JSON.stringify(props.data || []),
        'data-plot-layout': JSON.stringify(props.layout || {}),
      })
    },
  }
})

vi.mock('plotly.js-dist-min', () => {
  return {
    default: {},
  }
})

// Mock window.URL.createObjectURL
if (typeof window !== 'undefined') {
  window.URL.createObjectURL = vi.fn(() => 'blob:mock-url')
}
