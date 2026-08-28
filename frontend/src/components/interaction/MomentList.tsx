import { useState, useCallback, useMemo } from 'react';
import { MomentContext } from '@/types';
import { formatTime } from '@/utils/time';
import {
  AlertTriangle, AlertCircle, Clock, Filter,
  Star, ChevronUp, ChevronDown, RotateCcw,
} from 'lucide-react';

interface Props {
  moments: MomentContext[];
  selectedId: number | null;
  onSelect: (moment: MomentContext) => void;
  onNavigate?: (direction: 'prev' | 'next') => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  'Emergency Recognition': 'bg-red-100 text-red-700',
  'Emergency Management': 'bg-red-100 text-red-700',
  'Medication Management': 'bg-amber-100 text-amber-700',
  'Communication Skills': 'bg-blue-100 text-blue-700',
  'Vascular Access': 'bg-purple-100 text-purple-700',
  'Physical Examination': 'bg-green-100 text-green-700',
  'Patient Assessment': 'bg-teal-100 text-teal-700',
};

type StarFilter = 'all' | 'starred';

export function MomentList({ moments, selectedId, onSelect, onNavigate }: Props) {
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [importanceFilter, setImportanceFilter] = useState<string>('all');
  const [starFilter, setStarFilter] = useState<StarFilter>('all');
  const [starredMoments, setStarredMoments] = useState<Set<number>>(new Set());

  const categories = useMemo(
    () =>
      Array.from(
        new Set(
          moments.flatMap((m) =>
            m.categories && m.categories.length > 1
              ? m.categories.map((c) => c.category)
              : [m.category]
          )
        )
      ),
    [moments]
  );

  const filtered = useMemo(() => {
    return moments.filter((m) => {
      if (categoryFilter !== 'all') {
        const allCats =
          m.categories && m.categories.length > 1
            ? m.categories.map((c) => c.category)
            : [m.category];
        if (!allCats.includes(categoryFilter)) return false;
      }
      if (importanceFilter !== 'all' && m.importance !== importanceFilter) return false;
      if (starFilter === 'starred' && !starredMoments.has(m.moment_id)) return false;
      return true;
    });
  }, [moments, categoryFilter, importanceFilter, starFilter, starredMoments]);

  const toggleStar = useCallback(
    (e: React.MouseEvent, momentId: number) => {
      e.stopPropagation();
      setStarredMoments((prev) => {
        const next = new Set(prev);
        if (next.has(momentId)) {
          next.delete(momentId);
        } else {
          next.add(momentId);
        }
        return next;
      });
    },
    []
  );

  const resetFilters = useCallback(() => {
    setCategoryFilter('all');
    setImportanceFilter('all');
    setStarFilter('all');
  }, []);

  const starredCount = starredMoments.size;

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-3 py-3 border-b border-gray-200 flex-shrink-0">
        <div className="flex items-center justify-between mb-0.5">
          <h3 className="text-sm font-bold text-gray-800 tracking-tight">Clinical Moments</h3>
          {/* Prev / Next nav buttons */}
          {onNavigate && (
            <div className="flex items-center gap-0.5">
              <button
                className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                onClick={() => onNavigate('prev')}
                title="Previous moment"
              >
                <ChevronUp size={14} />
              </button>
              <button
                className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                onClick={() => onNavigate('next')}
                title="Next moment"
              >
                <ChevronDown size={14} />
              </button>
            </div>
          )}
        </div>
        <p className="text-xs text-gray-500 mb-2">
          ({filtered.length} event{filtered.length !== 1 ? 's' : ''} detected)
          {starredCount > 0 && (
            <span className="ml-1 text-amber-600 font-medium">
              &middot; {starredCount} starred for debrief
            </span>
          )}
        </p>

        {/* Filters */}
        <div className="space-y-1.5">
          <select
            className="w-full text-xs border border-gray-200 rounded px-2 py-1 bg-white focus:ring-1 focus:ring-blue-300 focus:border-blue-300 outline-none"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="all">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <div className="flex gap-1 flex-wrap">
            {['all', 'critical', 'high'].map((imp) => (
              <button
                key={imp}
                className={`text-xs px-2 py-0.5 rounded transition-colors ${
                  importanceFilter === imp
                    ? 'bg-gray-800 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
                onClick={() => setImportanceFilter(imp)}
              >
                {imp === 'all' ? 'All' : imp.charAt(0).toUpperCase() + imp.slice(1)}
              </button>
            ))}
            <span className="w-px bg-gray-200 mx-0.5" />
            {(['all', 'starred'] as const).map((sf) => (
              <button
                key={sf}
                className={`text-xs px-2 py-0.5 rounded transition-colors flex items-center gap-1 ${
                  starFilter === sf
                    ? 'bg-amber-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
                onClick={() => setStarFilter(sf)}
              >
                {sf === 'starred' && <Star size={10} />}
                {sf === 'all' ? 'All' : 'Starred'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Scrollable list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full px-4 py-12 text-center">
            <Filter size={24} className="text-gray-300 mb-2" />
            <p className="text-sm text-gray-500 mb-3">No moments match your filters</p>
            <button
              className="text-xs px-3 py-1.5 rounded bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors flex items-center gap-1.5"
              onClick={resetFilters}
            >
              <RotateCcw size={12} />
              Reset filters
            </button>
          </div>
        ) : (
          filtered.map((moment) => {
            const isStarred = starredMoments.has(moment.moment_id);
            const isSelected = selectedId === moment.moment_id;
            return (
              <button
                key={moment.moment_id}
                className={`w-full text-left px-3 py-2.5 border-b border-gray-100 hover:bg-blue-50 transition-colors group ${
                  isSelected ? 'bg-blue-50 border-l-2 border-l-blue-500' : ''
                }`}
                onClick={() => onSelect(moment)}
              >
                <div className="flex items-start gap-1.5 mb-1">
                  <div className="flex items-center gap-1.5 flex-1 flex-wrap">
                    {moment.importance === 'critical' ? (
                      <AlertTriangle size={12} className="text-red-500 flex-shrink-0" />
                    ) : (
                      <AlertCircle size={12} className="text-amber-500 flex-shrink-0" />
                    )}
                    <span className="text-xs font-medium text-gray-500">
                      <Clock size={10} className="inline mr-0.5" />
                      {formatTime(moment.timestamp)}
                    </span>
                    {moment.categories && moment.categories.length > 1 ? (
                      moment.categories.map((cat, idx) => (
                        <span
                          key={idx}
                          className={`text-xs px-1.5 py-0.5 rounded ${
                            CATEGORY_COLORS[cat.category] || 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {cat.category}
                        </span>
                      ))
                    ) : (
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded ${
                          CATEGORY_COLORS[moment.category] || 'bg-gray-100 text-gray-600'
                        }`}
                      >
                        {moment.category}
                      </span>
                    )}
                  </div>
                  {/* Star button */}
                  <button
                    className={`p-0.5 rounded transition-colors flex-shrink-0 ${
                      isStarred
                        ? 'text-amber-500'
                        : 'text-gray-300 opacity-0 group-hover:opacity-100 hover:text-amber-400'
                    }`}
                    onClick={(e) => toggleStar(e, moment.moment_id)}
                    title={isStarred ? 'Remove from debrief' : 'Star for debrief'}
                  >
                    <Star
                      size={14}
                      fill={isStarred ? 'currentColor' : 'none'}
                    />
                  </button>
                </div>
                <p className="text-xs text-gray-700 line-clamp-2">
                  {moment.narrative || moment.original_text}
                </p>
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
