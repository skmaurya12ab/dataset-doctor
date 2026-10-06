import React from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { OverviewPage } from './pages/OverviewPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { DatasetDetailPage } from './pages/DatasetDetailPage'
import { VersionDetailPage } from './pages/VersionDetailPage'
import { AnalysisPage } from './pages/AnalysisPage'
import { RemediationPage } from './pages/RemediationPage'
import { ComparisonPage } from './pages/ComparisonPage'
import { SettingsPage } from './pages/SettingsPage'

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<OverviewPage />} />
          <Route path="datasets" element={<DatasetsPage />} />
          <Route path="datasets/:id" element={<DatasetDetailPage />} />
          <Route
            path="datasets/:datasetId/versions/:versionId"
            element={<VersionDetailPage />}
          />
          <Route path="analysis" element={<AnalysisPage />} />
          <Route path="remediation" element={<RemediationPage />} />
          <Route path="versions" element={<ComparisonPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
