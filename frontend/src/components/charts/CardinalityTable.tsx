import React from 'react'
import type { CardinalityVizItem } from '../../types/analysis'
import { SeverityBadge } from '../SeverityBadge'

interface CardinalityTableProps {
  items: CardinalityVizItem[]
}

export const CardinalityTable: React.FC<CardinalityTableProps> = ({ items }) => {
  if (!items || items.length === 0) {
    return (
      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
        No cardinality data available.
      </div>
    )
  }

  return (
    <div className="table-container">
      <table className="data-table">
        <thead>
          <tr>
            <th>Column</th>
            <th style={{ width: '120px' }}>Unique Count</th>
            <th style={{ width: '120px' }}>Unique Ratio</th>
            <th style={{ width: '160px' }}>Classification</th>
            <th style={{ width: '110px' }}>Severity</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.column}>
              <td>
                <span
                  className="font-mono"
                  style={{
                    fontSize: '12px',
                    backgroundColor: 'var(--bg-elevated)',
                    padding: '2px 6px',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--text-primary)',
                  }}
                >
                  {item.column}
                </span>
              </td>
              <td>
                <span className="font-mono">{item.unique_count.toLocaleString()}</span>
              </td>
              <td>
                <span className="font-mono">{(item.unique_ratio * 100).toFixed(1)}%</span>
              </td>
              <td>
                <span
                  className="badge font-mono"
                  style={{
                    backgroundColor: 'var(--bg-elevated)',
                    color:
                      item.classification.includes('CONSTANT') || item.classification.includes('IDENTIFIER')
                        ? 'var(--severity-high)'
                        : 'var(--text-secondary)',
                  }}
                >
                  {item.classification}
                </span>
              </td>
              <td>
                <SeverityBadge severity={item.severity} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
