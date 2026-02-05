import { useState, useRef, useEffect } from 'react';
import { Message, DataSource, Citation } from '../../types';
import { QueryInput } from './QueryInput';
import { ResponseDisplay } from './ResponseDisplay';
import { DataSourceIndicator } from '../common/DataSourceIndicator';
import { queryApi, DataSourceInfo } from '../../api/query';

interface ChatInterfaceProps {
  sessionId: string;
  initialMessages?: Message[];
  onNewSession?: () => void;
}

export function ChatInterface({ sessionId, initialMessages = [], onNewSession }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [isLoading, setIsLoading] = useState(false);
  const [dataSource, setDataSource] = useState<DataSource>('STUBBED');
  const [dataSourceInfo, setDataSourceInfo] = useState<DataSourceInfo | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMessages(initialMessages);
  }, [initialMessages, sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Fetch data source info on mount
  useEffect(() => {
    const fetchDataSourceInfo = async () => {
      try {
        const info = await queryApi.getDataSourceInfo();
        setDataSourceInfo(info);
        setDataSource(info.type as DataSource);
      } catch (error) {
        console.error('Failed to fetch data source info:', error);
      }
    };
    fetchDataSourceInfo();
  }, []);

  const handleSubmit = async (query: string) => {
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: query,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await queryApi.submit(sessionId, query);
      setMessages((prev) => [...prev, response.message]);
      setDataSource(response.data_source);
    } catch (error) {
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: 'Sorry, I encountered an error processing your request. Please try again.',
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      console.error('Query error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCitationClick = (citation: Citation) => {
    if (citation.source_url) {
      window.open(citation.source_url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold text-gray-900">Medical Billing Assistant</h2>
          <DataSourceIndicator 
            dataSource={dataSource} 
            isLive={dataSourceInfo?.is_live}
            displayMessage={dataSourceInfo?.display_message}
          />
        </div>
        {onNewSession && (
          <button
            onClick={onNewSession}
            className="text-sm text-blue-600 hover:text-blue-800 font-medium"
          >
            + New Chat
          </button>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <WelcomeMessage />
        ) : (
          messages.map((message) => (
            <ResponseDisplay
              key={message.id}
              message={message}
              dataSource={message.role === 'assistant' ? dataSource : undefined}
              isLiveData={message.role === 'assistant' ? dataSourceInfo?.is_live : undefined}
              onCitationClick={handleCitationClick}
            />
          ))
        )}

        {isLoading && <LoadingIndicator />}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <QueryInput onSubmit={handleSubmit} isLoading={isLoading} />
    </div>
  );
}

function WelcomeMessage() {
  return (
    <div className="text-center py-12">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-blue-100 mb-4">
        <svg className="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      </div>
      <h3 className="text-xl font-semibold text-gray-900 mb-2">Welcome to Medical Billing Copilot</h3>
      <p className="text-gray-600 max-w-md mx-auto mb-6">
        I can help you with coverage lookups, LCD queries, denial code explanations, and prior authorization requirements.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg mx-auto">
        <ExampleQuery text="Is CPT 99213 covered for diagnosis J06.9?" />
        <ExampleQuery text="Explain denial code CO-4" />
        <ExampleQuery text="What are the LCD requirements for 99214 in MAC region Novitas?" />
        <ExampleQuery text="Does Aetna require prior auth for 27447?" />
      </div>
    </div>
  );
}

function ExampleQuery({ text }: { text: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 text-left hover:border-blue-300 hover:bg-blue-50 cursor-pointer transition-colors">
      "{text}"
    </div>
  );
}

function LoadingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
        <div className="flex items-center space-x-2">
          <div className="flex space-x-1">
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
          <span className="text-sm text-gray-500">Searching policies...</span>
        </div>
      </div>
    </div>
  );
}
