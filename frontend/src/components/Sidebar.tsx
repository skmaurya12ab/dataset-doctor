import React from 'react'
import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Database,
  BarChart3,
  Wrench,
  GitBranch,
  Settings,
  ActivitySquare,
} from 'lucide-react'

export const Sidebar: React.FC = () => {
  const navItems = [
    { to: '/', label: 'Overview', icon: LayoutDashboard },
    { to: '/datasets', label: 'Datasets', icon: Database },
    { to: '/analysis', label: 'Analysis', icon: BarChart3 },
    { to: '/remediation', label: 'Remediation', icon: Wrench },
    { to: '/versions', label: 'Versions', icon: GitBranch },
  ]

  return (
    <aside className="sidebar">
      {/* Brand Header */}
      <div
        style={{
          height: '56px',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          padding: '0 20px',
          borderBottom: '1px solid var(--border-subtle)',
        }}
      >
        <ActivitySquare size={20} color="var(--accent-primary)" />
        <span
          className="logo-text"
          style={{
            fontSize: '15px',
            fontWeight: 700,
            letterSpacing: '-0.02em',
            color: 'var(--text-primary)',
          }}
        >
          Dataset Doctor
        </span>
      </div>

      {/* Main Nav */}
      <nav
        style={{
          flex: 1,
          padding: '16px 12px',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '8px 12px',
                borderRadius: 'var(--radius-sm)',
                fontSize: '13px',
                fontWeight: isActive ? 600 : 500,
                color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                backgroundColor: isActive ? 'var(--bg-elevated)' : 'transparent',
                borderLeft: isActive ? '3px solid var(--accent-primary)' : '3px solid transparent',
                textDecoration: 'none',
                transition: 'all 0.15s ease',
              })}
            >
              <Icon size={16} />
              <span className="nav-label">{item.label}</span>
            </NavLink>
          )
        })}
      </nav>

      {/* Bottom Utility: Settings */}
      <div
        style={{
          padding: '12px',
          borderTop: '1px solid var(--border-subtle)',
        }}
      >
        <NavLink
          to="/settings"
          style={({ isActive }) => ({
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            padding: '8px 12px',
            borderRadius: 'var(--radius-sm)',
            fontSize: '13px',
            fontWeight: isActive ? 600 : 500,
            color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
            backgroundColor: isActive ? 'var(--bg-elevated)' : 'transparent',
            textDecoration: 'none',
          })}
        >
          <Settings size={16} />
          <span className="nav-label">Settings</span>
        </NavLink>
      </div>
    </aside>
  )
}
