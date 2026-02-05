import { useState, useEffect, useCallback } from 'react';
import { Session, Message } from '../types';
import { sessionsApi } from '../api/sessions';
import { ChatInterface } from '../components/chat/ChatInterface';
import { SessionSidebar } from '../components/session/SessionSidebar';
import { useAuth } from '../contexts/AuthContext';

export function ChatPage() {
  const { user, logout } = useAuth();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [currentMessages, setCurrentMessages] = useState<Message[]>([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  const loadSessions = useCallback(async () => {
    try {
      const data = await sessionsApi.list();
      setSessions(data);
      return data;
    } catch (error) {
      console.error('Failed to load sessions:', error);
      return [];
    }
  }, []);

  const loadSessionMessages = useCallback(async (sessionId: string) => {
    try {
      const session = await sessionsApi.get(sessionId);
      setCurrentMessages(session.messages || []);
    } catch (error) {
      console.error('Failed to load session messages:', error);
      setCurrentMessages([]);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      setIsLoadingSessions(true);
      const loadedSessions = await loadSessions();
      
      if (loadedSessions.length > 0) {
        const firstSession = loadedSessions[0];
        setCurrentSessionId(firstSession.id);
        await loadSessionMessages(firstSession.id);
      } else {
        // Create initial session if none exist
        await handleNewSession();
      }
      setIsLoadingSessions(false);
    };

    init();
  }, [loadSessions, loadSessionMessages]);

  const handleNewSession = async () => {
    try {
      const newSession = await sessionsApi.create();
      setSessions((prev) => [newSession, ...prev]);
      setCurrentSessionId(newSession.id);
      setCurrentMessages([]);
    } catch (error) {
      console.error('Failed to create session:', error);
    }
  };

  const handleSelectSession = async (sessionId: string) => {
    setCurrentSessionId(sessionId);
    await loadSessionMessages(sessionId);
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await sessionsApi.delete(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      
      if (currentSessionId === sessionId) {
        const remainingSessions = sessions.filter((s) => s.id !== sessionId);
        if (remainingSessions.length > 0) {
          setCurrentSessionId(remainingSessions[0].id);
          await loadSessionMessages(remainingSessions[0].id);
        } else {
          await handleNewSession();
        }
      }
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Mobile sidebar toggle */}
      <button
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-gray-900 text-white rounded-lg"
      >
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
        </svg>
      </button>

      {/* Sidebar */}
      <div
        className={`fixed lg:static inset-y-0 left-0 z-40 transform ${
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
        } lg:translate-x-0 transition-transform duration-200 ease-in-out`}
      >
        <SessionSidebar
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          onDeleteSession={handleDeleteSession}
          isLoading={isLoadingSessions}
        />
      </div>

      {/* Overlay for mobile */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black bg-opacity-50 z-30 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200">
          <a
            href="/dashboard"
            className="text-sm text-blue-600 hover:text-blue-800 flex items-center gap-1"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
            Data Sources
          </a>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600">{user?.email}</span>
            <button
              onClick={logout}
              className="text-sm text-gray-500 hover:text-gray-700"
            >
              Sign out
            </button>
          </div>
        </div>

        {/* Chat interface */}
        <div className="flex-1 min-h-0">
          {currentSessionId ? (
            <ChatInterface
              sessionId={currentSessionId}
              initialMessages={currentMessages}
              onNewSession={handleNewSession}
            />
          ) : (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <p className="text-gray-500">Loading...</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
