import React, { useState, useMemo } from 'react'
import { Sparkles, Search, Filter } from 'lucide-react'
import type { QualityIssue } from '../types/analysis'
import { SeverityBadge } from './SeverityBadge'

interface IssueTableProps {
  issues: QualityIssue[]
  onExplainIssue?: (issue: QualityIssue) => void
}

const SEVERITY_ORDER: Record<string, number> = {
  CRITICAL: 5,
  HIGH: 4,
  MEDIUM: 3,
  LOW: 2,
  INFO: 1,
}

export const IssueTable: React.FC<IssueTableProps> = ({
  issues,
  onExplainIssue,
}) => {
  const [selectedModule, setSelectedModule] = useState<string>('ALL')
  const [selectedSeverity, setSelectedSeverity] = useState<string>('ALL')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Unique modules present in the issue set
  const modules = useMemo(() => {
    const set = new Set<string>()
    issues.forEach((i) => set.add(i.module))
    return Array.from(set).sort()
  }, [issues])

  // Filter & sort
  const filteredIssues = useMemo(() => {
    return issues
      .filter((issue) => {
        if (selectedModule !== 'ALL' && issue.module !== selectedModule) return false
        if (selectedSeverity !== 'ALL' && issue.severity !== selectedSeverity) return false
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase()
          const matchTitle = issue.title.toLowerCase().includes(q)
          const matchCol = issue.column_name?.toLowerCase().includes(q) ?? false
          const matchDesc = issue.description.toLowerCase().includes(q)
          if (!matchTitle && !matchCol && !matchDesc) return false
        }
        return true
      })
      .sort((a, b) => {
        const orderA = SEVERITY_ORDER[a.severity] || 0
        const orderB = SEVERITY_ORDER[b.severity] || 0
        return orderB - orderA // Highest severity first
      })
  }, [issues, selectedModule, selectedSeverity, searchQuery])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Filters bar */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', gap: '12px', flex: 1, minWidth: '260px' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <Search
              size={14}
              style={{
                position: 'absolute',
                left: '10px',
                top: '50%',
                transform: 'translateY(-50%)',
                color: 'var(--text-muted)',
              }}
            />
            <input
              type="text"
              className="input-text"
              placeholder="Search issues by title, column, or description..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ paddingLeft: '32px', width: '100%' }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Filter size={14} color="var(--text-muted)" />
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Module:</span>
          </div>
          <select
            className="select-input"
            value={selectedModule}
            onChange={(e) => setSelectedModule(e.target.value)}
          >
            <option value="ALL">All Modules ({issues.length})</option>
            {modules.map((mod) => (
              <option key={mod} value={mod}>
                {mod.replace(/_/g, ' ').toUpperCase()}
              </option>
            ))}
          </select>

          <select
            className="select-input"
            value={selectedSeverity}
            onChange={(e) => setSelectedSeverity(e.target.value)}
          >
            <option value="ALL">All Severities</option>
            <option value="CRITICAL">CRITICAL</option>
            <option value="HIGH">HIGH</option>
            <option value="MEDIUM">MEDIUM</option>
            <option value="LOW">LOW</option>
            <option value="INFO">INFO</option>
          </select>
        </div>
      </div>

      {/* Issues Table */}
      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: '110px' }}>Severity</th>
              <th style={{ width: '130px' }}>Module</th>
              <th style={{ width: '150px' }}>Column</th>
              <th>Finding Title & Description</th>
              <th style={{ width: '140px', textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredIssues.length === 0 ? (
              <tr>
                <td colSpan={5} style={{ textAlign: 'center', padding: '32px', color: 'var(--text-muted)' }}>
                  No deterministic quality issues matching filters.
                </td>
              </tr>
            ) : (
              filteredIssues.map((issue) => (
                <tr key={issue.id}>
                  <td>
                    <SeverityBadge severity={issue.severity} />
                  </td>
                  <td>
                    <span
                      className="font-mono"
                      style={{ fontSize: '12px', color: 'var(--text-secondary)' }}
                    >
                      {issue.module.replace(/_analyzer$/, '')}
                    </span>
                  </td>
                  <td>
                    {issue.column_name ? (
                      <span
                        className="font-mono"
                        style={{
                          fontSize: '12px',
                          color: 'var(--text-primary)',
                          backgroundColor: 'var(--bg-elevated)',
                          padding: '2px 6px',
                          borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        {issue.column_name}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                        (Dataset-level)
                      </span>
                    )}
                  </td>
                  <td>
                    <div>
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '2px' }}>
                        {issue.title}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {issue.description}
                      </div>
                      {issue.remediation_hint && (
                        <div
                          style={{
                            fontSize: '11px',
                            color: 'var(--text-muted)',
                            marginTop: '4px',
                            fontStyle: 'italic',
                          }}
                        >
                          Hint: {issue.remediation_hint}
                        </div>
                      )}
                    </div>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    {onExplainIssue && (
                      <button
                        className="btn btn-secondary btn-sm"
                        onClick={() => onExplainIssue(issue)}
                        title="Generate grounded AI explanation"
                      >
                        <Sparkles size={13} color="var(--accent-primary)" />
                        <span>Explain</span>
                      </button>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'flex', justifyContent: 'space-between' }}>
        <span>Showing {filteredIssues.length} of {issues.length} deterministic findings</span>
        <span>Findings source: Deterministic Python Engine</span>
      </div>
    </div>
  )
}
