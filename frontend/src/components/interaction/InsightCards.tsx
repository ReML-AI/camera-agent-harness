import { InteractionInsight } from '@/types';
import { Clock, Eye, RefreshCw, Zap } from 'lucide-react';

interface Props {
  insights: InteractionInsight[];
  onSeek: (time: number) => void;
}

const INSIGHT_CONFIG: Record<string, { icon: typeof Clock; bg: string; border: string; label: string }> = {
  long_silence: { icon: Clock, bg: 'bg-orange-50', border: 'border-orange-200', label: 'Silence' },
  no_attention: { icon: Eye, bg: 'bg-red-50', border: 'border-red-200', label: 'No Attention' },
  dominance_shift: { icon: RefreshCw, bg: 'bg-purple-50', border: 'border-purple-200', label: 'Shift' },
  rapid_exchange: { icon: Zap, bg: 'bg-blue-50', border: 'border-blue-200', label: 'Rapid' },
  overlap: { icon: RefreshCw, bg: 'bg-yellow-50', border: 'border-yellow-200', label: 'Overlap' },
};

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

export function InsightCards({ insights, onSeek }: Props) {
  if (insights.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Insights</h3>
        <p className="text-xs text-gray-400 text-center py-4">No insights detected</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">
        Auto-Detected Insights
        <span className="ml-2 text-xs font-normal text-gray-400">({insights.length})</span>
      </h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
        {insights.map((ins, i) => {
          const config = INSIGHT_CONFIG[ins.type] || INSIGHT_CONFIG.overlap;
          const Icon = config.icon;
          return (
            <button
              key={i}
              onClick={() => onSeek(ins.timestamp)}
              className={`text-left p-3 rounded-lg border ${config.border} ${config.bg} hover:shadow-sm transition-shadow`}
            >
              <div className="flex items-start gap-2">
                <Icon size={14} className="text-gray-500 mt-0.5 flex-shrink-0" />
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 mb-1">
                    <span className="text-[10px] font-semibold uppercase text-gray-500">
                      {config.label}
                    </span>
                    <span className="text-[10px] text-gray-400 bg-white px-1.5 py-0.5 rounded">
                      {formatTime(ins.timestamp)}
                    </span>
                    {ins.duration && (
                      <span className="text-[10px] text-gray-400">{ins.duration.toFixed(1)}s</span>
                    )}
                  </div>
                  <p className="text-xs text-gray-600 leading-snug line-clamp-2">
                    {ins.description}
                  </p>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
