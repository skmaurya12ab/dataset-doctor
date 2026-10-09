import React from 'react'
import {
  FileCode,
  Shield,
  Layers,
  Sparkles,
  ArrowRight,
} from 'lucide-react'
import type { AIReportContent, TransformationSpec } from '../types/ai'
import { SeverityBadge } from './SeverityBadge'

interface RemediationPlanViewProps {
  plan: AIReportContent
  onOpenApprovalModal?: () => void
  isExecutionDisabled?: boolean
}

export const RemediationPlanView: React.FC<RemediationPlanViewProps> = ({
  plan,
  onOpenApprovalModal,
  isExecutionDisabled = false,
}) => {
  const specs = plan?.transformation_specs ?? []
  const steps = plan?.prioritized_remediation_steps ?? plan?.remediation_plan ?? []
  const risks = plan?.risk_assessment ?? []
  const summary = plan?.executive_summary ?? 'No executive summary provided.'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Executive Summary */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sparkles size={16} color="var(--accent-primary)" />
            <span className="card-title">Executive Summary & Strategy</span>
          </div>
          {onOpenApprovalModal && (
            <button
              className="btn btn-primary"
              onClick={onOpenApprovalModal}
              disabled={isExecutionDisabled || specs.length === 0}
            >
              <span>Review & Approve Plan</span>
              <ArrowRight size={14} />
            </button>
          )}
        </div>
        <p style={{ fontSize: '14px', color: 'var(--text-primary)', lineHeight: 1.6 }}>
          {summary}
        </p>
      </div>

      {/* Advisory Transformation Specs */}
      <div className="card">
        <div className="card-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Layers size={16} color="var(--accent-primary)" />
            <span className="card-title">
              Proposed Transformations ({specs.length})
            </span>
          </div>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Requires explicit human approval before execution
          </span>
        </div>

        {specs.length === 0 ? (
          <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
            No automated transformations proposed. Manual data curation or feature engineering recommended.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {specs.map((spec: TransformationSpec, idx: number) => {
              const targetCol = spec.column || (spec.columns ? spec.columns.join(', ') : 'All columns')
              return (
                <div
                  key={idx}
                  style={{
                    backgroundColor: 'var(--bg-elevated)',
                    border: '1px solid var(--border-subtle)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '14px',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '8px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span
                        className="font-mono"
                        style={{
                          fontSize: '12px',
                          fontWeight: 700,
                          color: 'var(--accent-primary)',
                          backgroundColor: 'var(--accent-subtle)',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-sm)',
                        }}
                      >
                        #{idx + 1} {spec.action}
                      </span>
                      <span className="font-mono" style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        Target: {targetCol}
                      </span>
                    </div>
                  </div>

                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                    <strong>Rationale:</strong> {spec.rationale}
                  </div>

                  {spec.parameters && Object.keys(spec.parameters).length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Parameters:</span>
                      <span
                        className="font-mono"
                        style={{
                          backgroundColor: 'var(--bg-app)',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-sm)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        {JSON.stringify(spec.parameters)}
                      </span>
                    </div>
                  )}

                  {spec.source_issue_ids && spec.source_issue_ids.length > 0 && (
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      Motivated by {spec.source_issue_ids.length} deterministic findings
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Prioritized Steps & Risk Assessment */}
      <div className="grid-cols-2">
        <div className="card">
          <div className="card-header">
            <span className="card-title">Prioritized Remediation Roadmap</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {steps.map((step, idx) => (
              <div
                key={idx}
                style={{
                  padding: '10px 12px',
                  backgroundColor: 'var(--bg-elevated)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span className="font-mono" style={{ fontWeight: 600, color: 'var(--accent-primary)' }}>
                    Step {step.priority}: {step.issue_reference}
                  </span>
                </div>
                <div style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>{step.recommendation}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Reason: {step.reason}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <span className="card-title">Risk Assessment</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {risks.map((risk, idx) => (
              <div
                key={idx}
                style={{
                  padding: '10px 12px',
                  backgroundColor: 'var(--bg-elevated)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '13px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{risk.risk_type || risk.category || 'Identified Risk'}</span>
                  <SeverityBadge severity={risk.severity || 'INFO'} showIcon={false} />
                </div>
                <div style={{ color: 'var(--text-secondary)', marginBottom: '4px' }}>{risk.summary}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Impact: {risk.ml_impact}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Inert Generated Python Code (Advisory only) */}
      {plan.generated_python_code && (
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <FileCode size={16} color="var(--text-muted)" />
              <span className="card-title">Advisory Python Snippet (Read-Only)</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--text-muted)' }}>
              <Shield size={13} color="var(--status-success)" />
              <span>Inert. Execution always occurs via deterministic engine.</span>
            </div>
          </div>
          <pre
            className="font-mono"
            style={{
              backgroundColor: 'var(--bg-app)',
              padding: '14px',
              borderRadius: 'var(--radius-sm)',
              fontSize: '12px',
              color: 'var(--text-secondary)',
              overflowX: 'auto',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <code>{plan.generated_python_code}</code>
          </pre>
        </div>
      )}
    </div>
  )
}
