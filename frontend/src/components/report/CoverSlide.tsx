import { InteractionAnalytics } from '@/types';

interface Props {
  sessionId: string;
  analytics: InteractionAnalytics;
  totalMoments: number;
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}m ${s}s`;
}

export function CoverSlide({ sessionId, analytics, totalMoments }: Props) {
  const duration = analytics.timeline_segments.length
    ? analytics.timeline_segments.reduce((max, s) => (s.end > max ? s.end : max), 0)
    : 0;

  const speakers = Object.values(analytics.speakers);
  const criticalCount = totalMoments;
  const sessionNum = sessionId.replace('session_', '');

  return (
    <div className="h-full flex bg-white">
      {/* Left accent stripe */}
      <div className="w-2 bg-blue-600 flex-shrink-0" />

      {/* Main content */}
      <div className="flex-1 flex flex-col justify-between p-12">
        {/* Top — header area */}
        <div>
          <p className="text-xs font-semibold tracking-widest text-gray-400 uppercase mb-6">
            Clinical Simulation Debrief Report
          </p>

          <h1 className="text-7xl font-black text-gray-900 leading-none mb-2">
            Session {sessionNum}
          </h1>
          <p className="text-xl text-gray-400 font-light">
            {new Date().toLocaleDateString('en-AU', {
              weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
            })}
          </p>
        </div>

        {/* Middle — stats */}
        <div className="flex gap-6">
          {[
            { value: formatDuration(duration), label: 'Duration', color: '#2563EB' },
            { value: String(speakers.length), label: 'Participants', color: '#059669' },
            { value: String(criticalCount), label: 'Key Moments', color: '#D97706' },
          ].map(({ value, label, color }) => (
            <div key={label} className="border border-gray-200 rounded-xl p-5 min-w-[140px]">
              <div className="text-4xl font-bold mb-1" style={{ color }}>{value}</div>
              <p className="text-xs text-gray-500 font-medium tracking-wide uppercase">{label}</p>
            </div>
          ))}
        </div>

        {/* Bottom — participants */}
        <div>
          <p className="text-xs font-semibold tracking-widest text-gray-400 uppercase mb-3">
            Participants
          </p>
          <div className="flex flex-wrap gap-2.5">
            {speakers
              .sort((a, b) => (b.talk_percentage ?? 0) - (a.talk_percentage ?? 0))
              .map((spk, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 bg-gray-50"
                >
                  <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: spk.color }} />
                  <span className="text-sm font-semibold text-gray-800">{spk.label}</span>
                  <span className="text-xs text-gray-400">{Math.round(spk.talk_percentage ?? 0)}%</span>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Right decorative panel */}
      <div className="w-48 flex-shrink-0 bg-gray-50 border-l border-gray-100 flex flex-col items-center justify-center gap-6 p-4">
        <div className="text-center">
          <div className="text-3xl font-black text-gray-900">
            {Object.values(analytics.speakers)
              .filter(s => (s.talk_percentage ?? 0) > 20).length}
          </div>
          <p className="text-[10px] text-gray-400 uppercase tracking-wide mt-0.5">Active speakers</p>
        </div>
        <div className="w-px h-8 bg-gray-200" />
        <div className="text-center">
          <div className="text-3xl font-black text-blue-600">
            {Object.values(analytics.speakers)
              .reduce((sum, s) => sum + (s.segment_count ?? 0), 0)}
          </div>
          <p className="text-[10px] text-gray-400 uppercase tracking-wide mt-0.5">Speaking turns</p>
        </div>
        <div className="w-px h-8 bg-gray-200" />
        <div className="text-center">
          <div className="text-3xl font-black text-red-500">
            {/* will be passed as prop if needed — placeholder */}
            ✓
          </div>
          <p className="text-[10px] text-gray-400 uppercase tracking-wide mt-0.5">AI-analysed</p>
        </div>
      </div>
    </div>
  );
}
