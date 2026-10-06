import React, { useEffect, useState, useCallback } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  Wrench,
  ShieldAlert,
  HelpCircle,
} from 'lucide-react'
import { api } from '../services/api'
import type {
  AnalysisRun,
  QualityIssue,
  VisualizationData,
  HeuristicBreakdown,
} from '../types/analysis'
import type { FindingExplanationResponse } from '../types/ai'
import { ReadinessCard } from '../components/ReadinessCard'
import { IssueTable } from '../components/IssueTable'
import { AIExplanationModal } from '../components/AIExplanationModal'
import { LoadingSpinner } from '../components/LoadingSpinner'
import { MissingnessChart } from '../components/charts/MissingnessChart'
import { DistributionChart } from '../components/charts/DistributionChart'
import { CorrelationHeatmap } from '../components/charts/CorrelationHeatmap'
import { ClassDistributionChart } from '../components/charts/ClassDistributionChart'
import { CardinalityTable } from '../components/charts/CardinalityTable'

export const AnalysisPage: React.FC = () => {
  const [searchParams] = useSearchParams()
  const runId = searchParams.get('runId')

  const [run, setRun] = useState<AnalysisRun | null>(null)
  const [issues, setIssues] = useState<QualityIssue[]>([])
  const [heuristic, setHeuristic] = useState<HeuristicBreakdown | null>(null)
  const [vizData, setVizData] = useState<VisualizationData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // AI Explanation Modal State
  const [selectedIssue, setSelectedIssue] = useState<QualityIssue | null>(null)
  const [explanation, setExplanation] = useState<FindingExplanationResponse | null>(null)
  const [isExplaining, setIsExplaining] = useState(false)
  const [explanationError, setExplanationError] = useState<string | null>(null)

  const loadAnalysis = useCallback(async (id: string) => {
    try {
      setIsLoading(true)
      setError(null)

      // Fetch or poll analysis run
      const runData = await api.getAnalysisRun(id)
      setRun(runData)

      if (runData.status === 'RUNNING' || runData.status === 'PENDING') {
        // Poll until completion
        const completedRun = await api.pollAnalysisRun(id, (updated) => setRun(updated))
        setRun(completedRun)
      }

      // Fetch issues, heuristic, and visualizations in parallel
      const [issuesRes, heuristicRes, vizRes] = await Promise.all([
        api.getAnalysisIssues(id, { limit: 100 }),
        api.getAnalysisHeuristic(id).catch(() => null),
        api.getAnalysisVisualizations(id).catch(() => null),
      ])

      setIssues(issuesRes.items || [])
      if (heuristicRes) setHeuristic(heuristicRes)
      if (vizRes) setVizData(vizRes)
    } catch (err: unknown) {
      const errObj = err as { message?: string }
      setError(errObj.message || 'Failed to load analysis findings.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (runId) {
      loadAnalysis(runId)
    } else {
      // If no runId, check recent runs from overview
      api.getOverviewStats().then((stats) => {
        if (stats.latest_analyses && stats.latest_analyses.length > 0) {
          loadAnalysis(stats.latest_analyses[0].id)
        } else {
          setIsLoading(false)
        }
      }).catch(() => setIsLoading(false))
    }
  }, [runId, loadAnalysis])

  const handleExplainIssue = async (issue: QualityIssue) => {
    if (!run) return
    setSelectedIssue(issue)
    setExplanation(null)
    setExplanationError(null)
    setIsExplaining(true)

    try {
      const exp = await api.explainFinding(run.id, issue.id)
      setExplanation(exp)
    } catch (err: unknown) {
      const errObj = err as { message?: string }
      setExplanationError(errObj.message || 'Failed to generate AI explanation.')
    } finally {
      setIsExplaining(false)
    }
  }

  if (isLoading) return <LoadingSpinner message="Loading and compiling analysis findings..." />

  if (error || !run) {
    return (
      <div className="card" style={{ borderColor: 'var(--border-default)', textAlign: 'center', padding: '36px' }}>
        <h3 style={{ fontSize: '16px', color: 'var(--text-primary)', marginBottom: '8px' }}>
          {error || 'No analysis run selected.'}
        </h3>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
          Select a dataset to trigger a deterministic analysis run.
        </p>
        <Link to="/datasets" className="btn btn-primary">
          View Datasets
        </Link>
      </div>
    )
  }

  // Count severities
  const severityCounts = {
    CRITICAL: issues.filter((i) => i.severity === 'CRITICAL').length,
    HIGH: issues.filter((i) => i.severity === 'HIGH').length,
    MEDIUM: issues.filter((i) => i.severity === 'MEDIUM').length,
    LOW: issues.filter((i) => i.severity === 'LOW').length,
    INFO: issues.filter((i) => i.severity === 'INFO').length,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Run Header Banner */}
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
              Deterministic Analysis Report
            </h1>
            <span
              className="badge font-mono"
              style={{
                backgroundColor:
                  run.status === 'COMPLETED'
                    ? 'var(--status-success-bg)'
                    : 'var(--severity-medium-bg)',
                color:
                  run.status === 'COMPLETED'
                    ? 'var(--status-success)'
                    : 'var(--severity-medium)',
              }}
            >
              {run.status}
            </span>
          </div>

          <div style={{ display: 'flex', gap: '16px', marginTop: '6px', fontSize: '12px', color: 'var(--text-muted)' }}>
            <span className="font-mono">Run: {run.id.slice(0, 8)}...</span>
            <span>Target: {run.target_column || '(None - Unsupervised)'}</span>
            <span>Problem: {run.problem_type || 'General Tabular'}</span>
            <span>Engine: v{run.engine_version}</span>
            <span>{new Date(run.created_at).toLocaleString()}</span>
          </div>
        </div>

        {/* Action button to generate or open remediation plan */}
        <Link
          to={`/remediation?runId=${run.id}`}
          className="btn btn-primary"
        >
          <Wrench size={15} />
          <span>Synthesize Remediation Plan</span>
        </Link>
      </div>

      {/* Top Analysis Summary: Score + Severity Counts Grid */}
      <div className="grid-cols-2">
        <ReadinessCard
          score={run.ml_readiness_score}
          breakdown={heuristic}
        />

        {/* Severity Count Card */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Defect Severity Hierarchy</span>
            <span className="font-mono" style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Total: {issues.length}
            </span>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, minmax(0, 1fr))', gap: '8px', marginTop: '8px' }}>
            <div
              style={{
                padding: '12px 6px',
                textAlign: 'center',
                backgroundColor: 'var(--severity-critical-bg)',
                border: '1px solid var(--severity-critical-border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--severity-critical)' }}>CRITICAL</div>
              <div className="font-mono" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--severity-critical)', marginTop: '4px' }}>
                {severityCounts.CRITICAL}
              </div>
            </div>

            <div
              style={{
                padding: '12px 6px',
                textAlign: 'center',
                backgroundColor: 'var(--severity-high-bg)',
                border: '1px solid var(--severity-high-border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--severity-high)' }}>HIGH</div>
              <div className="font-mono" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--severity-high)', marginTop: '4px' }}>
                {severityCounts.HIGH}
              </div>
            </div>

            <div
              style={{
                padding: '12px 6px',
                textAlign: 'center',
                backgroundColor: 'var(--severity-medium-bg)',
                border: '1px solid var(--severity-medium-border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--severity-medium)' }}>MEDIUM</div>
              <div className="font-mono" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--severity-medium)', marginTop: '4px' }}>
                {severityCounts.MEDIUM}
              </div>
            </div>

            <div
              style={{
                padding: '12px 6px',
                textAlign: 'center',
                backgroundColor: 'var(--severity-low-bg)',
                border: '1px solid var(--severity-low-border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--severity-low)' }}>LOW</div>
              <div className="font-mono" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--severity-low)', marginTop: '4px' }}>
                {severityCounts.LOW}
              </div>
            </div>

            <div
              style={{
                padding: '12px 6px',
                textAlign: 'center',
                backgroundColor: 'var(--severity-info-bg)',
                border: '1px solid var(--severity-info-border)',
                borderRadius: 'var(--radius-sm)',
              }}
            >
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--severity-info)' }}>INFO</div>
              <div className="font-mono" style={{ fontSize: '24px', fontWeight: 800, color: 'var(--severity-info)', marginTop: '4px' }}>
                {severityCounts.INFO}
              </div>
            </div>
          </div>

          <div style={{ marginTop: '16px', fontSize: '12px', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
            Defects are detected across the 11 deterministic analysis modules: Schema, Data Types, Missing Values,
            Duplicates, Cardinality, Outliers, Distributions, Correlations, Class Imbalance, Data Leakage, and ML Readiness.
          </div>
        </div>
      </div>

      {/* Visual Analytics Grid */}
      {vizData && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>
            Analytical Visualizations
          </h2>

          {/* Missing Values & Distribution Charts */}
          <div className="grid-cols-2">
            <div className="card">
              <div className="card-header">
                <span className="card-title">Missing Values By Column (%)</span>
              </div>
              <MissingnessChart items={vizData.missing_values} />
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">Feature Distribution & Quantiles</span>
              </div>
              <DistributionChart distributions={vizData.distributions} />
            </div>
          </div>

          {/* Correlation Heatmap & Cardinality */}
          <div className="grid-cols-2">
            <div className="card">
              <div className="card-header">
                <span className="card-title">Correlation Heatmap</span>
              </div>
              <CorrelationHeatmap correlations={vizData.correlations} />
            </div>

            <div className="card">
              <div className="card-header">
                <span className="card-title">Cardinality & Uniqueness Ratios</span>
              </div>
              <CardinalityTable items={vizData.cardinality} />
            </div>
          </div>

          {/* Class Imbalance & Leakage Signals */}
          <div className="grid-cols-2">
            <div className="card">
              <div className="card-header">
                <span className="card-title">Target Class Distribution</span>
              </div>
              <ClassDistributionChart data={vizData.class_imbalance} />
            </div>

            {/* Data Leakage Section */}
            <div className="card">
              <div className="card-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShieldAlert size={16} color="var(--severity-high)" />
                  <span className="card-title">Potential Data Leakage Risks</span>
                </div>
              </div>

              {vizData.summary?.leakage_risks && vizData.summary.leakage_risks.length > 0 ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {vizData.summary.leakage_risks.map((risk, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: '10px 12px',
                        backgroundColor: 'var(--bg-elevated)',
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '13px',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                        <span className="font-mono" style={{ fontWeight: 600, color: 'var(--text-primary)' }}>
                          {risk.column}
                        </span>
                        <span className="badge badge-high font-mono">{risk.severity}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                        {risk.detail}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
                  No target identity or suspicious leakage relationships detected.
                </div>
              )}

              <div
                style={{
                  marginTop: '16px',
                  paddingTop: '10px',
                  borderTop: '1px solid var(--border-subtle)',
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <HelpCircle size={13} style={{ flexShrink: 0 }} />
                <span>
                  Correlation and statistical signals indicate potential leakage risk; they do not prove leakage.
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Deterministic Quality Findings Table */}
      <div className="card">
        <div className="card-header">
          <span className="card-title">All Deterministic Quality Findings</span>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            Click 'Explain' on any finding for grounded AI contextualization
          </span>
        </div>

        <IssueTable
          issues={issues}
          onExplainIssue={handleExplainIssue}
        />
      </div>

      {/* AI Explanation Modal */}
      <AIExplanationModal
        isOpen={Boolean(selectedIssue)}
        onClose={() => setSelectedIssue(null)}
        issue={selectedIssue}
        explanation={explanation}
        isLoading={isExplaining}
        error={explanationError}
      />
    </div>
  )
}
