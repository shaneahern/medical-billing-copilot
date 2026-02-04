import { apiClient } from './client';

// Types
export interface IngestionJob {
  job_id: string;
  source: 'CMS_GOV' | 'COMMERCIAL_PAYER';
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'PARTIAL';
  started_at: string;
  completed_at?: string;
  documents_processed: number;
  documents_failed: number;
  error_message?: string;
  details?: Record<string, unknown>;
}

export interface IngestionStats {
  total_jobs: number;
  completed_jobs: number;
  failed_jobs: number;
  partial_jobs: number;
  running_jobs: number;
  total_documents_processed: number;
  total_documents_failed: number;
  scheduler_running: boolean;
  log_entries: number;
}

export interface IngestionLog {
  id: string;
  job_id: string;
  timestamp: string;
  level: string;
  message: string;
  document_id?: string;
}

export interface PayerSupport {
  payer_id: string;
  payer_name: string;
  is_supported: boolean;
  document_count: number;
  last_updated?: string;
  coverage_areas: string[];
  message?: string;
}

export interface PolicyFreshness {
  source: string;
  source_type: string;
  last_updated?: string;
  document_count: number;
  is_fresh: boolean;
  freshness_threshold_days: number;
  days_since_update?: number;
}

export interface PolicyDatabaseStats {
  total_documents: number;
  medicare_lcd_count: number;
  medicare_ncd_count: number;
  commercial_policy_count: number;
  mac_regions_covered: string[];
  payers_supported: string[];
  last_full_ingestion?: string;
  overall_freshness: boolean;
}

export interface MACRegionCoverage {
  mac_region: string;
  mac_name: string;
  document_count: number;
  is_covered: boolean;
  jurisdictions: string[];
}

export interface CommercialPayer {
  id: string;
  name: string;
  scrape_method: string;
}

// API Functions
export async function getIngestionStats(): Promise<IngestionStats> {
  const response = await apiClient.get('/ingestion/stats');
  return response.data;
}

export async function getPolicyDatabaseStats(): Promise<PolicyDatabaseStats> {
  const response = await apiClient.get('/ingestion/policy/stats');
  return response.data;
}

export async function getSupportedPayers(): Promise<PayerSupport[]> {
  const response = await apiClient.get('/ingestion/policy/payers/supported');
  return response.data;
}

export async function getCommercialPayers(): Promise<CommercialPayer[]> {
  const response = await apiClient.get('/ingestion/payers');
  return response.data.payers;
}

export async function getMACRegions(): Promise<{ mac_regions: MACRegionCoverage[]; total_regions: number }> {
  const response = await apiClient.get('/ingestion/policy/mac-regions');
  return response.data;
}

export async function getPolicyFreshness(source: string): Promise<PolicyFreshness> {
  const response = await apiClient.get(`/ingestion/policy/freshness/${source}`);
  return response.data;
}

export async function getIngestionJobs(limit = 50): Promise<IngestionJob[]> {
  const response = await apiClient.get('/ingestion/jobs', { params: { limit } });
  return response.data;
}

export async function getRunningJobs(): Promise<IngestionJob[]> {
  const response = await apiClient.get('/ingestion/jobs/running');
  return response.data;
}

export async function getIngestionLogs(jobId?: string, limit = 100): Promise<IngestionLog[]> {
  const response = await apiClient.get('/ingestion/logs', {
    params: { job_id: jobId, limit },
  });
  return response.data;
}

export async function triggerCMSIngestion(
  macRegions?: string[],
  documentType?: 'LCD' | 'NCD'
): Promise<IngestionJob> {
  const response = await apiClient.post('/ingestion/trigger/cms', {
    mac_regions: macRegions,
    document_type: documentType,
  });
  return response.data;
}

export async function triggerCommercialIngestion(
  payerIds?: string[],
  limitPerPayer = 100
): Promise<IngestionJob> {
  const response = await apiClient.post('/ingestion/trigger/commercial', {
    payer_ids: payerIds,
    limit_per_payer: limitPerPayer,
  });
  return response.data;
}

export async function triggerFullIngestion(): Promise<IngestionJob[]> {
  const response = await apiClient.post('/ingestion/trigger/full');
  return response.data;
}

export async function getSchedulerStatus(): Promise<{ running: boolean }> {
  const response = await apiClient.get('/ingestion/scheduler/status');
  return response.data;
}

export async function startScheduler(intervalHours = 24, runImmediately = false): Promise<void> {
  await apiClient.post('/ingestion/scheduler/start', {
    interval_hours: intervalHours,
    run_immediately: runImmediately,
  });
}

export async function stopScheduler(): Promise<void> {
  await apiClient.post('/ingestion/scheduler/stop');
}


// Custom Document Types
export interface CustomDocumentRequest {
  title: string;
  content: string;
  source_type: 'LCD' | 'NCD' | 'COMMERCIAL' | 'CARC';
  payer?: string;
  mac_region?: string;
  source_url?: string;
  effective_date?: string;
}

export interface CustomDocumentResponse {
  success: boolean;
  document_id: string;
  message: string;
}

export async function addCustomDocument(doc: CustomDocumentRequest): Promise<CustomDocumentResponse> {
  const response = await apiClient.post('/ingestion/documents/custom', doc);
  return response.data;
}
