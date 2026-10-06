import React from 'react'
import {
  Clock,
  CheckCircle2,
  AlertTriangle,
  PlayCircle,
  XCircle,
} from 'lucide-react'
import type { RemediationStatus } from '../types/remediation'

interface RemediationStatusBadgeProps {
  status: RemediationStatus | string
}

export const RemediationStatusBadge: React.FC<RemediationStatusBadgeProps> = ({
  status,
}) => {
  const normalized = status.toUpperCase() as RemediationStatus

  let badgeColor = 'var(--text-secondary)'
  let bgColor = 'var(--bg-elevated)'
  let borderColor = 'var(--border-default)'
  let IconComponent = Clock
  let label = status

  switch (normalized) {
    case 'PENDING_APPROVAL':
      badgeColor = 'var(--severity-medium)'
      bgColor = 'var(--severity-medium-bg)'
      borderColor = 'var(--severity-medium-border)'
      IconComponent = Clock
      label = 'Pending Approval'
      break
    case 'APPROVED':
      badgeColor = 'var(--severity-low)'
      bgColor = 'var(--severity-low-bg)'
      borderColor = 'var(--severity-low-border)'
      IconComponent = CheckCircle2
      label = 'Approved'
      break
    case 'VALIDATING':
    case 'RUNNING':
      badgeColor = 'var(--accent-primary)'
      bgColor = 'var(--accent-subtle)'
      borderColor = 'var(--accent-primary)'
      IconComponent = PlayCircle
      label = 'Applying Transformations...'
      break
    case 'COMPLETED':
      badgeColor = 'var(--status-success)'
      bgColor = 'var(--status-success-bg)'
      borderColor = 'var(--status-success-border)'
      IconComponent = CheckCircle2
      label = 'Completed'
      break
    case 'FAILED':
      badgeColor = 'var(--severity-critical)'
      bgColor = 'var(--severity-critical-bg)'
      borderColor = 'var(--severity-critical-border)'
      IconComponent = AlertTriangle
      label = 'Failed (Data Preserved)'
      break
    case 'REJECTED':
      badgeColor = 'var(--severity-info)'
      bgColor = 'var(--severity-info-bg)'
      borderColor = 'var(--severity-info-border)'
      IconComponent = XCircle
      label = 'Rejected'
      break
  }

  return (
    <span
      className="badge font-mono"
      style={{
        backgroundColor: bgColor,
        color: badgeColor,
        borderColor: borderColor,
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        padding: '3px 10px',
      }}
    >
      <IconComponent size={13} />
      <span>{label}</span>
    </span>
  )
}
