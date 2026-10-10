import React from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ChevronRight, UploadCloud, Server, LogOut, User as UserIcon } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

interface HeaderProps {
  onOpenUpload?: () => void
}

export const Header: React.FC<HeaderProps> = ({ onOpenUpload }) => {
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const pathParts = location.pathname.split('/').filter(Boolean)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

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

        {user && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              borderLeft: '1px solid var(--border-subtle)',
              paddingLeft: '14px',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                fontSize: '12px',
                color: 'var(--text-primary)',
              }}
            >
              <div
                style={{
                  width: '26px',
                  height: '26px',
                  borderRadius: '50%',
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent-primary)',
                }}
              >
                <UserIcon size={14} />
              </div>
              <span style={{ maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user.email}
              </span>
              {!user.is_verified && (
                <Link
                  to="/verify-email"
                  style={{
                    fontSize: '10px',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    background: '#f59e0b20',
                    color: '#f59e0b',
                    border: '1px solid #f59e0b40',
                    textDecoration: 'none',
                    fontWeight: 600,
                  }}
                >
                  Unverified
                </Link>
              )}
            </div>

            <button
              onClick={handleLogout}
              title="Sign Out"
              aria-label="Sign Out"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--text-muted)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                padding: '4px',
                borderRadius: '4px',
                transition: 'color 0.15s ease',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = '#f43f5e')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--text-muted)')}
            >
              <LogOut size={16} />
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
