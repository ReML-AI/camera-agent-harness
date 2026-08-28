import { useState, useEffect } from 'react';
import { MomentContext } from '@/types';
import { api } from '@/services/api';
import {
  RefreshCw, Loader2, Star, ChevronLeft, ChevronRight,
  ChevronDown, MessageCircle,
} from 'lucide-react';

interface Props {
  moment: MomentContext;
  sessionId: string;
  momentIndex: number;
  totalMoments: number;
  isStarred: boolean;
  onNavigate: (direction: 'prev' | 'next') => void;
  hasPrev: boolean;
  hasNext: boolean;
  onNarrativeUpdated: (momentId: number, narrative: string, tags: string[], prompt: string) => void;
  onToggleStar: (momentId: number) => void;
}

const NARRATIVE_TRUNCATE = 150;

export function AIObservationPanel({
  moment, sessionId, momentIndex, totalMoments,
  isStarred, onNavigate, hasPrev, hasNext, onNarrativeUpdated, onToggleStar,
}: Props) {
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [narrativeExpanded, setNarrativeExpanded] = useState(false);
  const [showPrompt, setShowPrompt] = useState(false);
  // Reset on moment navigation
  useEffect(() => {
    setNarrativeExpanded(false);
    setShowPrompt(false);
    setError(null);
  }, [moment.moment_id]);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setError(null);
    try {
      const result = await api.regenerateNarrative(sessionId, moment.moment_id);
      onNarrativeUpdated(moment.moment_id, result.narrative, result.tags, result.discussion_prompt);
    } catch (err) {
      setError('Failed to regenerate. Check API key.');
      console.error('Regenerate failed:', err);
    } finally {
      setRegenerating(false);
    }
  };

  const narrativeText = moment.narrative ?? '';
  const isTruncated = narrativeText.length > NARRATIVE_TRUNCATE;
  const displayedNarrative = (narrativeExpanded || !isTruncated)
    ? narrativeText
    : narrativeText.slice(0, NARRATIVE_TRUNCATE) + '...';

  return (
    <div className="space-y-3 text-xs">
      {/* AI Narrative */}
      {moment.narrative ? (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="font-semibold text-blue-700 flex items-center gap-1">
              <MessageCircle size={12} />
              AI Observation
            </span>
            <button
              className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
              onClick={handleRegenerate}
              disabled={regenerating}
            >
              {regenerating ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
              Regen
            </button>
          </div>
          <p className="text-sm text-gray-800 leading-relaxed">
            {displayedNarrative}
            {isTruncated && (
              <button
                className="ml-1 text-blue-600 hover:underline"
                onClick={() => setNarrativeExpanded(!narrativeExpanded)}
              >
                {narrativeExpanded ? 'Show less' : 'Read more'}
              </button>
            )}
          </p>
          {error && <p className="text-red-500 mt-1">{error}</p>}
        </div>
      ) : (
        <div className="bg-gray-50 rounded-lg p-3 flex items-center justify-between">
          <span className="text-gray-400 italic">No narrative yet</span>
          <button
            className="text-blue-600 hover:text-blue-800 flex items-center gap-1"
            onClick={handleRegenerate}
            disabled={regenerating}
          >
            {regenerating ? <Loader2 size={11} className="animate-spin" /> : <RefreshCw size={11} />}
            Generate
          </button>
        </div>
      )}

      {/* Discussion Prompt — collapsed by default */}
      {moment.discussion_prompt && (
        <div>
          <button
            className="flex items-center gap-1 text-amber-700 font-semibold hover:text-amber-800"
            onClick={() => setShowPrompt(!showPrompt)}
          >
            {showPrompt ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            Discussion Prompt
          </button>
          {showPrompt && (
            <div className="mt-1 bg-amber-50 border border-amber-200 rounded-lg p-3">
              <p className="text-sm text-gray-700 italic leading-relaxed">{moment.discussion_prompt}</p>
            </div>
          )}
        </div>
      )}

      {/* Star + Navigation footer */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-100">
        <button
          onClick={() => onToggleStar(moment.moment_id)}
          className={`flex items-center gap-1 px-2 py-1 rounded transition-colors ${
            isStarred
              ? 'text-amber-600 bg-amber-50 hover:bg-amber-100'
              : 'text-gray-400 hover:text-amber-500 hover:bg-gray-50'
          }`}
        >
          <Star size={13} fill={isStarred ? 'currentColor' : 'none'} />
          {isStarred ? 'Starred' : 'Star for debrief'}
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onNavigate('prev')}
            disabled={!hasPrev}
            className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed text-gray-500"
          >
            <ChevronLeft size={14} />
          </button>
          <span className="text-gray-500 font-medium">
            {momentIndex + 1} / {totalMoments}
          </span>
          <button
            onClick={() => onNavigate('next')}
            disabled={!hasNext}
            className="p-1 rounded hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed text-gray-500"
          >
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
