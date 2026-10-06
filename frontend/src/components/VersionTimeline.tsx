import React from 'react'
import { GitCommit, ExternalLink } from 'lucide-react'
import type { DatasetVersion } from '../types/dataset'

interface VersionTimelineProps {
  versions: DatasetVersion[]
  selectedVersionId?: string
  onSelectVersion?: (version: DatasetVersion) => void
  onCompareWithParent?: (v1Id: string, v2Id: string) => void
}

export const VersionTimeline: React.FC<VersionTimelineProps> = ({
  versions,
  selectedVersionId,
  onSelectVersion,
  onCompareWithParent,
}) => {
  // Sort versions ascending by version_number for timeline
  const sorted = [...versions].sort((a, b) => a.version_number - b.version_number)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0px' }}>
      {sorted.map((version, idx) => {
        const isSelected = version.id === selectedVersionId
        const hasParent = Boolean(version.parent_version_id)
        const parentVersion = hasParent
          ? versions.find((v) => v.id === version.parent_version_id)
          : null

        return (
          <React.Fragment key={version.id}>
            {idx > 0 && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  paddingLeft: '19px',
                  height: '36px',
                  color: 'var(--text-muted)',
                }}
              >
                <div
                  style={{
                    width: '2px',
                    height: '100%',
                    backgroundColor: 'var(--border-default)',
                  }}
                />
                <span
                  style={{
                    fontSize: '11px',
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-muted)',
                    marginLeft: '8px',
                  }}
                >
                  {version.change_summary || 'Deterministic remediation pipeline'}
                </span>
              </div>
            )}

            <div
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '12px',
                padding: '12px',
                backgroundColor: isSelected ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                border: `1px solid ${isSelected ? 'var(--accent-primary)' : 'var(--border-subtle)'}`,
                borderRadius: 'var(--radius-md)',
                cursor: onSelectVersion ? 'pointer' : 'default',
                transition: 'all 0.15s ease',
              }}
              onClick={() => onSelectVersion && onSelectVersion(version)}
            >
              <div
                style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  backgroundColor: isSelected ? 'var(--accent-subtle)' : 'var(--bg-elevated)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: isSelected ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  flexShrink: 0,
                }}
              >
                <GitCommit size={16} />
              </div>

              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span
                      className="font-mono"
                      style={{
                        fontWeight: 700,
                        fontSize: '13px',
                        color: 'var(--text-primary)',
                      }}
                    >
                      v{version.version_number}
                    </span>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {new Date(version.created_at).toLocaleString()}
                    </span>
                  </div>

                  {parentVersion && onCompareWithParent && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={(e) => {
                        e.stopPropagation()
                        onCompareWithParent(parentVersion.id, version.id)
                      }}
                      title={`Compare v${parentVersion.version_number} with v${version.version_number}`}
                    >
                      <ExternalLink size={12} />
                      <span>Compare with v{parentVersion.version_number}</span>
                    </button>
                  )}
                </div>

                <div
                  style={{
                    display: 'flex',
                    gap: '16px',
                    marginTop: '6px',
                    fontSize: '12px',
                    color: 'var(--text-secondary)',
                  }}
                >
                  <span className="font-mono">
                    <strong>{version.row_count.toLocaleString()}</strong> rows
                  </span>
                  <span className="font-mono">
                    <strong>{version.column_count}</strong> cols
                  </span>
                  <span className="font-mono">
                    {(version.file_size_bytes / 1024).toFixed(1)} KB
                  </span>
                  <span
                    className="font-mono"
                    style={{
                      color: 'var(--text-muted)',
                      maxWidth: '180px',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={version.sha256_hash}
                  >
                    sha256:{version.sha256_hash.slice(0, 10)}...
                  </span>
                </div>
              </div>
            </div>
          </React.Fragment>
        )
      })}
    </div>
  )
}
