import React from 'react'

interface LoadingSpinnerProps {
  message?: string
  size?: number
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({
  message = 'Loading data...',
  size = 24,
}) => {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '36px',
        gap: '12px',
        color: 'var(--text-secondary)',
      }}
    >
      <div
        style={{
          width: `${size}px`,
          height: `${size}px`,
          border: '2px solid var(--border-default)',
          borderTopColor: 'var(--accent-primary)',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }}
      />
      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      {message && <span style={{ fontSize: '13px' }}>{message}</span>}
    </div>
  )
}
