import React, { useEffect, useState, useMemo } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { Search, Plus, ArrowUpDown, ChevronRight } from 'lucide-react'
import { api } from '../services/api'
import type { DatasetListItem } from '../types/dataset'
import { EmptyState } from '../components/EmptyState'
import { LoadingSpinner } from '../components/LoadingSpinner'

export const DatasetsPage: React.FC = () => {
  const [datasets, setDatasets] = useState<DatasetListItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [sortField, setSortField] = useState<'name' | 'created_at' | 'rows'>('created_at')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')
  const context = useOutletContext<{ openUpload?: () => void }>()
  const openUpload = context?.openUpload

  useEffect(() => {
    let mounted = true
    const load = async () => {
      try {
        setIsLoading(true)
        const items = await api.listDatasets()
        if (mounted) setDatasets(items)
      } catch (err: unknown) {
        if (mounted) {
          const errObj = err as { message?: string }
          setError(errObj.message || 'Failed to load datasets.')
        }
      } finally {
        if (mounted) setIsLoading(false)
      }
    }
    load()
    return () => {
      mounted = false
    }
  }, [])

  const filteredAndSorted = useMemo(() => {
    return datasets
      .filter((ds) => {
        if (!searchQuery.trim()) return true
        const q = searchQuery.toLowerCase()
        return (
          ds.name.toLowerCase().includes(q) ||
          (ds.description && ds.description.toLowerCase().includes(q))
        )
      })
      .sort((a, b) => {
        let cmp = 0
        if (sortField === 'name') cmp = a.name.localeCompare(b.name)
        else if (sortField === 'created_at')
          cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        else if (sortField === 'rows') cmp = a.latest_row_count - b.latest_row_count

        return sortOrder === 'desc' ? -cmp : cmp
      })
  }, [datasets, searchQuery, sortField, sortOrder])

  const toggleSort = (field: 'name' | 'created_at' | 'rows') => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortOrder('desc')
    }
  }

  if (isLoading) return <LoadingSpinner message="Loading dataset registry..." />

  if (error) {
    return (
      <div className="card" style={{ borderColor: 'var(--severity-critical-border)' }}>
        <div style={{ color: 'var(--severity-critical)', fontSize: '14px' }}>
          Error loading datasets: {error}
        </div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
            Datasets ({datasets.length})
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
            Managed tabular datasets and versioned parquet storage.
          </p>
        </div>
        <button className="btn btn-primary" onClick={openUpload}>
          <Plus size={16} />
          <span>Upload Dataset</span>
        </button>
      </div>

      {/* Search & Filter Toolbar */}
      <div style={{ display: 'flex', gap: '12px', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ position: 'relative', width: '320px' }}>
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
            placeholder="Search by dataset name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{ paddingLeft: '32px', width: '100%' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => toggleSort('created_at')}
          >
            <ArrowUpDown size={12} />
            <span>Date {sortField === 'created_at' ? (sortOrder === 'desc' ? '↓' : '↑') : ''}</span>
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => toggleSort('rows')}
          >
            <ArrowUpDown size={12} />
            <span>Rows {sortField === 'rows' ? (sortOrder === 'desc' ? '↓' : '↑') : ''}</span>
          </button>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => toggleSort('name')}
          >
            <ArrowUpDown size={12} />
            <span>Name {sortField === 'name' ? (sortOrder === 'desc' ? '↓' : '↑') : ''}</span>
          </button>
        </div>
      </div>

      {/* Dataset Grid / Table */}
      {filteredAndSorted.length === 0 ? (
        <EmptyState
          title={searchQuery ? 'No matching datasets' : 'No datasets registered'}
          description={
            searchQuery
              ? 'Try modifying your search query or clear filters.'
              : 'Ingest your first dataset to run deterministic profiling and ML readiness analysis.'
          }
          actionLabel={searchQuery ? undefined : 'Upload Dataset'}
          onAction={openUpload}
        />
      ) : (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Dataset Name</th>
                <th style={{ width: '100px' }}>Version</th>
                <th style={{ width: '120px' }}>Rows</th>
                <th style={{ width: '100px' }}>Columns</th>
                <th style={{ width: '160px' }}>Created</th>
                <th style={{ width: '80px', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredAndSorted.map((ds) => (
                <tr key={ds.dataset_id} style={{ cursor: 'pointer' }}>
                  <td>
                    <Link
                      to={`/datasets/${ds.dataset_id}`}
                      style={{
                        textDecoration: 'none',
                        color: 'inherit',
                        display: 'block',
                      }}
                    >
                      <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                        {ds.name}
                      </div>
                      {ds.description && (
                        <div
                          style={{
                            fontSize: '12px',
                            color: 'var(--text-secondary)',
                            maxWidth: '460px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {ds.description}
                        </div>
                      )}
                    </Link>
                  </td>
                  <td>
                    <span className="badge font-mono" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--accent-primary)' }}>
                      v{ds.latest_version_number}
                    </span>
                  </td>
                  <td>
                    <span className="font-mono">{ds.latest_row_count.toLocaleString()}</span>
                  </td>
                  <td>
                    <span className="font-mono">{ds.latest_column_count}</span>
                  </td>
                  <td>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {new Date(ds.created_at).toLocaleDateString()}
                    </span>
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <Link
                      to={`/datasets/${ds.dataset_id}`}
                      className="btn btn-secondary btn-sm"
                      style={{ padding: '4px 8px' }}
                    >
                      <ChevronRight size={14} />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
