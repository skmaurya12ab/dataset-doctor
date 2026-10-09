import React, { useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { Header } from './Header'
import { UploadModal } from './UploadModal'
import { ErrorBoundary } from './ErrorBoundary'
import type { DatasetUploadResponse } from '../types/dataset'

export const Layout: React.FC = () => {
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const navigate = useNavigate()

  const handleUploadSuccess = (uploaded: DatasetUploadResponse) => {
    navigate(`/datasets/${uploaded.dataset_id}`)
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <div className="main-wrapper">
        <Header onOpenUpload={() => setIsUploadOpen(true)} />
        <main className="page-content" role="main">
          <ErrorBoundary>
            <Outlet context={{ openUpload: () => setIsUploadOpen(true) }} />
          </ErrorBoundary>
        </main>
      </div>

      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onSuccess={handleUploadSuccess}
      />
    </div>
  )
}
