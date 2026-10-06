import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ChevronRight, UploadCloud, Server } from 'lucide-react'

interface HeaderProps {
  onOpenUpload?: () => void
}

export const Header: React.FC<HeaderProps> = ({ onOpenUpload }) => {
  const location = useLocation()
  const pathParts = location.pathname.split('/').filter(Boolean)

  return (
    <header className="top-header">
      {/* Breadcrumb Context */}
      <nav aria-label="Breadcrumb" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}>
        <Link
          to="/"
          style={{
            color: 'var(--text-secondary)',
            textDecoration: 'none',
          }}
        >
          App
        </Link>
        {pathParts.length === 0 && (
          <>
            <ChevronRight size={12} color="var(--text-muted)" />
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Overview</span>
          </>
        )}
        {pathParts.map((part, index) => {
          const isLast = index === pathParts.length - 1
          const url = `/${pathParts.slice(0, index + 1).join('/')}`
          const displayName = part.charAt(0).toUpperCase() + part.slice(1).replace(/-/g, ' ')

          return (
            <React.Fragment key={url}>
              <ChevronRight size={12} color="var(--text-muted)" />
              {isLast ? (
                <span
                  style={{
                    color: 'var(--text-primary)',
                    fontWeight: 600,
                    maxWidth: '240px',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {displayName}
                </span>
              ) : (
                <Link
                  to={url}
                  style={{
                    color: 'var(--text-secondary)',
                    textDecoration: 'none',
                  }}
                >
                  {displayName}
                </Link>
              )}
            </React.Fragment>
          )
        })}
      </nav>

      {/* Right Actions & Health Status */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '11px',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          <Server size={12} color="var(--status-success)" />
          <span>v1.0.0</span>
        </div>

        {onOpenUpload && (
          <button className="btn btn-primary btn-sm" onClick={onOpenUpload}>
            <UploadCloud size={14} />
            <span>Upload Dataset</span>
          </button>
        )}
      </div>
    </header>
  )
}
