import { Message, Citation, DataSource } from '../../types';

interface ResponseDisplayProps {
  message: Message;
  dataSource?: DataSource;
  isLiveData?: boolean;
  onCitationClick?: (citation: Citation) => void;
}

export function ResponseDisplay({ message, dataSource, isLiveData, onCitationClick }: ResponseDisplayProps) {
  const isUser = message.role === 'user';
  
  // Show demo data warning only if we know it's not live data
  // If isLiveData is provided, use it; otherwise fall back to checking dataSource
  const showDemoWarning = isLiveData === false || (isLiveData === undefined && dataSource === 'STUBBED');

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-lg px-4 py-3 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-white border border-gray-200 text-gray-900'
        }`}
      >
        <div className="whitespace-pre-wrap">{message.content}</div>

        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <p className="text-xs font-medium text-gray-500 mb-2">Sources:</p>
            <div className="space-y-1">
              {message.citations.map((citation, index) => (
                <CitationBadge
                  key={index}
                  citation={citation}
                  onClick={() => onCitationClick?.(citation)}
                />
              ))}
            </div>
          </div>
        )}

        {!isUser && showDemoWarning && (
          <div className="mt-2 flex items-center text-xs text-amber-600">
            <svg className="h-3 w-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            Demo data
          </div>
        )}

        <div className={`mt-1 text-xs ${isUser ? 'text-blue-200' : 'text-gray-400'}`}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}

interface CitationBadgeProps {
  citation: Citation;
  onClick?: () => void;
}

function CitationBadge({ citation, onClick }: CitationBadgeProps) {
  const typeColors: Record<string, string> = {
    LCD: 'bg-purple-100 text-purple-800',
    NCD: 'bg-blue-100 text-blue-800',
    COMMERCIAL: 'bg-green-100 text-green-800',
    CARC: 'bg-orange-100 text-orange-800',
  };

  const colorClass = typeColors[citation.source_type] || 'bg-gray-100 text-gray-800';

  return (
    <button
      onClick={onClick}
      className={`inline-flex items-center px-2 py-1 rounded text-xs font-medium ${colorClass} hover:opacity-80 transition-opacity`}
    >
      <span className="font-semibold mr-1">{citation.source_type}:</span>
      <span className="truncate max-w-[200px]">{citation.document_title}</span>
      {citation.source_url && (
        <svg className="ml-1 h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
        </svg>
      )}
    </button>
  );
}
