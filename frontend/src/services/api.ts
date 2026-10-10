import axios from 'axios'
import type {
  Dataset,
  DatasetListItem,
  DatasetPreviewResponse,
  DatasetUploadResponse,
  DatasetVersion,
} from '../types/dataset'
import type {
  AnalysisRun,
  HeuristicBreakdown,
  OverviewStats,
  QualityIssueListResponse,
  VisualizationData,
} from '../types/analysis'
import type { AIReport, FindingExplanationResponse } from '../types/ai'
import type {
  RemediationApplyRequest,
  RemediationExecution,
  VersionComparison,
} from '../types/remediation'
import { normalizeAIReport } from '../utils/aiReport'
import { normalizeVersionComparison } from '../utils/versionComparison'
export { normalizeAIReport, normalizeVersionComparison }

import type {
  User,
  LoginResponse,
  RegisterRequest,
  LoginRequest,
  VerifyEmailRequest,
  ForgotPasswordRequest,
  ResetPasswordRequest,
  MessageResponse,
} from '../types/auth'

const apiClient = axios.create({
  baseURL: '/api/v1',
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
})

export const api = {
  // --- Overview & Dashboard ---
  async getOverviewStats(): Promise<OverviewStats> {
    const response = await apiClient.get<OverviewStats>('/overview/stats')
    return response.data
  },

  // --- Datasets ---
  async listDatasets(params?: {
    skip?: number
    limit?: number
    search?: string
  }): Promise<DatasetListItem[]> {
    const response = await apiClient.get<DatasetListItem[]>('/datasets', {
      params,
    })
    return response.data
  },

  async getDataset(id: string): Promise<Dataset> {
    const response = await apiClient.get<Dataset>(`/datasets/${id}`)
    return response.data
  },

  async getDatasetVersion(
    datasetId: string,
    versionId: string,
  ): Promise<DatasetVersion> {
    const response = await apiClient.get<DatasetVersion>(
      `/datasets/${datasetId}/versions/${versionId}`,
    )
    return response.data
  },

  async previewDatasetVersion(
    datasetId: string,
    versionNumber: number,
    limit = 10,
    offset = 0,
  ): Promise<DatasetPreviewResponse> {
    const response = await apiClient.get<DatasetPreviewResponse>(
      `/datasets/${datasetId}/versions/${versionNumber}/preview`,
      { params: { limit, offset } },
    )
    return response.data
  },

  async uploadDataset(formData: FormData): Promise<DatasetUploadResponse> {
    const response = await apiClient.post<DatasetUploadResponse>(
      '/datasets/upload',
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    )
    return response.data
  },

  async uploadNewVersion(
    datasetId: string,
    formData: FormData,
  ): Promise<DatasetUploadResponse> {
    const response = await apiClient.post<DatasetUploadResponse>(
      `/datasets/${datasetId}/versions`,
      formData,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
      },
    )
    return response.data
  },

  // --- Analyses ---
  async triggerAnalysis(
    datasetId: string,
    versionId: string,
    payload?: {
      target_column?: string
      problem_type?: string
      parameters?: Record<string, unknown>
    },
  ): Promise<{ analysis_run_id: string; status: string }> {
    const response = await apiClient.post<{
      analysis_run_id: string
      status: string
    }>(`/datasets/${datasetId}/versions/${versionId}/analyze`, payload || {})
    return response.data
  },

  async getAnalysisRun(runId: string): Promise<AnalysisRun> {
    const response = await apiClient.get<AnalysisRun>(`/analyses/${runId}`)
    return response.data
  },

  async getAnalysisIssues(
    runId: string,
    params?: {
      skip?: number
      limit?: number
      module?: string
      severity?: string
    },
  ): Promise<QualityIssueListResponse> {
    const response = await apiClient.get<QualityIssueListResponse>(
      `/analyses/${runId}/issues`,
      { params },
    )
    return response.data
  },

  async getAnalysisHeuristic(runId: string): Promise<HeuristicBreakdown> {
    const response = await apiClient.get<HeuristicBreakdown>(
      `/analyses/${runId}/heuristic`,
    )
    return response.data
  },

  async listVersionAnalyses(
    datasetId: string,
    versionId: string,
  ): Promise<AnalysisRun[]> {
    const response = await apiClient.get<AnalysisRun[]>(
      `/datasets/${datasetId}/versions/${versionId}/analyses`,
    )
    return response.data
  },

  async getAnalysisVisualizations(runId: string): Promise<VisualizationData> {
    const response = await apiClient.get<VisualizationData>(
      `/analyses/${runId}/visualizations`,
    )
    return response.data
  },

  // --- Async Analysis Poller ---
  async pollAnalysisRun(
    runId: string,
    onProgress?: (run: AnalysisRun) => void,
    intervalMs = 1500,
    maxAttempts = 40,
  ): Promise<AnalysisRun> {
    let attempts = 0
    while (attempts < maxAttempts) {
      const run = await this.getAnalysisRun(runId)
      if (onProgress) onProgress(run)

      if (run.status === 'COMPLETED' || run.status === 'FAILED') {
        return run
      }

      attempts++
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
    throw new Error(
      `Analysis ${runId} timed out after ${maxAttempts * (intervalMs / 1000)}s`,
    )
  },

  // --- AI Explanations & Reports ---
  async explainFinding(
    runId: string,
    issueId: string,
  ): Promise<FindingExplanationResponse> {
    const response = await apiClient.post<FindingExplanationResponse>(
      `/analyses/${runId}/issues/${issueId}/explain`,
    )
    return response.data
  },

  async getAIPlan(runId: string): Promise<AIReport> {
    const response = await apiClient.get<any>(`/analyses/${runId}/ai-plan`)
    return normalizeAIReport(response.data)
  },

  async generateAIPlan(
    runId: string,
    forceRegenerate = false,
  ): Promise<AIReport> {
    const response = await apiClient.post<any>(
      `/analyses/${runId}/generate-ai-plan?force_regenerate=${forceRegenerate}`,
      {},
    )
    return normalizeAIReport(response.data)
  },

  // --- Remediation & Comparison ---
  async applyRemediation(
    runId: string,
    payload: RemediationApplyRequest,
  ): Promise<RemediationExecution> {
    const response = await apiClient.post<RemediationExecution>(
      `/analyses/${runId}/remediations/apply`,
      payload,
    )
    return response.data
  },

  async getRemediationExecution(
    executionId: string,
  ): Promise<RemediationExecution> {
    const response = await apiClient.get<RemediationExecution>(
      `/remediations/${executionId}`,
    )
    return response.data
  },

  async listDatasetRemediations(
    datasetId: string,
  ): Promise<RemediationExecution[]> {
    const response = await apiClient.get<{
      items: RemediationExecution[]
      total: number
    }>(`/datasets/${datasetId}/remediations`)
    return response.data.items || []
  },

  async compareVersions(
    datasetId: string,
    v1: string,
    v2: string,
  ): Promise<VersionComparison> {
    const response = await apiClient.get<VersionComparison>(
      `/datasets/${datasetId}/compare-versions`,
      {
        params: { v1, v2 },
      },
    )
    return normalizeVersionComparison(response.data)
  },


  async pollRemediationExecution(
    executionId: string,
    onProgress?: (execution: RemediationExecution) => void,
    intervalMs = 1500,
    maxAttempts = 40,
  ): Promise<RemediationExecution> {
    let attempts = 0
    while (attempts < maxAttempts) {
      const execution = await this.getRemediationExecution(executionId)
      if (onProgress) onProgress(execution)

      if (execution.status === 'COMPLETED' || execution.status === 'FAILED') {
        return execution
      }

      attempts++
      await new Promise((resolve) => setTimeout(resolve, intervalMs))
    }
    throw new Error(
      `Remediation ${executionId} timed out after ${maxAttempts * (intervalMs / 1000)}s`,
    )
  },

  // --- Authentication ---
  async register(payload: RegisterRequest): Promise<User> {
    const response = await apiClient.post<User>('/auth/register', payload)
    return response.data
  },

  async login(payload: LoginRequest): Promise<LoginResponse> {
    const response = await apiClient.post<LoginResponse>('/auth/login', payload)
    return response.data
  },

  async logout(): Promise<MessageResponse> {
    const response = await apiClient.post<MessageResponse>('/auth/logout')
    return response.data
  },

  async getCurrentUser(): Promise<User> {
    const response = await apiClient.get<User>('/auth/me')
    return response.data
  },

  async verifyEmail(payload: VerifyEmailRequest): Promise<MessageResponse> {
    const response = await apiClient.post<MessageResponse>('/auth/verify-email', payload)
    return response.data
  },

  async forgotPassword(payload: ForgotPasswordRequest): Promise<MessageResponse> {
    const response = await apiClient.post<MessageResponse>('/auth/forgot-password', payload)
    return response.data
  },

  async resetPassword(payload: ResetPasswordRequest): Promise<MessageResponse> {
    const response = await apiClient.post<MessageResponse>('/auth/reset-password', payload)
    return response.data
  },
}
