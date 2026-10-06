export interface ColumnSchemaItem {
  name: string
  dtype: string
}

export interface RawSchema {
  columns: ColumnSchemaItem[]
}

export interface DatasetVersion {
  id: string
  dataset_id: string
  parent_version_id?: string | null
  version_number: number
  change_summary?: string | null
  file_name: string
  file_size_bytes: number
  sha256_hash: string
  row_count: number
  column_count: number
  raw_schema: {
    columns?: ColumnSchemaItem[]
    [key: string]: unknown
  }
  created_at: string
}

export interface Dataset {
  id: string
  name: string
  description?: string | null
  created_at: string
  updated_at: string
  versions: DatasetVersion[]
}

export interface DatasetListItem {
  dataset_id: string
  name: string
  description?: string | null
  latest_version_number: number
  latest_row_count: number
  latest_column_count: number
  created_at: string
  updated_at: string
  // UI enrichment
  latest_readiness_score?: number | null
  latest_analysis_status?: string | null
}

export interface DatasetUploadResponse {
  dataset_id: string
  version_id: string
  version_number: number
  file_name: string
  row_count: number
  column_count: number
  storage_format: string
  status: string
}

export interface DatasetPreviewResponse {
  dataset_id: string
  version_number: number
  total_rows: number
  total_columns: number
  file_size_bytes: number
  columns: string[]
  dtypes: Record<string, string>
  rows: Array<Record<string, unknown>>
  limit: number
  offset: number
}
