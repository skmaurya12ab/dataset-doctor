import React, { useEffect, useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { GitCompare, ArrowRight, AlertCircle } from 'lucide-react'
import { api } from '../services/api'
import type { VersionComparison } from '../types/remediation'
import type { Dataset, DatasetListItem } from '../types/dataset'
import { VersionComparisonView } from '../components/VersionComparisonView'
import { LoadingSpinner } from '../components/LoadingSpinner'

export const ComparisonPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const datasetIdParam = searchParams.get('datasetId')
  const v1Param = searchParams.get('v1')
  const v2Param = searchParams.get('v2')

  const [datasets, setDatasets] = useState<DatasetListItem[]>([])
  const [selectedDataset, setSelectedDataset] = useState<Dataset | null>(null)
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(datasetIdParam || '')
  const [selectedV1, setSelectedV1] = useState<string>(v1Param || '')
  const [selectedV2, setSelectedV2] = useState<string>(v2Param || '')

  const [comparison, setComparison] = useState<VersionComparison | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 1. Load datasets list
  useEffect(() => {
    api.listDatasets().then(async (items) => {
      setDatasets(items)

      if (datasetIdParam) {
        setSelectedDatasetId(datasetIdParam)
      } else if (v1Param || v2Param) {
        let matchedDatasetId = ''
        for (const item of items) {
          try {
            const ds = await api.getDataset(item.dataset_id)
            if (ds.versions.some((v) => v.id === v1Param || v.id === v2Param)) {
              matchedDatasetId = item.dataset_id
              break
            }
          } catch {
            // ignore
          }
        }
        setSelectedDatasetId(matchedDatasetId || (items[0]?.dataset_id ?? ''))
      } else {
        setSelectedDatasetId((prev) => {
          if (prev) return prev
          const multi = items.find((d) => d.latest_version_number >= 2)
          return multi ? multi.dataset_id : (items[0]?.dataset_id ?? '')
        })
      }
    })
  }, [datasetIdParam, v1Param, v2Param])

  // 2. Load dataset details with versions whenever selectedDatasetId changes
  useEffect(() => {
    if (!selectedDatasetId) return
    api.getDataset(selectedDatasetId).then((ds) => {
      setSelectedDataset(ds)
      if (ds.versions && ds.versions.length >= 2) {
        const hasV1 = v1Param && ds.versions.some((v) => v.id === v1Param)
        const hasV2 = v2Param && ds.versions.some((v) => v.id === v2Param)

        setSelectedV1((prev) => (hasV1 ? v1Param! : prev || ds.versions[0].id))
        setSelectedV2((prev) => (hasV2 ? v2Param! : prev || ds.versions[ds.versions.length - 1].id))
      } else {
        setSelectedV1('')
        setSelectedV2('')
      }
    })
  }, [selectedDatasetId, v1Param, v2Param])



  // 3. Load comparison
  const loadComparison = useCallback(async (dsId: string, v1: string, v2: string) => {
    if (!dsId || !v1 || !v2 || v1 === v2) return
    try {
      setIsLoading(true)
      setError(null)
      const data = await api.compareVersions(dsId, v1, v2)
      setComparison(data)
    } catch (err: unknown) {
      const errObj = err as { response?: { data?: { detail?: string } }; message?: string }
      const detail = errObj.response?.data?.detail || errObj.message || 'Failed to compare versions.'
      setError(detail)
      setComparison(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (selectedDatasetId && selectedV1 && selectedV2 && selectedV1 !== selectedV2) {
      loadComparison(selectedDatasetId, selectedV1, selectedV2)
    }
  }, [selectedDatasetId, selectedV1, selectedV2, loadComparison])



  const handleCompareSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedDatasetId && selectedV1 && selectedV2) {
      setSearchParams({
        datasetId: selectedDatasetId,
        v1: selectedV1,
        v2: selectedV2,
      })
      loadComparison(selectedDatasetId, selectedV1, selectedV2)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Title */}
      <div>
        <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
          Version Comparison & Audit
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
          Deterministic before/after audit: Did remediation actually improve tabular quality?
        </p>
      </div>

      {/* Version Selector Form */}
      <form onSubmit={handleCompareSubmit} className="card">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '16px', alignItems: 'flex-end' }}>
          {/* Dataset selector */}
          <div style={{ minWidth: '220px', flex: 1 }}>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
              Dataset
            </label>
            <select
              className="select-input"
              style={{ width: '100%' }}
              value={selectedDatasetId}
              onChange={(e) => {
                setSelectedDatasetId(e.target.value)
                setSelectedV1('')
                setSelectedV2('')
              }}
            >
              {datasets.map((d) => (
                <option key={d.dataset_id} value={d.dataset_id}>
                  {d.name} ({d.latest_version_number} versions)
                </option>
              ))}
            </select>
          </div>

          {/* V1 (Source) selector */}
          <div style={{ minWidth: '180px', flex: 1 }}>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
              Before (Source Version)
            </label>
            <select
              className="select-input font-mono"
              style={{ width: '100%' }}
              value={selectedV1}
              onChange={(e) => setSelectedV1(e.target.value)}
              disabled={!selectedDataset}
            >
              <option value="">Select source version</option>
              {selectedDataset?.versions.map((ver) => (
                <option key={ver.id} value={ver.id}>
                  v{ver.version_number} ({ver.row_count} rows)
                </option>
              ))}
            </select>
          </div>

          <div style={{ paddingBottom: '8px', color: 'var(--text-muted)' }}>
            <ArrowRight size={16} />
          </div>

          {/* V2 (Remediated) selector */}
          <div style={{ minWidth: '180px', flex: 1 }}>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, marginBottom: '6px' }}>
              After (Remediated Version)
            </label>
            <select
              className="select-input font-mono"
              style={{ width: '100%' }}
              value={selectedV2}
              onChange={(e) => setSelectedV2(e.target.value)}
              disabled={!selectedDataset}
            >
              <option value="">Select target version</option>
              {selectedDataset?.versions.map((ver) => (
                <option key={ver.id} value={ver.id}>
                  v{ver.version_number} ({ver.row_count} rows)
                </option>
              ))}
            </select>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={!selectedV1 || !selectedV2 || selectedV1 === selectedV2 || isLoading}
          >
            <GitCompare size={14} />
            <span>Compare</span>
          </button>
        </div>
      </form>

      {/* Loading & Error States */}
      {isLoading ? (
        <LoadingSpinner message="Computing exact metric deltas and defect lifecycle transitions..." />
      ) : error ? (
        <div
          className="card"
          style={{
            borderColor: 'var(--severity-critical-border)',
            backgroundColor: 'var(--severity-critical-bg)',
            color: 'var(--severity-critical)',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontSize: '13px',
          }}
        >
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      ) : comparison ? (
        <VersionComparisonView comparison={comparison} />
      ) : (
        <div className="card" style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Please select two distinct dataset versions with completed analyses to view comparison.
        </div>
      )}
    </div>
  )
}
