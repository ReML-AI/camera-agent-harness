import { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useSessionStore } from '@/stores/sessionStore';
import { api } from '@/services/api';
import { DebriefView } from '@/pages/DebriefView';
import { DebriefReport } from '@/pages/DebriefReport';

const queryClient = new QueryClient();

function ReviewSession() {
  const { sessionId, setSessionId } = useSessionStore();
  const [showDebriefReport, setShowDebriefReport] = useState(false);

  useEffect(() => {
    if (sessionId) return;
    api.listSessions()
      .then((sessions) => {
        if (sessions.length > 0) setSessionId(sessions[0].id);
      })
      .catch(() => undefined);
  }, [sessionId, setSessionId]);

  const handleToolSelect = (view: string) => {
    if (view === 'debrief_report') {
      setShowDebriefReport(true);
    }
  };

  if (!sessionId) {
    return (
      <main className="h-screen grid place-items-center bg-gray-50 text-gray-700">
        No processed sessions are available.
      </main>
    );
  }

  return (
    <>
      {showDebriefReport && (
        <DebriefReport
          sessionId={sessionId}
          onClose={() => setShowDebriefReport(false)}
        />
      )}

      <div className="h-screen bg-gray-50 flex flex-col overflow-hidden">
        <DebriefView
          sessionId={sessionId}
          onSwitchView={handleToolSelect}
        />
      </div>
    </>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ReviewSession />
    </QueryClientProvider>
  );
}

export default App;
