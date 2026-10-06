import React from 'react'
import { X, Sparkles, AlertCircle, CheckCircle, Info } from 'lucide-react'
import type { FindingExplanationResponse } from '../types/ai'
import type { QualityIssue } from '../types/analysis'
import { SeverityBadge } from './SeverityBadge'
import { LoadingSpinner } from './LoadingSpinner'

interface AIExplanationModalProps {
  isOpen: boolean
  onClose: () => void
  issue: QualityIssue | null
  explanation: FindingExplanationResponse | null
  isLoading: boolean
  error?: string | null
}

export const AIExplanationModal: React.FC<AIExplanationModalProps> = ({
  isOpen,
  onClose,
  issue,
  explanation,
  isLoading,
  error,
}) => {
  if (!isOpen || !issue) return null

  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div
        className="modal-dialog"
        style={{ maxWidth: '680px' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={18} color="var(--accent-primary)" />
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
              AI Finding Explanation
            </h3>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex',
              padding: '4px',
            }}
            aria-label="Close modal"
          >
            <X size={18} />
          </button>
        </div>

        <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {/* Issue Header Context */}
          <div
            style={{
              backgroundColor: 'var(--bg-elevated)',
              padding: '12px 16px',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <SeverityBadge severity={issue.severity} />
              <span className="font-mono" style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                {issue.module}
              </span>
              {issue.column_name && (
                <span className="font-mono" style={{ fontSize: '12px', color: 'var(--accent-primary)' }}>
                  [{issue.column_name}]
                </span>
              )}
            </div>
            <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-primary)' }}>
              {issue.title}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '4px' }}>
              {issue.description}
            </div>
          </div>

          {/* AI Banner Disclaimer */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              backgroundColor: 'rgba(59, 130, 246, 0.08)',
              border: '1px solid rgba(59, 130, 246, 0.25)',
              padding: '8px 12px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '11px',
              color: 'var(--text-secondary)',
            }}
          >
            <Info size={14} color="var(--accent-primary)" style={{ flexShrink: 0 }} />
            <span>
              <strong>AI-generated explanation:</strong> Grounded interpretation of deterministic finding.
              Underlying statistics are strictly computed by the Python engine.
            </span>
          </div>

          {isLoading ? (
            <LoadingSpinner message="Generating grounded AI explanation..." />
          ) : error ? (
            <div
              style={{
                backgroundColor: 'var(--severity-critical-bg)',
                border: '1px solid var(--severity-critical-border)',
                padding: '12px',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--severity-critical)',
                fontSize: '13px',
              }}
            >
              <AlertCircle size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} />
              {error}
            </div>
          ) : explanation ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              <div>
                <span
                  style={{
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    color: 'var(--text-secondary)',
                    fontWeight: 600,
                    letterSpacing: '0.05em',
                  }}
                >
                  Context & Overview
                </span>
                <p style={{ marginTop: '4px', fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                  {explanation.explanation}
                </p>
              </div>

              <div>
                <span
                  style={{
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    color: 'var(--text-secondary)',
                    fontWeight: 600,
                    letterSpacing: '0.05em',
                  }}
                >
                  Why It Matters
                </span>
                <p style={{ marginTop: '4px', fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                  {explanation.why_it_matters}
                </p>
              </div>

              <div>
                <span
                  style={{
                    fontSize: '11px',
                    textTransform: 'uppercase',
                    color: 'var(--text-secondary)',
                    fontWeight: 600,
                    letterSpacing: '0.05em',
                  }}
                >
                  Practical ML Impact
                </span>
                <p style={{ marginTop: '4px', fontSize: '13px', color: 'var(--text-primary)', lineHeight: 1.5 }}>
                  {explanation.practical_impact}
                </p>
              </div>

              {explanation.recommended_actions && explanation.recommended_actions.length > 0 && (
                <div>
                  <span
                    style={{
                      fontSize: '11px',
                      textTransform: 'uppercase',
                      color: 'var(--text-secondary)',
                      fontWeight: 600,
                      letterSpacing: '0.05em',
                      display: 'block',
                      marginBottom: '6px',
                    }}
                  >
                    Recommended Actions
                  </span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    {explanation.recommended_actions.map((act, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '8px',
                          fontSize: '13px',
                          backgroundColor: 'var(--bg-elevated)',
                          padding: '8px 12px',
                          borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        <CheckCircle size={14} color="var(--status-success)" style={{ marginTop: '2px', flexShrink: 0 }} />
                        <span>{act}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Provenance note */}
              <div
                className="font-mono"
                style={{
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                  borderTop: '1px solid var(--border-subtle)',
                  paddingTop: '8px',
                }}
              >
                Model: {explanation.model} | Provider: {explanation.provider} | Prompt: {explanation.prompt_version}
              </div>
            </div>
          ) : null}
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
