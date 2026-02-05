import { useState, useEffect, useCallback } from 'react';
import {
  getIngestionStats,
  getPolicyDatabaseStats,
  getSupportedPayers,
  getMACRegions,
  getIngestionJobs,
  getRunningJobs,
  triggerCMSIngestion,
  triggerCommercialIngestion,
  triggerFullIngestion,
  getSchedulerStatus,
  startScheduler,
  stopScheduler,
  addCustomDocument,
  getPayerDocuments,
  getMACRegionDocuments,
  getCMSDataSources,
  triggerCMSBulkDownload,
  triggerCMSAPISync,
  triggerCMSIncrementalUpdate,
  getDocumentDetail,
  IngestionStats,
  PolicyDatabaseStats,
  PayerSupport,
  MACRegionCoverage,
  IngestionJob,
  CustomDocumentRequest,
  DocumentInfo,
  DocumentDetail,
  CMSDataSourcesResponse,
} from '../api/ingestion';

// Stats Card Component
function StatsCard({ title, value, subtitle, color = 'blue' }: {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'purple';
}) {
  const colorClasses = {
    blue: 'bg-blue-50 border-blue-200 text-blue-700',
    green: 'bg-green-50 border-green-200 text-green-700',
    yellow: 'bg-yellow-50 border-yellow-200 text-yellow-700',
    red: 'bg-red-50 border-red-200 text-red-700',
    purple: 'bg-purple-50 border-purple-200 text-purple-700',
  };

  return (
    <div className={`rounded-lg border p-4 ${colorClasses[color]}`}>
      <div className="text-sm font-medium opacity-75">{title}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
      {subtitle && <div className="text-xs mt-1 opacity-60">{subtitle}</div>}
    </div>
  );
}

