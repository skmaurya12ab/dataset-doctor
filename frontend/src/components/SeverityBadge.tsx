import React from 'react'
import {
  AlertCircle,
  AlertTriangle,
  Info,
  ShieldAlert,
  HelpCircle,
} from 'lucide-react'
import type { IssueSeverity } from '../types/analysis'

interface SeverityBadgeProps {
  severity: IssueSeverity | string
  className?: string
  showIcon?: boolean
}

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({
  severity,
  className = '',
  showIcon = true,
}) => {
  const normalized = severity.toUpperCase() as IssueSeverity

  let badgeClass = 'badge-info'
  let IconComponent = Info

  switch (normalized) {
    case 'CRITICAL':
      badgeClass = 'badge-critical'
      IconComponent = ShieldAlert
      break
    case 'HIGH':
      badgeClass = 'badge-high'
      IconComponent = AlertCircle
      break
    case 'MEDIUM':
      badgeClass = 'badge-medium'
      IconComponent = AlertTriangle
      break
    case 'LOW':
      badgeClass = 'badge-low'
      IconComponent = Info
      break
    case 'INFO':
    default:
      badgeClass = 'badge-info'
      IconComponent = HelpCircle
      break
  }

  return (
    <span
      className={`badge ${badgeClass} ${className}`}
      role="status"
      aria-label={`Severity: ${normalized}`}
    >
      {showIcon && <IconComponent size={12} aria-hidden="true" />}
      <span>{normalized}</span>
    </span>
  )
}
