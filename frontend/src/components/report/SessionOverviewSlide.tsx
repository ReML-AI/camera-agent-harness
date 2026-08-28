import { InteractionAnalytics, MomentContext } from '@/types';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  ScatterChart, Scatter, ZAxis,
} from 'recharts';
import { SlideShell } from './SlideShell';

interface Props {
  analytics: InteractionAnalytics;
  moments: MomentContext[];
  starredMomentIds: number[];
}

export function SessionOverviewSlide({ analytics, moments, starredMomentIds }: Props) {
  const duration = analytics.timeline_segments.length
    ? analytics.timeline_segments.reduce((max, s) => (s.end > max ? s.end : max), 0)
    : 0;

  const criticalCount = moments.filter(m => m.importance === 'critical').length;
  const highCount = moments.filter(m => m.importance === 'high').length;

  const talkData = Object.entries(analytics.speakers).map(([, spk]) => ({
    name: spk.label,
    pct: Math.round(spk.talk_percentage ?? 0),
    color: spk.color,
  })).sort((a, b) => b.pct - a.pct);

  const formatDur = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const formatMmSs = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

  // Compute synthesized summary values
  const closedLoopCount = moments.filter(m => m.dynamics.closed_loop_detected).length;
  const closedLoopRate = moments.length > 0 ? ((closedLoopCount / moments.length) * 100).toFixed(1) : '0';
  const criticalPct = moments.length > 0 ? Math.round((criticalCount / moments.length) * 100) : 0;

  const dominantSpeaker = talkData.length > 0 ? talkData[0] : null;

  const closedLoopInterpretation = parseFloat(closedLoopRate) < 20
    ? 'significant gaps in'
    : parseFloat(closedLoopRate) < 50
      ? 'inconsistent'
      : 'generally adequate';

  const summaryText = [
    `This ${formatDur(duration)} session captured ${moments.length} key moments, ${criticalPct}% of which were critical.`,
    dominantSpeaker ? `${dominantSpeaker.name} led the conversation at ${dominantSpeaker.pct}% talk time.` : '',
    `Closed-loop communication was confirmed in ${closedLoopCount} of ${moments.length} moments (${closedLoopRate}%), suggesting ${closedLoopInterpretation} directive acknowledgment.`,
  ].filter(Boolean).join(' ');

  // Scatter timeline data
  const scatterData = moments.map(m => ({
    x: m.timestamp,
    y: m.importance === 'critical' ? 2 : 1,
    size: starredMomentIds.includes(m.moment_id) ? 120 : 50,
    fill: m.importance === 'critical' ? '#ef4444' : '#f59e0b',
    label: formatMmSs(m.timestamp),
    momentId: m.moment_id,
  }));

  return (
    <SlideShell title="Session Overview" accent="border-blue-500">
      <div className="grid grid-cols-2 gap-8 h-full">
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-4">
            {[
              { label: 'Duration', value: formatDur(duration), color: 'bg-blue-50 text-blue-800' },
              { label: 'Total Moments', value: String(moments.length), color: 'bg-gray-50 text-gray-800' },
              { label: 'Critical', value: String(criticalCount), color: 'bg-red-50 text-red-800' },
              { label: 'High Priority', value: String(highCount), color: 'bg-amber-50 text-amber-800' },
            ].map(({ label, value, color }) => (
              <div key={label} className={`rounded-xl p-4 ${color}`}>
                <p className="text-3xl font-bold">{value}</p>
                <p className="text-xs font-medium opacity-70 mt-1">{label}</p>
              </div>
            ))}
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Session Summary</p>
            <p className="text-sm text-gray-700 leading-relaxed">{summaryText}</p>
          </div>
        </div>

        <div className="space-y-6">
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Talk Time</p>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={talkData} layout="vertical" margin={{ left: 8, right: 32 }}>
                <XAxis type="number" domain={[0, 100]} tickFormatter={v => `${v}%`} tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} width={80} />
                <Tooltip formatter={(v) => [`${v}%`, 'Talk time']} />
                <Bar dataKey="pct" radius={[0, 4, 4, 0]}>
                  {talkData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Moment Timeline</p>
            <ResponsiveContainer width="100%" height={120}>
              <ScatterChart margin={{ left: 8, right: 8, top: 8, bottom: 4 }}>
                <XAxis
                  dataKey="x"
                  type="number"
                  domain={['dataMin', 'dataMax']}
                  tickFormatter={formatMmSs}
                  tick={{ fontSize: 10 }}
                  name="Time"
                />
                <YAxis
                  dataKey="y"
                  type="number"
                  domain={[0.5, 2.5]}
                  ticks={[1, 2]}
                  tickFormatter={v => v === 2 ? 'Critical' : 'High'}
                  tick={{ fontSize: 10 }}
                  width={50}
                />
                <ZAxis dataKey="size" range={[50, 120]} />
                <Tooltip
                  formatter={(_v: any, name?: string) => {
                    if (name === 'x') return [formatMmSs(_v as number), 'Time'];
                    if (name === 'y') return [_v === 2 ? 'Critical' : 'High', 'Priority'];
                    return _v;
                  }}
                  labelFormatter={() => ''}
                />
                <Scatter data={scatterData} isAnimationActive={false}>
                  {scatterData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </SlideShell>
  );
}
