import React, { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  FileCode,
  Eye,
} from 'lucide-react'
import { api } from '../services/api'
import type {
  DatasetVersion,
  DatasetPreviewResponse,
  ColumnSchemaItem,
} from '../types/dataset'
import { MetricCard } from '../components/MetricCard'
import { LoadingSpinner } from '../components/LoadingSpinner'

export const VersionDetailPage: React.FC = () => {
  const { datasetId, versionId } = useParams<{ datasetId: string; versionId: string }>()

  const [version, setVersion] = useState<DatasetVersion | null>(null)
  const [preview, setPreview] = useState<DatasetPreviewResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true
    const load = async () => {
      if (!datasetId || !versionId) return
      try {
        setIsLoading(true)
        const ver = await api.getDatasetVersion(datasetId, versionId)
        if (!mounted) return
        setVersion(ver)

        // Load preview
        try {
          const prev = await api.previewDatasetVersion(datasetId, ver.version_number, 8, 0)
          if (mounted) setPreview(prev)
        } catch {
          // Preview is optional
        }
      } catch (err: unknown) {
        if (mounted) {
          const errObj = err as { message?: string }
          setError(errObj.message || 'Failed to load dataset version.')
        }
      } finally {
        if (mounted) setIsLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [datasetId, versionId])

  if (isLoading) return <LoadingSpinner message="Loading version metadata..." />

  if (error || !version) {
    return (
      <div className="card" style={{ borderColor: 'var(--severity-critical-border)' }}>
        <div style={{ color: 'var(--severity-critical)' }}>
          {error || 'Version snapshot not found.'}
        </div>
      </div>
    )
  }

  const columnsList: ColumnSchemaItem[] =
    version.raw_schema?.columns ||
    Object.entries(version.raw_schema || {}).map(([name, dtype]) => ({
      name,
      dtype: String(dtype),
    }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Navigation Breadcrumb */}
      <div>
        <Link
          to={`/datasets/${datasetId}`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            color: 'var(--text-secondary)',
            textDecoration: 'none',
            fontSize: '13px',
            marginBottom: '8px',
          }}
        >
          <ArrowLeft size={14} />
          <span>Back to Dataset</span>
        </Link>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
            Dataset Version v{version.version_number}
          </h1>
          <span className="badge font-mono" style={{ backgroundColor: 'var(--status-success-bg)', color: 'var(--status-success)' }}>
            IMMUTABLE SNAPSHOT
          </span>
        </div>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px' }}>
          {version.change_summary || 'Original ingested dataset version.'}
        </p>
      </div>

      {/* Metrics Row */}
      <div className="grid-cols-4">
        <MetricCard
          label="Row Count"
          value={version.row_count.toLocaleString()}
          subtext="Total instances"
        />
        <MetricCard
          label="Feature Columns"
          value={version.column_count}
          subtext="Tabular width"
        />
        <MetricCard
          label="File Size"
          value={`${(version.file_size_bytes / 1024).toFixed(1)} KB`}
          subtext="Parquet compressed"
        />
        <MetricCard
          label="Created"
          value={new Date(version.created_at).toLocaleDateString()}
          subtext={new Date(version.created_at).toLocaleTimeString()}
        />
      </div>

      {/* Checksum & Provenance */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">Cryptographic & Lineage Provenance</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '13px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>SHA-256 Digest:</span>
            <span className="font-mono" style={{ color: 'var(--text-primary)' }}>
              {version.sha256_hash}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Parquet Filename:</span>
            <span className="font-mono" style={{ color: 'var(--text-primary)' }}>
              {version.file_name}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: 'var(--text-secondary)' }}>Parent Version:</span>
            <span className="font-mono" style={{ color: 'var(--text-secondary)' }}>
              {version.parent_version_id ? `ID: ${version.parent_version_id}` : '(Root version - no parent)'}
            </span>
          </div>
        </div>
      </div>

      {/* Schema Table */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <FileCode size={16} color="var(--accent-primary)" />
            <span className="card-title">Inferred Tabular Schema ({columnsList.length} columns)</span>
          </div>
        </div>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '40px' }}>#</th>
                <th>Column Name</th>
                <th style={{ width: '180px' }}>Inferred Data Type</th>
                <th style={{ width: '120px' }}>Nullable</th>
              </tr>
            </thead>
            <tbody>
              {columnsList.map((col, idx) => (
                <tr key={col.name}>
                  <td style={{ color: 'var(--text-muted)' }}>{idx + 1}</td>
                  <td>
                    <span
                      className="font-mono"
                      style={{
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                        backgroundColor: 'var(--bg-elevated)',
                        padding: '2px 8px',
                        borderRadius: 'var(--radius-sm)',
                      }}
                    >
                      {col.name}
                    </span>
                  </td>
                  <td>
                    <span className="font-mono" style={{ color: 'var(--accent-primary)', fontSize: '12px' }}>
                      {col.dtype}
                    </span>
                  </td>
                  <td>
                    <span style={{ color: 'var(--text-secondary)', fontSize: '12px' }}>
                      Yes
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bounded Data Preview */}
      {preview && preview.rows && preview.rows.length > 0 && (
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Eye size={16} color="var(--accent-primary)" />
              <span className="card-title">
                Bounded Data Preview (First {preview.rows.length} rows)
              </span>
            </div>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              Server-bounded rows. Raw datasets are never transferred in bulk.
            </span>
          </div>

          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  {preview.columns.map((col) => (
                    <th key={col} className="font-mono">
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row, rIdx) => (
                  <tr key={rIdx}>
                    {preview.columns.map((col) => (
                      <td key={col} className="font-mono" style={{ fontSize: '12px' }}>
                        {row[col] === null || row[col] === undefined ? (
                          <span style={{ color: 'var(--severity-critical)', fontStyle: 'italic' }}>null</span>
                        ) : (
                          String(row[col])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
