import React, { useState } from 'react'
import { ShieldCheck, X, AlertTriangle, Play } from 'lucide-react'
import type { TransformationSpec } from '../types/ai'

interface ApprovalModalProps {
  isOpen: boolean
  onClose: () => void
  onApprove: (approvedBy: string) => void
  transformationSpecs: TransformationSpec[]
  isApplying: boolean
}

export const ApprovalModal: React.FC<ApprovalModalProps> = ({
  isOpen,
  onClose,
  onApprove,
  transformationSpecs,
  isApplying,
}) => {
  const [hasConfirmed, setHasConfirmed] = useState(false)
  const [reviewerName, setReviewerName] = useState('data-engineer')

  if (!isOpen) return null

  const handleApprove = () => {
    if (!hasConfirmed || isApplying) return
    onApprove(reviewerName.trim() || 'data-engineer')
  }

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal-dialog"
        style={{ maxWidth: '600px' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <ShieldCheck size={18} color="var(--status-success)" />
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Approve Deterministic Remediation
            </h3>
          </div>
          <button
            onClick={onClose}
            disabled={isApplying}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: isApplying ? 'not-allowed' : 'pointer',
              padding: '4px',
            }}
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            You are about to authorize the deterministic execution of{' '}
            <strong>{transformationSpecs.length} allowlisted transformation(s)</strong>.
            The Python engine will execute these in memory, produce an immutable new DatasetVersion,
            and automatically trigger comprehensive re-analysis.
          </p>

          <div
            style={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-sm)',
              padding: '12px',
              maxHeight: '180px',
              overflowY: 'auto',
            }}
          >
            <span
              style={{
                fontSize: '11px',
                textTransform: 'uppercase',
                color: 'var(--text-secondary)',
                fontWeight: 600,
                display: 'block',
                marginBottom: '8px',
              }}
            >
              Approved Pipeline Actions
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {transformationSpecs.map((spec, i) => (
                <div
                  key={i}
                  className="font-mono"
                  style={{
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '4px 6px',
                    backgroundColor: 'var(--bg-app)',
                    borderRadius: 'var(--radius-sm)',
                  }}
                >
                  <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>
                    #{i + 1} {spec.action}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>
                    {spec.column || (spec.columns ? spec.columns.join(', ') : 'all')}
                  </span>
                </div>
              ))}
            </div>
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
              Human Reviewer Identifier:
            </label>
            <input
              type="text"
              className="input-text"
              style={{ width: '100%' }}
              value={reviewerName}
              onChange={(e) => setReviewerName(e.target.value)}
              disabled={isApplying}
              placeholder="e.g. data-engineer or username"
            />
          </div>

          <div
            style={{
              backgroundColor: 'rgba(234, 179, 8, 0.08)',
              border: '1px solid rgba(234, 179, 8, 0.25)',
              padding: '12px',
              borderRadius: 'var(--radius-sm)',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--severity-medium)' }}>
              <AlertTriangle size={16} />
              <span style={{ fontSize: '13px', fontWeight: 600 }}>Explicit Human Approval Required</span>
            </div>
            <label
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                cursor: 'pointer',
                fontSize: '13px',
                color: 'var(--text-primary)',
              }}
            >
              <input
                type="checkbox"
                checked={hasConfirmed}
                onChange={(e) => setHasConfirmed(e.target.checked)}
                disabled={isApplying}
                style={{ width: '16px', height: '16px', cursor: 'pointer' }}
              />
              <span>I understand these changes will create an immutable new dataset version.</span>
            </label>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={isApplying}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleApprove}
            disabled={!hasConfirmed || isApplying || !reviewerName.trim()}
          >
            <Play size={14} />
            <span>{isApplying ? 'Applying Pipeline...' : 'Approve & Apply'}</span>
          </button>
        </div>
      </div>
    </div>
  )
}
