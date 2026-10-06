import React, { useState, useRef } from 'react'
import { UploadCloud, X, FileText, CheckCircle2, AlertCircle } from 'lucide-react'
import { api } from '../services/api'
import type { DatasetUploadResponse } from '../types/dataset'

interface UploadModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: (uploaded: DatasetUploadResponse) => void
  datasetId?: string // If present, uploading new version to existing dataset
  parentVersionId?: string
}

export const UploadModal: React.FC<UploadModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  datasetId,
  parentVersionId,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [changeSummary, setChangeSummary] = useState('')
  const [isUploading, setIsUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState<DatasetUploadResponse | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  if (!isOpen) return null

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0]
      setSelectedFile(file)
      setError(null)
      if (!name) {
        // Strip extension for default dataset name
        const cleanName = file.name.replace(/\.[^/.]+$/, '').replace(/[-_]/g, ' ')
        setName(cleanName.charAt(0).toUpperCase() + cleanName.slice(1))
      }
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedFile) {
      setError('Please select a file to upload.')
      return
    }

    try {
      setIsUploading(true)
      setError(null)

      const formData = new FormData()
      formData.append('file', selectedFile)

      let res: DatasetUploadResponse
      if (datasetId) {
        if (parentVersionId) formData.append('parent_version_id', parentVersionId)
        if (changeSummary) formData.append('change_summary', changeSummary)
        res = await api.uploadNewVersion(datasetId, formData)
      } else {
        formData.append('name', name.trim() || selectedFile.name)
        if (description.trim()) formData.append('description', description.trim())
        res = await api.uploadDataset(formData)
      }

      setUploadSuccess(res)
      setTimeout(() => {
        onSuccess(res)
        onClose()
      }, 1200)
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string }
      const detail = errorObj.response?.data?.detail || errorObj.message || 'Failed to upload dataset.'
      setError(detail)
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal-dialog"
        style={{ maxWidth: '560px' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <UploadCloud size={18} color="var(--accent-primary)" />
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {datasetId ? 'Upload New Dataset Version' : 'Upload New Dataset'}
            </h3>
          </div>
          <button
            onClick={onClose}
            disabled={isUploading}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: isUploading ? 'not-allowed' : 'pointer',
              padding: '4px',
            }}
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {uploadSuccess ? (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  padding: '24px',
                  backgroundColor: 'var(--status-success-bg)',
                  border: '1px solid var(--status-success-border)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--status-success)',
                  textAlign: 'center',
                  gap: '8px',
                }}
              >
                <CheckCircle2 size={32} />
                <div style={{ fontWeight: 600, fontSize: '15px' }}>
                  Upload Successful!
                </div>
                <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                  Version {uploadSuccess.version_number} created with {uploadSuccess.row_count} rows and {uploadSuccess.column_count} columns.
                </div>
              </div>
            ) : (
              <>
                {/* File Drop Area */}
                <div
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    border: '1px dashed var(--border-default)',
                    borderRadius: 'var(--radius-md)',
                    padding: '28px',
                    textAlign: 'center',
                    backgroundColor: 'var(--bg-elevated)',
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: '8px',
                    transition: 'border-color 0.15s ease',
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.xlsx,.json,.parquet"
                    onChange={handleFileChange}
                    style={{ display: 'none' }}
                  />
                  <UploadCloud size={28} color="var(--accent-primary)" />
                  <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
                    {selectedFile ? selectedFile.name : 'Click or drag file to upload'}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    Supported formats: CSV, XLSX, JSON, Parquet (up to 50MB)
                  </div>

                  {selectedFile && (
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        marginTop: '8px',
                        backgroundColor: 'var(--bg-app)',
                        padding: '4px 10px',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '12px',
                        color: 'var(--text-secondary)',
                      }}
                    >
                      <FileText size={14} />
                      <span className="font-mono">{(selectedFile.size / 1024).toFixed(1)} KB</span>
                    </div>
                  )}
                </div>

                {!datasetId ? (
                  <>
                    <div>
                      <label
                        style={{
                          display: 'block',
                          fontSize: '12px',
                          fontWeight: 600,
                          color: 'var(--text-secondary)',
                          marginBottom: '6px',
                        }}
                      >
                        Dataset Name
                      </label>
                      <input
                        type="text"
                        className="input-text"
                        style={{ width: '100%' }}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="e.g. Customer Churn 2026"
                        required
                      />
                    </div>
                    <div>
                      <label
                        style={{
                          display: 'block',
                          fontSize: '12px',
                          fontWeight: 600,
                          color: 'var(--text-secondary)',
                          marginBottom: '6px',
                        }}
                      >
                        Description (optional)
                      </label>
                      <textarea
                        className="input-text"
                        style={{ width: '100%', minHeight: '60px', resize: 'vertical' }}
                        value={description}
                        onChange={(e) => setDescription(e.target.value)}
                        placeholder="Context regarding source and problem type..."
                      />
                    </div>
                  </>
                ) : (
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: 'var(--text-secondary)',
                        marginBottom: '6px',
                      }}
                    >
                      Version Change Summary (optional)
                    </label>
                    <input
                      type="text"
                      className="input-text"
                      style={{ width: '100%' }}
                      value={changeSummary}
                      onChange={(e) => setChangeSummary(e.target.value)}
                      placeholder="e.g. Manually cleansed null entries from Q3 records"
                    />
                  </div>
                )}

                {error && (
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '10px 12px',
                      backgroundColor: 'var(--severity-critical-bg)',
                      border: '1px solid var(--severity-critical-border)',
                      borderRadius: 'var(--radius-sm)',
                      color: 'var(--severity-critical)',
                      fontSize: '13px',
                    }}
                  >
                    <AlertCircle size={16} style={{ flexShrink: 0 }} />
                    <span>{error}</span>
                  </div>
                )}
              </>
            )}
          </div>

          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isUploading}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!selectedFile || isUploading || Boolean(uploadSuccess)}
            >
              {isUploading ? 'Uploading & Normalizing...' : 'Upload Dataset'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
