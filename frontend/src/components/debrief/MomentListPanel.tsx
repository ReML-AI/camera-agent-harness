// frontend/src/components/debrief/MomentListPanel.tsx
import { useMemo } from 'react';
import { MomentContext } from '@/types';
import { Star, AlertTriangle, AlertCircle } from 'lucide-react';

interface Props {
  moments: MomentContext[];
  selectedMomentId: number | null;
  starredMomentIds: number[];
  onSelect: (moment: MomentContext) => void;
  onToggleStar: (momentId: number) => void;
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function formatCategory(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function MomentListPanel({ moments, selectedMomentId, starredMomentIds, onSelect, onToggleStar }: Props) {
  const starredSet = useMemo(() => new Set(starredMomentIds), [starredMomentIds]);

  return (
    <div className="h-full flex flex-col bg-white border-r border-gray-200">
      {/* Header */}
      <div className="px-3 py-2 border-b border-gray-100 flex-shrink-0">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Moments · {moments.length}
        </h2>
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto">
        {moments.map((moment) => {
          const isSelected = moment.moment_id === selectedMomentId;
          const isStarred = starredSet.has(moment.moment_id);
          const importanceIcon =
            moment.importance === 'critical' ? (
              <AlertTriangle size={12} className="text-red-500" />
            ) : (
              <AlertCircle size={12} className="text-amber-500" />
            );

          return (
            <div
              key={moment.moment_id}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(moment)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onSelect(moment);
                }
              }}
              className={`w-full text-left px-3 py-2 border-b border-gray-50 hover:bg-gray-50 transition-colors flex items-start gap-2 cursor-pointer border-l-2 ${
                isSelected ? 'bg-blue-50 border-l-blue-500' : 'border-l-transparent'
              }`}
            >
              {/* Importance icon */}
              <span className="mt-0.5 flex-shrink-0">
                {importanceIcon}
              </span>

              {/* Content */}
              <span className="flex-1 min-w-0">
                <span className="block text-xs font-medium text-gray-800 truncate">
                  {formatCategory(moment.category)}
                </span>
                <span className="block text-[10px] text-gray-400">
                  {formatTime(moment.timestamp)}
                  {moment.narrative ? ' · AI ready' : ''}
                </span>
              </span>

              {/* Star toggle */}
              <button
                aria-label={isStarred ? 'Unstar moment' : 'Star moment'}
                onClick={(e) => { e.stopPropagation(); onToggleStar(moment.moment_id); }}
                className={`flex-shrink-0 p-0.5 rounded transition-colors ${
                  isStarred ? 'text-amber-500' : 'text-gray-200 hover:text-amber-400'
                }`}
              >
                <Star size={11} fill={isStarred ? 'currentColor' : 'none'} />
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
