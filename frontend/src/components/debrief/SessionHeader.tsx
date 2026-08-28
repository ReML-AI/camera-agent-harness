import { useEffect, useState } from 'react';
import { MomentContextsResponse, InteractionAnalytics } from '@/types';
import { ToolsMenu } from './ToolsMenu';
import { Star } from 'lucide-react';
import { api } from '@/services/api';
import { useSessionStore } from '@/stores/sessionStore';

type ToolView = 'debrief_report';

interface Props {
  sessionId: string;
  analytics: InteractionAnalytics | undefined;
  momentContexts: MomentContextsResponse | undefined;
  starredCount?: number;
  onSelectTool: (view: ToolView) => void;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function SessionHeader({ sessionId, analytics, momentContexts, starredCount = 0, onSelectTool }: Props) {
  const { setSessionId } = useSessionStore();
  const [sessions, setSessions] = useState<{ id: string; total_moments: number }[]>([]);

  useEffect(() => {
    api.listSessions().then(setSessions).catch(() => {});
  }, []);

  const speakerCount = analytics ? Object.keys(analytics.speakers).length : 0;
  const momentCount = momentContexts?.metadata.total_moments ?? 0;

  const duration = analytics?.timeline_segments.length
    ? analytics.timeline_segments.reduce((max, s) => (s.end > max ? s.end : max), 0)
    : null;

  const moments = momentContexts?.moments ?? [];
  const criticalCount = moments.filter(m => m.importance === 'critical').length;
  const narrativesReady = moments.filter(m => m.narrative).length;
  const narrativePct = moments.length > 0 ? narrativesReady / moments.length : 0;

  const dominantSpeaker = analytics
    ? Object.entries(analytics.speakers).sort(
        (a, b) => (b[1].talk_percentage ?? 0) - (a[1].talk_percentage ?? 0)
      )[0]
    : null;

  return (
    <div className="bg-white border-b border-gray-200 px-4 py-2.5 flex items-center justify-between flex-shrink-0">
      <div>
        <h1 className="text-base font-semibold text-gray-900">Clinical Simulation Debrief</h1>
        <div className="flex items-center gap-2 mt-0.5">
          {sessions.length > 1 ? (
            <select
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              className="text-xs text-gray-700 border border-gray-300 rounded px-1.5 py-0.5 bg-white cursor-pointer hover:border-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              {sessions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id} ({s.total_moments} moments)
                </option>
              ))}
            </select>
          ) : (
            <span className="text-xs text-gray-500">Session {sessionId}</span>
          )}
          {analytics && (
            <span className="text-xs text-gray-500">&mdash; {speakerCount} speakers, {momentCount} moments</span>
          )}
        </div>
        {analytics && momentContexts && (
          <div className="flex flex-wrap gap-1.5 mt-1">
            {duration !== null && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                {formatDuration(duration)}
              </span>
            )}
            {criticalCount > 0 && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-red-50 text-red-700">
                {criticalCount} critical
              </span>
            )}
            {moments.length > 0 && (
              <span className={`text-[11px] px-2 py-0.5 rounded-full ${narrativePct >= 0.8 ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700'}`}>
                {narrativesReady}/{moments.length} narratives
              </span>
            )}
            {dominantSpeaker && dominantSpeaker[1].talk_percentage != null && (
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">
                {dominantSpeaker[1].label} {dominantSpeaker[1].talk_percentage.toFixed(0)}%
              </span>
            )}
          </div>
        )}
      </div>
      <div className="flex items-center gap-3">
        {starredCount > 0 && (
          <span className="flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5">
            <Star size={11} className="fill-amber-400 text-amber-400" />
            {starredCount} starred
          </span>
        )}
        <ToolsMenu onSelectView={onSelectTool} />
      </div>
    </div>
  );
}
