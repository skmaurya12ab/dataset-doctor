import React from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AuthProvider } from './context/AuthContext'
import { ProtectedRoute } from './components/ProtectedRoute'
import { Layout } from './components/Layout'
import { OverviewPage } from './pages/OverviewPage'
import { DatasetsPage } from './pages/DatasetsPage'
import { DatasetDetailPage } from './pages/DatasetDetailPage'
import { VersionDetailPage } from './pages/VersionDetailPage'
import { AnalysisPage } from './pages/AnalysisPage'
import { RemediationPage } from './pages/RemediationPage'
import { ComparisonPage } from './pages/ComparisonPage'
import { SettingsPage } from './pages/SettingsPage'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { VerifyEmailPage } from './pages/VerifyEmailPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { ResetPasswordPage } from './pages/ResetPasswordPage'

const RemediationsRedirect: React.FC = () => {
  const location = useLocation()
  return <Navigate to={{ pathname: '/remediation', search: location.search }} replace />
}

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public Authentication Routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          {/* Protected Application Routes */}
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <Layout />
              </ProtectedRoute>
            }
          >
            <Route index element={<OverviewPage />} />
            <Route path="datasets" element={<DatasetsPage />} />
            <Route path="datasets/:id" element={<DatasetDetailPage />} />
            <Route
              path="datasets/:datasetId/versions/:versionId"
              element={<VersionDetailPage />}
            />
            <Route path="analysis" element={<AnalysisPage />} />
            <Route path="remediation" element={<RemediationPage />} />
            <Route path="remediations" element={<RemediationsRedirect />} />
            <Route path="versions" element={<ComparisonPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
