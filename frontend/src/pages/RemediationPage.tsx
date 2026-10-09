import React, { useEffect, useState, useCallback } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import {
  Sparkles,
  GitCompare,
  ArrowRight,
  AlertCircle,
  CheckCircle2,
  Clock,
  Play,
  RotateCw,
} from 'lucide-react'
import { api } from '../services/api'
import { normalizeAIReport } from '../utils/aiReport'
import type { AIReport } from '../types/ai'
import type { RemediationExecution } from '../types/remediation'
import type { AnalysisRun } from '../types/analysis'
import { RemediationPlanView } from '../components/RemediationPlanView'
import { ApprovalModal } from '../components/ApprovalModal'
import { RemediationStatusBadge } from '../components/RemediationStatusBadge'
import { LoadingSpinner } from '../components/LoadingSpinner'

export const RemediationPage: React.FC = () => {
  const [searchParams] = useSearchParams()
  const runId = searchParams.get('runId')
  const navigate = useNavigate()

  const [aiReport, setAiReport] = useState<AIReport | null>(null)
  const [analysisRun, setAnalysisRun] = useState<AnalysisRun | null>(null)
  const [execution, setExecution] = useState<RemediationExecution | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false)
  const [isApplying, setIsApplying] = useState(false)
  const [isApprovalOpen, setIsApprovalOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async (rId: string) => {
    try {
      setIsLoading(true)
      setError(null)

      const run = await api.getAnalysisRun(rId)
      setAnalysisRun(run)

      // Try fetching existing plan first
      try {
        const report = await api.getAIPlan(rId)
        setAiReport(report)
      } catch {
        // Plan doesn't exist yet; user can click generate
      }
    } catch (err: unknown) {
      const errObj = err as { message?: string }
      setError(errObj.message || 'Failed to load analysis for remediation.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (runId) {
      loadData(runId)
    } else {
      // Find latest completed analysis run
      api.getOverviewStats().then((stats) => {
        if (stats.latest_analyses && stats.latest_analyses.length > 0) {
          const completed = stats.latest_analyses.find((r) => r.status === 'COMPLETED')
          if (completed) loadData(completed.id)
          else loadData(stats.latest_analyses[0].id)
        } else {
          setIsLoading(false)
        }
      }).catch(() => setIsLoading(false))
    }
  }, [runId, loadData])

  const handleGeneratePlan = async (force = false) => {
    if (!analysisRun) return
    try {
      setIsGeneratingPlan(true)
      setError(null)
      const report = await api.generateAIPlan(analysisRun.id, force)
      setAiReport(report)
    } catch (err: unknown) {
      const errObj = err as { message?: string }
      setError(errObj.message || 'Failed to generate remediation plan.')
    } finally {
      setIsGeneratingPlan(false)
    }
  }

  const handleApproveAndApply = async (approvedBy: string) => {
    if (!analysisRun || !aiReport) return
    try {
      setIsApplying(true)
      setIsApprovalOpen(false)

      // Trigger remediation apply endpoint
      const exec = await api.applyRemediation(analysisRun.id, {
        ai_report_id: aiReport.id,
        approval: true,
        approved_by: approvedBy,
      })
      setExecution(exec)

      // Poll until execution finishes
      const finishedExec = await api.pollRemediationExecution(
        exec.id,
        (updated) => setExecution(updated),
      )
      setExecution(finishedExec)
    } catch (err: unknown) {
      const errObj = err as { message?: string }
      alert(`Remediation application failed: ${errObj.message}`)
    } finally {
      setIsApplying(false)
    }
  }

  if (isLoading) return <LoadingSpinner message="Loading remediation workspace..." />

  if (error && !analysisRun) {
    return (
      <div
        className="card"
        style={{
          borderColor: 'var(--severity-critical-border)',
          backgroundColor: 'var(--severity-critical-bg)',
          color: 'var(--severity-critical)',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          padding: '24px',
        }}
      >
        <AlertCircle size={20} />
        <div>
          <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '4px' }}>
            Failed to load analysis for remediation
          </div>
          <div style={{ fontSize: '13px' }}>{error}</div>
        </div>
      </div>
    )
  }

  if (!analysisRun) {
    return (
      <div className="card" style={{ textAlign: 'center', padding: '36px' }}>
        <h3 style={{ fontSize: '16px', color: 'var(--text-primary)', marginBottom: '8px' }}>
          No Analysis Run Selected
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
          Remediation plans are synthesized from completed deterministic analysis runs.
        </p>
        <Link to="/analysis" className="btn btn-primary">
          View Analyses
        </Link>
      </div>
    )
  }

  const transformationSpecs =
    aiReport?.content?.transformation_specs ?? aiReport?.transformation_specs ?? []
  const planContent =
    aiReport?.content ?? (aiReport ? normalizeAIReport(aiReport).content : null)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Header Banner */}
      <div
        className="card"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '16px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
              Remediation & Execution Workflow
            </h1>
            {execution ? (
              <RemediationStatusBadge status={execution.status} />
            ) : aiReport ? (
              <span className="badge font-mono" style={{ backgroundColor: 'var(--severity-medium-bg)', color: 'var(--severity-medium)' }}>
                PENDING APPROVAL
              </span>
            ) : (
              <span className="badge font-mono" style={{ backgroundColor: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                PLAN NOT GENERATED
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: '16px', marginTop: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
            <span className="font-mono">Analysis Run: {analysisRun.id.slice(0, 8)}...</span>
            <span>Version ID: {analysisRun.dataset_version_id.slice(0, 8)}...</span>
            <span>Total findings: {analysisRun.total_issues_count}</span>
          </div>
        </div>

        {/* Top Actions */}
        <div style={{ display: 'flex', gap: '10px' }}>
          {aiReport && !execution && (
            <button
              className="btn btn-primary"
              onClick={() => setIsApprovalOpen(true)}
              disabled={isApplying || transformationSpecs.length === 0}
            >
              <Play size={14} />
              <span>Review & Approve Plan</span>
            </button>
          )}

          <button
            className="btn btn-secondary btn-sm"
            onClick={() => handleGeneratePlan(true)}
            disabled={isGeneratingPlan || isApplying}
          >
            <RotateCw size={13} className={isGeneratingPlan ? 'spin' : ''} />
            <span>{aiReport ? 'Regenerate Plan' : 'Synthesize AI Plan'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div
          className="card"
          style={{
            borderColor: 'var(--severity-critical-border)',
            backgroundColor: 'var(--severity-critical-bg)',
            color: 'var(--severity-critical)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '13px',
          }}
        >
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}

      {/* Execution Status Feedback Banner */}
      {execution && (
        <div
          className="card"
          style={{
            borderColor:
              execution.status === 'COMPLETED'
                ? 'var(--status-success-border)'
                : execution.status === 'FAILED'
                ? 'var(--severity-critical-border)'
                : 'var(--accent-primary)',
          }}
        >
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <RemediationStatusBadge status={execution.status} />
              <span className="card-title">Execution Lifecycle Telemetry</span>
            </div>
            <span className="font-mono" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Execution ID: {execution.id.slice(0, 8)}...
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ fontSize: '14px', color: 'var(--text-primary)' }}>
              {execution.status === 'COMPLETED' ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--status-success)' }}>
                  <CheckCircle2 size={18} />
                  <span>
                    Remediation successfully applied! An immutable new DatasetVersion was created.
                  </span>
                </div>
              ) : execution.status === 'RUNNING' || execution.status === 'VALIDATING' ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--accent-primary)' }}>
                  <Clock size={18} />
                  <span>
                    Applying approved transformations in memory and creating immutable version snapshot...
                  </span>
                </div>
              ) : execution.status === 'FAILED' ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--severity-critical)' }}>
                  <AlertCircle size={18} />
                  <span>
                    Remediation execution failed: {execution.error_message || 'Validation error'}.
                    Original dataset version was preserved intact.
                  </span>
                </div>
              ) : null}
            </div>

            {/* If completed, show button to Compare Versions */}
            {execution.status === 'COMPLETED' && execution.result_dataset_version_id && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  backgroundColor: 'var(--bg-elevated)',
                  padding: '12px 16px',
                  borderRadius: 'var(--radius-sm)',
                  marginTop: '8px',
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: '13px', color: 'var(--text-primary)' }}>
                    Ready for Before / After Quality Audit
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    Re-analysis has been automatically triggered on the remediated version.
                  </div>
                </div>

                <button
                  className="btn btn-primary btn-sm"
                  onClick={() =>
                    navigate(
                      `/versions?v1=${execution.source_dataset_version_id}&v2=${execution.result_dataset_version_id}`,
                    )
                  }


                >
                  <GitCompare size={14} />
                  <span>Compare Before & After</span>
                  <ArrowRight size={13} />
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Main Plan View */}
      {isGeneratingPlan ? (
        <LoadingSpinner message="Synthesizing advisory remediation plan with LLM provider..." />
      ) : aiReport && planContent ? (
        <RemediationPlanView
          plan={planContent}
          onOpenApprovalModal={() => setIsApprovalOpen(true)}
          isExecutionDisabled={isApplying || Boolean(execution && execution.status === 'COMPLETED')}
        />
      ) : (
        <div
          className="card"
          style={{
            textAlign: 'center',
            padding: '48px 24px',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <Sparkles size={32} color="var(--accent-primary)" />
          <h3 style={{ fontSize: '16px', fontWeight: 600 }}>No Remediation Plan Synthesized Yet</h3>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)', maxWidth: '480px' }}>
            The AI engine synthesizes allowlisted transformation proposals (`DROP_COLUMN`, `REMOVE_DUPLICATES`, `IMPUTE`, `CAST_TYPE`, `CLIP_OUTLIERS`)
            grounded in deterministic quality findings.
          </p>
          <button
            className="btn btn-primary"
            onClick={() => handleGeneratePlan(false)}
            disabled={isGeneratingPlan}
          >
            <span>Synthesize Advisory Plan</span>
          </button>
        </div>
      )}

      {/* Explicit Human Approval Modal */}
      {aiReport && (
        <ApprovalModal
          isOpen={isApprovalOpen}
          onClose={() => setIsApprovalOpen(false)}
          onApprove={handleApproveAndApply}
          transformationSpecs={transformationSpecs}
          isApplying={isApplying}
        />
      )}
    </div>
  )
}
