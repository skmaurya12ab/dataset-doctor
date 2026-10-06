import React from 'react'
import { Shield, Lock } from 'lucide-react'

export const SettingsPage: React.FC = () => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div>
        <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>
          Settings & System Architecture
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '2px' }}>
          Runtime configuration, deterministic safety boundaries, and transformation constraints.
        </p>
      </div>

      <div className="grid-cols-2">
        {/* Core Principles */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Shield size={16} color="var(--status-success)" />
              <span className="card-title">Architectural Principles</span>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
            <div style={{ padding: '8px 10px', backgroundColor: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)' }}>
              <strong>1. AI Proposes, Human Approves, Python Executes</strong>
              <div style={{ color: 'var(--text-secondary)', fontSize: '12px', marginTop: '2px' }}>
                LLMs never compute statistics or execute code. All numeric calculations and data mutations occur deterministically in Python.
              </div>
            </div>
            <div style={{ padding: '8px 10px', backgroundColor: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)' }}>
              <strong>2. Immutable Versioning</strong>
              <div style={{ color: 'var(--text-secondary)', fontSize: '12px', marginTop: '2px' }}>
                Source versions are never modified in place. Every approved remediation produces a new, cryptographic SHA-256 version snapshot.
              </div>
            </div>
            <div style={{ padding: '8px 10px', backgroundColor: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)' }}>
              <strong>3. Raw Data Protection</strong>
              <div style={{ color: 'var(--text-secondary)', fontSize: '12px', marginTop: '2px' }}>
                Raw datasets are never streamed in bulk to the browser. Only bounded previews and aggregated chart statistics are transferred.
              </div>
            </div>
          </div>
        </div>

        {/* Security & Endpoints */}
        <div className="card">
          <div className="card-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Lock size={16} color="var(--accent-primary)" />
              <span className="card-title">Security Boundaries</span>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Backend API:</span>
              <span className="font-mono" style={{ color: 'var(--accent-primary)' }}>/api/v1</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>LLM API Key Location:</span>
              <span className="font-mono" style={{ color: 'var(--status-success)' }}>Backend Server Only</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--border-subtle)' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Allowed Formats:</span>
              <span className="font-mono">CSV, XLSX, JSON, Parquet</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}>
              <span style={{ color: 'var(--text-secondary)' }}>Allowlisted Actions:</span>
              <span className="font-mono" style={{ color: 'var(--text-primary)', fontSize: '12px' }}>
                DROP_COLUMN, REMOVE_DUPLICATES, IMPUTE, CAST_TYPE, CLIP_OUTLIERS
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
