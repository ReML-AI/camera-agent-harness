import { useState } from 'react';
import { MomentContext } from '@/types';
import { api } from '@/services/api';
import {
  AlertTriangle, AlertCircle, MessageSquare, Activity,
  RefreshCw, ChevronDown, ChevronRight, Loader2,
  Clock, Users, Zap, VolumeX,
} from 'lucide-react';

interface Props {
  moment: MomentContext;
  speakerRoles: Record<string, { label: string; role: string }>;
  sessionId: string;
  onNarrativeUpdated?: (momentId: number, narrative: string, tags: string[], prompt: string) => void;
  onNavigate?: (direction: 'prev' | 'next') => void;
  hasPrev?: boolean;
  hasNext?: boolean;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export function MomentContextPanel({ moment, speakerRoles, sessionId, onNarrativeUpdated, onNavigate, hasPrev, hasNext }: Props) {
  const [regenerating, setRegenerating] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);
  const [showUtterances, setShowUtterances] = useState(false);
  const [showOverlappingInsights, setShowOverlappingInsights] = useState(false);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setRegenerateError(null);
    try {
      const result = await api.regenerateNarrative(sessionId, moment.moment_id);
      onNarrativeUpdated?.(moment.moment_id, result.narrative, result.tags, result.discussion_prompt);
    } catch (err) {
      setRegenerateError('Failed to regenerate narrative. Check API key configuration.');
      console.error('Failed to regenerate:', err);
    } finally {
      setRegenerating(false);
    }
  };

  const getRoleName = (speaker: string) => {
    const info = speakerRoles[speaker];
    return info ? `${info.label} (${info.role})` : speaker;
  };

  const getShortRole = (speaker: string) => {
    const info = speakerRoles[speaker];
    return info ? info.role : speaker;
  };

  // Collect all utterances chronologically across all speakers
  const allUtterances: { speaker: string; text: string; start?: number }[] = [];
  Object.entries(moment.speech.per_speaker).forEach(([spk, data]) => {
    (data.utterances || []).forEach((utt: string, i: number) => {
      allUtterances.push({ speaker: spk, text: utt, start: data.talk_time_seconds });
    });
  });

  const { dynamics } = moment;

  return (
    <div className="space-y-3">
      {/* Header */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            {moment.importance === 'critical' ? (
              <AlertTriangle size={16} className="text-red-500" />
            ) : (
              <AlertCircle size={16} className="text-amber-500" />
            )}
            <span className="text-sm font-semibold text-gray-900">{moment.category}</span>
            <span className={`text-xs px-1.5 py-0.5 rounded ${moment.importance === 'critical' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
              {moment.importance}
            </span>
          </div>
          {/* Prev/Next navigation */}
          {onNavigate && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => onNavigate('prev')}
                disabled={!hasPrev}
                className="text-xs px-1.5 py-0.5 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                &larr; Prev
              </button>
              <button
                onClick={() => onNavigate('next')}
                disabled={!hasNext}
                className="text-xs px-1.5 py-0.5 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Next &rarr;
              </button>
            </div>
          )}
        </div>
        {/* Multiple categories badge */}
        {moment.categories && moment.categories.length > 1 && (
          <div className="flex flex-wrap gap-1 mb-1">
            {moment.categories.map((cat, i) => (
              <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                {cat.category}
              </span>
            ))}
          </div>
        )}
        <div className="text-xs text-gray-500 mb-1">
          {formatTime(moment.timestamp)} - {formatTime(moment.end_timestamp)} ({moment.duration.toFixed(1)}s)
        </div>
        <p className="text-xs text-gray-500 italic line-clamp-2">
          &ldquo;{moment.original_text.slice(0, 150)}{moment.original_text.length > 150 ? '...' : ''}&rdquo;
        </p>
      </div>

      {/* Vitals strip */}
      {moment.vitals.readings_in_window > 0 ? (
        <div className="bg-white border border-gray-200 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-600 flex items-center gap-1 mb-2">
            <Activity size={12} /> Vitals
          </h4>
          <div className="flex gap-4 text-xs">
            {moment.vitals.spo2 && (
              <span>SpO2: {moment.vitals.spo2.start}% &rarr; {moment.vitals.spo2.end}%
                <span className={moment.vitals.spo2.trend === 'declining' ? ' text-red-600 font-medium' : ''}> ({moment.vitals.spo2.trend})</span>
              </span>
            )}
            {moment.vitals.heart_rate && (
              <span>HR: {moment.vitals.heart_rate.start} &rarr; {moment.vitals.heart_rate.end} bpm</span>
            )}
          </div>
        </div>
      ) : (
        <div className="flex gap-2 items-center p-2 text-xs text-gray-400">
          <Activity size={14} className="flex-shrink-0" />
          <span>Monitor data not captured</span>
        </div>
      )}

      {/* Speech Analysis Card */}
      <div className="bg-white border border-gray-200 rounded-lg p-3">
        <h4 className="text-xs font-semibold text-gray-600 flex items-center gap-1 mb-2">
          <MessageSquare size={12} /> Speech Analysis
          <span className="font-normal text-gray-400 ml-1">({moment.speech.total_utterances} utterances, {moment.speech.silence_seconds.toFixed(1)}s silence)</span>
        </h4>
        {Object.entries(moment.speech.per_speaker).map(([spk, data]) => (
          <div key={spk} className="mb-1.5">
            <div className="flex items-center gap-2 text-xs">
              <span className="font-medium text-gray-700 w-44 truncate">{getRoleName(spk)}</span>
              <div className="flex-1 bg-gray-100 rounded-full h-3 overflow-hidden">
                <div
                  className="bg-blue-500 h-full rounded-full"
                  style={{ width: `${Math.min(data.talk_time_pct, 100)}%` }}
                />
              </div>
              <span className="text-gray-500 w-12 text-right">{data.talk_time_pct}%</span>
            </div>
          </div>
        ))}
        {/* Chronological utterances (all speakers interleaved) */}
        {allUtterances.length > 0 && (
          <button
            className="text-xs text-blue-600 hover:underline flex items-center gap-1 mt-1"
            onClick={() => setShowUtterances(!showUtterances)}
          >
            {showUtterances ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {showUtterances ? 'Hide' : 'Show'} conversation flow
          </button>
        )}
        {showUtterances && (
          <div className="mt-2 space-y-1.5 pl-2 border-l-2 border-blue-200">
            {allUtterances.map((utt, i) => (
              <p key={i} className="text-xs text-gray-600">
                <span className="font-medium text-gray-800">{getShortRole(utt.speaker)}:</span>{' '}
                &ldquo;{utt.text.slice(0, 200)}{utt.text.length > 200 ? '...' : ''}&rdquo;
              </p>
            ))}
          </div>
        )}
      </div>

      {/* Team Dynamics Card */}
      {dynamics && (
        <div className="bg-white border border-gray-200 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-gray-600 flex items-center gap-1 mb-2">
            <Users size={12} /> Team Dynamics
          </h4>
          <div className="space-y-2">
            {/* Response latency */}
            {dynamics.first_response_latency_seconds != null && dynamics.first_response_latency_seconds > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <Clock size={14} className="text-blue-400" />
                <span className="text-gray-700">{dynamics.first_response_latency_seconds.toFixed(1)}s to first response</span>
              </div>
            )}
            {dynamics.first_response_latency_seconds != null && dynamics.first_response_latency_seconds === 0 && (
              <div className="flex items-center gap-2 text-xs">
                <Zap size={14} className="text-green-400" />
                <span className="text-gray-500">Immediate response</span>
              </div>
            )}

            {/* Silence gaps */}
            {dynamics.silence_gaps && dynamics.silence_gaps.length > 0 && (
              <div className="flex items-center gap-2 text-xs">
                <VolumeX size={14} className={dynamics.silence_gaps.some(g => g.duration > 5) ? 'text-amber-500' : 'text-gray-400'} />
                <span className={dynamics.silence_gaps.some(g => g.duration > 5) ? 'text-amber-700 font-medium' : 'text-gray-500'}>
                  {dynamics.silence_gaps.map((g, i) => `${g.duration.toFixed(1)}s silence`).join(', ')}
                </span>
              </div>
            )}

            {/* Overlapping insights */}
            {dynamics.overlapping_insights && dynamics.overlapping_insights.length > 0 && (
              <div>
                <button
                  className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                  onClick={() => setShowOverlappingInsights(!showOverlappingInsights)}
                >
                  {showOverlappingInsights ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                  {dynamics.overlapping_insights.length} interaction insight{dynamics.overlapping_insights.length > 1 ? 's' : ''} detected
                </button>
                {showOverlappingInsights && (
                  <div className="mt-1 space-y-1 pl-4">
                    {dynamics.overlapping_insights.map((insight, i) => (
                      <p key={i} className="text-xs text-gray-500">
                        <span className="font-medium">{insight.type}</span>
                        {insight.description && `: ${insight.description}`}
                      </p>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* AI Narrative */}
      {moment.narrative ? (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
          <div className="flex items-center justify-between mb-1">
            <h4 className="text-xs font-semibold text-blue-700">AI Observation</h4>
            <button
              className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
              onClick={handleRegenerate}
              disabled={regenerating}
            >
              {regenerating ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Regenerate
            </button>
          </div>
          <p className="text-sm text-gray-800">{moment.narrative}</p>
          {regenerateError && (
            <p className="text-xs text-red-500 mt-1">{regenerateError}</p>
          )}
        </div>
      ) : (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-gray-400 italic">No narrative generated yet</p>
            <button
              className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1"
              onClick={handleRegenerate}
              disabled={regenerating}
            >
              {regenerating ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
              Generate
            </button>
          </div>
          {regenerateError && (
            <p className="text-xs text-red-500 mt-1">{regenerateError}</p>
          )}
        </div>
      )}

      {/* Discussion Prompt */}
      {moment.discussion_prompt && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
          <h4 className="text-xs font-semibold text-amber-700 mb-1">Discussion Prompt</h4>
          <p className="text-sm text-gray-700 italic">{moment.discussion_prompt}</p>
        </div>
      )}
    </div>
  );
}