// Status Badge Component
function StatusBadge({ status }: { status: string }) {
  const statusColors: Record<string, string> = {
    COMPLETED: 'bg-green-100 text-green-800',
    RUNNING: 'bg-blue-100 text-blue-800',
    PENDING: 'bg-gray-100 text-gray-800',
    FAILED: 'bg-red-100 text-red-800',
    PARTIAL: 'bg-yellow-100 text-yellow-800',
  };

  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${statusColors[status] || 'bg-gray-100'}`}>
      {status}
    </span>
  );
}

// Freshness Badge Component (exported for potential future use)
export function FreshnessBadge({ isFresh, daysSinceUpdate }: { isFresh: boolean; daysSinceUpdate?: number }) {
  if (isFresh) {
    return (
      <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
        Fresh {daysSinceUpdate !== undefined && `(${daysSinceUpdate}d ago)`}
      </span>
    );
  }
  return (
    <span className="px-2 py-1 rounded-full text-xs font-medium bg-red-100 text-red-800">
      Stale {daysSinceUpdate !== undefined && `(${daysSinceUpdate}d ago)`}
    </span>
  );
}

export function DashboardPage() {
  const [ingestionStats, setIngestionStats] = useState<IngestionStats | null>(null);
  const [policyStats, setPolicyStats] = useState<PolicyDatabaseStats | null>(null);
  const [payers, setPayers] = useState<PayerSupport[]>([]);
  const [macRegions, setMACRegions] = useState<MACRegionCoverage[]>([]);
  const [jobs, setJobs] = useState<IngestionJob[]>([]);
  const [runningJobs, setRunningJobs] = useState<IngestionJob[]>([]);
  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Custom document form state
  const [showAddDocForm, setShowAddDocForm] = useState(false);
  const [customDoc, setCustomDoc] = useState<CustomDocumentRequest>({
    title: '',
    content: '',
    source_type: 'COMMERCIAL',
    payer: '',
    mac_region: '',
    source_url: '',
    effective_date: '',
  });

  // Document viewer modal state
  const [showDocumentsModal, setShowDocumentsModal] = useState(false);
  const [documentsModalTitle, setDocumentsModalTitle] = useState('');
  const [documentsModalData, setDocumentsModalData] = useState<DocumentInfo[]>([]);
  const [documentsLoading, setDocumentsLoading] = useState(false);

  // CMS data source state
  const [cmsDataSources, setCMSDataSources] = useState<CMSDataSourcesResponse | null>(null);
  const [showCMSOptions, setShowCMSOptions] = useState(false);
  const [incrementalDays, setIncrementalDays] = useState(7);

  // Document detail modal state
  const [showDocumentDetail, setShowDocumentDetail] = useState(false);
  const [documentDetail, setDocumentDetail] = useState<DocumentDetail | null>(null);
  const [documentDetailLoading, setDocumentDetailLoading] = useState(false);

  const handleViewDocumentDetail = async (documentId: string) => {
    setShowDocumentDetail(true);
    setDocumentDetailLoading(true);
    try {
      const detail = await getDocumentDetail(documentId);
      setDocumentDetail(detail);
    } catch (err) {
      console.error('Failed to load document detail:', err);
      setDocumentDetail(null);
    } finally {
      setDocumentDetailLoading(false);
    }
  };

  const handleViewPayerDocuments = async (payerId: string, payerName: string) => {
    setDocumentsModalTitle(`${payerName} Documents`);
    setShowDocumentsModal(true);
    setDocumentsLoading(true);
    try {
      const docs = await getPayerDocuments(payerId);
      setDocumentsModalData(docs);
    } catch (err) {
      console.error('Failed to load documents:', err);
      setDocumentsModalData([]);
    } finally {
      setDocumentsLoading(false);
    }
  };

  const handleViewMACRegionDocuments = async (macRegion: string, macName: string) => {
    setDocumentsModalTitle(`${macName} (${macRegion}) Documents`);
    setShowDocumentsModal(true);
    setDocumentsLoading(true);
    try {
      const docs = await getMACRegionDocuments(macRegion);
      setDocumentsModalData(docs);
    } catch (err) {
      console.error('Failed to load documents:', err);
      setDocumentsModalData([]);
    } finally {
      setDocumentsLoading(false);
    }
  };

  const loadData = useCallback(async () => {
    try {
      setError(null);
      const [stats, policy, payerList, regions, jobList, running, scheduler, cmsSources] = await Promise.all([
        getIngestionStats(),
        getPolicyDatabaseStats(),
        getSupportedPayers(),
        getMACRegions(),
        getIngestionJobs(20),
        getRunningJobs(),
        getSchedulerStatus(),
        getCMSDataSources().catch(() => null),
      ]);
      setIngestionStats(stats);
      setPolicyStats(policy);
      setPayers(payerList);
      setMACRegions(regions.mac_regions);
      setJobs(jobList);
      setRunningJobs(running);
      setSchedulerRunning(scheduler.running);
      setCMSDataSources(cmsSources);
    } catch (err) {
      setError('Failed to load dashboard data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    // Refresh every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleTriggerCMS = async (docType?: 'LCD' | 'NCD') => {
    setActionLoading('cms');
    try {
      await triggerCMSIngestion(undefined, docType);
      setSuccessMessage('CMS ingestion started');
      await loadData();
    } catch (err) {
      setError('Failed to trigger CMS ingestion');
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerCMSBulk = async () => {
    setActionLoading('cms-bulk');
    try {
      await triggerCMSBulkDownload();
      setSuccessMessage('CMS bulk download started - this may take a few minutes');
      await loadData();
    } catch (err) {
      setError('Failed to trigger CMS bulk download');
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerCMSAPI = async () => {
    setActionLoading('cms-api');
    try {
      await triggerCMSAPISync();
      setSuccessMessage('CMS API sync started');
      await loadData();
    } catch (err) {
      setError('Failed to trigger CMS API sync');
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerCMSIncremental = async () => {
    setActionLoading('cms-incremental');
    try {
      const result = await triggerCMSIncrementalUpdate(incrementalDays);
      setSuccessMessage(result.message);
      await loadData();
    } catch (err) {
      setError('Failed to trigger CMS incremental update');
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerCommercial = async () => {
    setActionLoading('commercial');
    try {
      await triggerCommercialIngestion();
      await loadData();
    } catch (err) {
      setError('Failed to trigger commercial ingestion');
    } finally {
      setActionLoading(null);
    }
  };

  const handleTriggerFull = async () => {
    setActionLoading('full');
    try {
      await triggerFullIngestion();
      await loadData();
    } catch (err) {
      setError('Failed to trigger full ingestion');
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleScheduler = async () => {
    setActionLoading('scheduler');
    try {
      if (schedulerRunning) {
        await stopScheduler();
      } else {
        await startScheduler(24, false);
      }
      await loadData();
    } catch (err) {
      setError('Failed to toggle scheduler');
    } finally {
      setActionLoading(null);
    }
  };

  const handleAddCustomDocument = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionLoading('customDoc');
    setError(null);
    setSuccessMessage(null);
    
    try {
      const result = await addCustomDocument(customDoc);
      setSuccessMessage(result.message);
      setShowAddDocForm(false);
      setCustomDoc({
        title: '',
        content: '',
        source_type: 'COMMERCIAL',
        payer: '',
        mac_region: '',
        source_url: '',
        effective_date: '',
      });
      await loadData();
    } catch (err) {
      setError('Failed to add custom document');
    } finally {
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-gray-500">Loading dashboard...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Data Sources Dashboard</h1>
            <p className="text-sm text-gray-500 mt-1">Manage RAG pipeline and policy data sources</p>
          </div>
          <div className="flex items-center gap-3">
            <a href="/chat" className="text-blue-600 hover:text-blue-800 text-sm">
              ← Back to Chat
            </a>
            <button
              onClick={loadData}
              className="px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-md"
            >
              Refresh
            </button>
          </div>
        </div>
      </header>

      <main className="p-6 max-w-7xl mx-auto">
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
            {error}
          </div>
        )}

        {successMessage && (
          <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg text-green-700">
            {successMessage}
          </div>
        )}

        {/* Overview Stats */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Overview</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
            <StatsCard
              title="Total Documents"
              value={policyStats?.total_documents || 0}
              color="blue"
            />
            <StatsCard
              title="Medicare LCDs"
              value={policyStats?.medicare_lcd_count || 0}
              color="purple"
            />
            <StatsCard
              title="Medicare NCDs"
              value={policyStats?.medicare_ncd_count || 0}
              color="purple"
            />
            <StatsCard
              title="Commercial Policies"
              value={policyStats?.commercial_policy_count || 0}
              color="green"
            />
            <StatsCard
              title="Data Freshness"
              value={policyStats?.overall_freshness ? 'Fresh' : 'Stale'}
              color={policyStats?.overall_freshness ? 'green' : 'red'}
            />
            <StatsCard
              title="Scheduler"
              value={schedulerRunning ? 'Running' : 'Stopped'}
              color={schedulerRunning ? 'green' : 'yellow'}
            />
          </div>
        </section>

        {/* Ingestion Actions */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Ingestion Actions</h2>
          <div className="bg-white rounded-lg border border-gray-200 p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <button
                onClick={() => handleTriggerFull()}
                disabled={actionLoading !== null}
                className="px-4 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === 'full' ? 'Running...' : 'Run Full Ingestion'}
              </button>
              <button
                onClick={() => setShowCMSOptions(!showCMSOptions)}
                disabled={actionLoading !== null}
                className="px-4 py-3 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                <span>Medicare Options</span>
                <svg className={`w-4 h-4 transition-transform ${showCMSOptions ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              <button
                onClick={() => handleTriggerCommercial()}
                disabled={actionLoading !== null}
                className="px-4 py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {actionLoading === 'commercial' ? 'Running...' : 'Ingest Commercial Payers'}
              </button>
              <button
                onClick={handleToggleScheduler}
                disabled={actionLoading !== null}
                className={`px-4 py-3 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed ${
                  schedulerRunning
                    ? 'bg-red-600 text-white hover:bg-red-700'
                    : 'bg-gray-600 text-white hover:bg-gray-700'
                }`}
              >
                {actionLoading === 'scheduler'
                  ? 'Processing...'
                  : schedulerRunning
                  ? 'Stop Scheduler'
                  : 'Start Scheduler (24h)'}
              </button>
            </div>

            {/* CMS Data Source Options */}
            {showCMSOptions && (
              <div className="mt-4 p-4 bg-purple-50 rounded-lg border border-purple-200">
                <h3 className="text-sm font-semibold text-purple-900 mb-3">Medicare Data Source Options</h3>
                <p className="text-xs text-purple-700 mb-4">
                  {cmsDataSources?.recommendation || 'Choose a data source for Medicare coverage data ingestion.'}
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                  <button
                    onClick={handleTriggerCMSBulk}
                    disabled={actionLoading !== null}
                    className="px-3 py-2 bg-purple-700 text-white text-sm rounded-md hover:bg-purple-800 disabled:opacity-50"
                  >
                    {actionLoading === 'cms-bulk' ? 'Downloading...' : '📦 Bulk Download (Initial)'}
                  </button>
                  <button
                    onClick={handleTriggerCMSAPI}
                    disabled={actionLoading !== null}
                    className="px-3 py-2 bg-purple-600 text-white text-sm rounded-md hover:bg-purple-700 disabled:opacity-50"
                  >
                    {actionLoading === 'cms-api' ? 'Syncing...' : '🔄 API Sync'}
                  </button>
                  <div className="flex gap-2">
                    <input
                      type="number"
                      min="1"
                      max="90"
                      value={incrementalDays}
                      onChange={(e) => setIncrementalDays(parseInt(e.target.value) || 7)}
                      className="w-16 px-2 py-2 border border-purple-300 rounded-md text-sm"
                    />
                    <button
                      onClick={handleTriggerCMSIncremental}
                      disabled={actionLoading !== null}
                      className="flex-1 px-3 py-2 bg-purple-500 text-white text-sm rounded-md hover:bg-purple-600 disabled:opacity-50"
                    >
                      {actionLoading === 'cms-incremental' ? 'Updating...' : `⚡ Last ${incrementalDays}d`}
                    </button>
                  </div>
                  <button
                    onClick={() => handleTriggerCMS()}
                    disabled={actionLoading !== null}
                    className="px-3 py-2 bg-gray-500 text-white text-sm rounded-md hover:bg-gray-600 disabled:opacity-50"
                  >
                    {actionLoading === 'cms' ? 'Running...' : '🕸️ Web Scrape (Fallback)'}
                  </button>
                </div>
                {cmsDataSources && (
                  <div className="mt-3 text-xs text-purple-600">
                    <details>
                      <summary className="cursor-pointer hover:text-purple-800">View data source details</summary>
                      <div className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                        {cmsDataSources.sources.map((source) => (
                          <div key={source.id} className="p-2 bg-white rounded border border-purple-100">
                            <div className="font-medium">{source.name}</div>
                            <div className="text-gray-600">{source.description}</div>
                            <div className="text-gray-500 mt-1">
                              Update: {source.update_frequency} | Auth: {String(source.requires_auth)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </details>
                  </div>
                )}
              </div>
            )}

            {runningJobs.length > 0 && (
              <div className="mt-4 p-3 bg-blue-50 rounded-lg">
                <div className="text-sm font-medium text-blue-800">
                  {runningJobs.length} job(s) currently running
                </div>
              </div>
            )}
            
            {/* Add Custom Document Button */}
            <div className="mt-4 pt-4 border-t border-gray-200">
              <button
                onClick={() => setShowAddDocForm(!showAddDocForm)}
                className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                </svg>
                {showAddDocForm ? 'Cancel' : 'Add Custom Document'}
              </button>
            </div>

            {/* Custom Document Form */}
            {showAddDocForm && (
              <form onSubmit={handleAddCustomDocument} className="mt-4 p-4 bg-gray-50 rounded-lg">
                <h3 className="text-sm font-semibold text-gray-900 mb-4">Add Custom Document</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Title *</label>
                    <input
                      type="text"
                      required
                      value={customDoc.title}
                      onChange={(e) => setCustomDoc({ ...customDoc, title: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      placeholder="Policy document title"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Source Type *</label>
                    <select
                      value={customDoc.source_type}
                      onChange={(e) => setCustomDoc({ ...customDoc, source_type: e.target.value as 'LCD' | 'NCD' | 'COMMERCIAL' | 'CARC' })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    >
                      <option value="COMMERCIAL">Commercial Policy</option>
                      <option value="LCD">Medicare LCD</option>
                      <option value="NCD">Medicare NCD</option>
                      <option value="CARC">CARC Code</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Payer</label>
                    <input
                      type="text"
                      value={customDoc.payer || ''}
                      onChange={(e) => setCustomDoc({ ...customDoc, payer: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      placeholder="e.g., Aetna, UnitedHealthcare"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">MAC Region</label>
                    <input
                      type="text"
                      value={customDoc.mac_region || ''}
                      onChange={(e) => setCustomDoc({ ...customDoc, mac_region: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      placeholder="e.g., NOVITAS, PALMETTO"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Source URL</label>
                    <input
                      type="url"
                      value={customDoc.source_url || ''}
                      onChange={(e) => setCustomDoc({ ...customDoc, source_url: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                      placeholder="https://..."
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Effective Date</label>
                    <input
                      type="date"
                      value={customDoc.effective_date || ''}
                      onChange={(e) => setCustomDoc({ ...customDoc, effective_date: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    />
                  </div>
                </div>
                <div className="mt-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">Content *</label>
                  <textarea
                    required
                    rows={6}
                    value={customDoc.content}
                    onChange={(e) => setCustomDoc({ ...customDoc, content: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                    placeholder="Paste the policy document content here..."
                  />
                </div>
                <div className="mt-4 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setShowAddDocForm(false)}
                    className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading === 'customDoc'}
                    className="px-4 py-2 bg-blue-600 text-white text-sm rounded-md hover:bg-blue-700 disabled:opacity-50"
                  >
                    {actionLoading === 'customDoc' ? 'Adding...' : 'Add Document'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </section>

        {/* Data Sources Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          {/* Medicare MAC Regions */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Medicare MAC Regions</h2>
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Region</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Docs</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {macRegions.map((region) => (
                    <tr key={region.mac_region} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-medium">
                        {region.document_count > 0 ? (
                          <button
                            onClick={() => handleViewMACRegionDocuments(region.mac_region, region.mac_name)}
                            className="text-blue-600 hover:text-blue-800 hover:underline text-left"
                          >
                            {region.mac_region}
                          </button>
                        ) : (
                          <span className="text-gray-900">{region.mac_region}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{region.mac_name}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{region.document_count}</td>
                      <td className="px-4 py-3">
                        {region.is_covered ? (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            Covered
                          </span>
                        ) : (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                            Not Ingested
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Commercial Payers */}
          <section>
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Commercial Payers</h2>
            <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Payer</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Docs</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Updated</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {payers.map((payer) => (
                    <tr key={payer.payer_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-medium">
                        {payer.document_count > 0 ? (
                          <button
                            onClick={() => handleViewPayerDocuments(payer.payer_id, payer.payer_name)}
                            className="text-blue-600 hover:text-blue-800 hover:underline text-left"
                          >
                            {payer.payer_name}
                          </button>
                        ) : (
                          <span className="text-gray-900">{payer.payer_name}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{payer.document_count}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {payer.last_updated
                          ? new Date(payer.last_updated).toLocaleDateString()
                          : 'Never'}
                      </td>
                      <td className="px-4 py-3">
                        {payer.is_supported ? (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            Supported
                          </span>
                        ) : (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                            Not Supported
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>

        {/* Recent Jobs */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Ingestion Jobs</h2>
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Job ID</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Started</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Docs</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Failed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {jobs.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                      No ingestion jobs yet. Click "Run Full Ingestion" to start.
                    </td>
                  </tr>
                ) : (
                  jobs.map((job) => (
                    <tr key={job.job_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm font-mono text-gray-600">
                        {job.job_id.slice(0, 8)}...
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-900">
                        {job.source === 'CMS_GOV' ? 'Medicare (CMS)' : 'Commercial'}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={job.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {new Date(job.started_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">{job.documents_processed}</td>
                      <td className="px-4 py-3 text-sm text-red-600">{job.documents_failed}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Ingestion Stats */}
        <section>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Ingestion Statistics</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatsCard
              title="Total Jobs"
              value={ingestionStats?.total_jobs || 0}
              color="blue"
            />
            <StatsCard
              title="Completed"
              value={ingestionStats?.completed_jobs || 0}
              color="green"
            />
            <StatsCard
              title="Failed"
              value={ingestionStats?.failed_jobs || 0}
              color="red"
            />
            <StatsCard
              title="Documents Processed"
              value={ingestionStats?.total_documents_processed || 0}
              color="purple"
            />
          </div>
        </section>
      </main>

      {/* Documents Modal */}
      {showDocumentsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[80vh] flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">{documentsModalTitle}</h3>
              <button
                onClick={() => setShowDocumentsModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6">
              {documentsLoading ? (
                <div className="text-center py-8 text-gray-500">Loading documents...</div>
              ) : documentsModalData.length === 0 ? (
                <div className="text-center py-8 text-gray-500">No documents found</div>
              ) : (
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Title</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Effective Date</th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {documentsModalData.map((doc) => (
                      <tr key={doc.document_id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 text-sm">
                          <button
                            onClick={() => handleViewDocumentDetail(doc.document_id)}
                            className="text-blue-600 hover:text-blue-800 hover:underline text-left"
                          >
                            {doc.title}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-600">{doc.document_type}</td>
                        <td className="px-4 py-3 text-sm text-gray-600">
                          {doc.effective_date
                            ? new Date(doc.effective_date).toLocaleDateString()
                            : '-'}
                        </td>
                        <td className="px-4 py-3 text-sm">
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleViewDocumentDetail(doc.document_id)}
                              className="text-blue-600 hover:text-blue-800 text-xs"
                            >
                              View Content
                            </button>
                            {doc.source_url && (
                              <a
                                href={doc.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-gray-500 hover:text-gray-700 text-xs"
                              >
                                Source ↗
                              </a>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="px-6 py-4 border-t border-gray-200 flex justify-end">
              <button
                onClick={() => setShowDocumentsModal(false)}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Document Detail Modal */}
      {showDocumentDetail && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-[60]">
          <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full mx-4 max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">
                  {documentDetail?.title || 'Document Details'}
                </h3>
                {documentDetail && (
                  <div className="flex gap-3 mt-1 text-xs text-gray-500">
                    <span className="px-2 py-0.5 bg-gray-100 rounded">{documentDetail.document_type}</span>
                    {documentDetail.payer && <span>Payer: {documentDetail.payer}</span>}
                    {documentDetail.mac_region && <span>MAC: {documentDetail.mac_region}</span>}
                    {documentDetail.effective_date && (
                      <span>Effective: {new Date(documentDetail.effective_date).toLocaleDateString()}</span>
                    )}
                  </div>
                )}
              </div>
              <button
                onClick={() => {
                  setShowDocumentDetail(false);
                  setDocumentDetail(null);
                }}
                className="text-gray-400 hover:text-gray-600"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 overflow-auto p-6">
              {documentDetailLoading ? (
                <div className="text-center py-8 text-gray-500">Loading document content...</div>
              ) : !documentDetail ? (
                <div className="text-center py-8 text-gray-500">Document not found</div>
              ) : !documentDetail.has_content ? (
                <div className="text-center py-8">
                  <div className="text-gray-500 mb-4">No extracted content available for this document.</div>
                  {documentDetail.source_url && (
                    <a
                      href={documentDetail.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
                    >
                      View Original Source
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  )}
                </div>
              ) : (
                <div className="prose prose-sm max-w-none">
                  <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
                    <pre className="whitespace-pre-wrap text-sm text-gray-800 font-sans leading-relaxed">
                      {documentDetail.content}
                    </pre>
                  </div>
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-gray-200 flex justify-between items-center">
              <div>
                {documentDetail?.source_url && (
                  <a
                    href={documentDetail.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
                  >
                    View Original Source
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                  </a>
                )}
              </div>
              <button
                onClick={() => {
                  setShowDocumentDetail(false);
                  setDocumentDetail(null);
                }}
                className="px-4 py-2 bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
