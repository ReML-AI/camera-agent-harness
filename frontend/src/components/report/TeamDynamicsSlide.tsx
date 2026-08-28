import { InteractionAnalytics, MomentContext } from '@/types';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { SlideShell } from './SlideShell';

interface Props {
  analytics: InteractionAnalytics;
  moments: MomentContext[];
}

export function TeamDynamicsSlide({ analytics, moments }: Props) {
  const total = moments.length;
  const closedLoopCount = moments.filter(m => m.dynamics.closed_loop_detected).length;

  // Tag counts
  const tagCounts: Record<string, number> = {};
  for (const m of moments) {
    for (const tag of m.tags ?? []) {
      tagCounts[tag] = (tagCounts[tag] ?? 0) + 1;
    }
  }
  const directiveCount = tagCounts['directive_given'] ?? 0;
  const unansweredCount = tagCounts['question_unanswered'] ?? 0;
  const clAbsent = tagCounts['closed_loop_absent'] ?? 0;
  const monologues = tagCounts['monologue'] ?? 0;

  // Closed-loop interpretation
  const clRate = total > 0 ? closedLoopCount / total : 0;
  const clInterpretation = clRate < 0.2
    ? 'Critical gap \u2014 most directives went unconfirmed'
    : clRate < 0.5
      ? 'Below standard \u2014 inconsistent confirmation'
      : 'Adequate \u2014 team generally confirmed directives';

  // Turn-taking transitions — top 6
  const transitions = Object.entries(analytics.turn_taking.transitions)
    .map(([key, count]) => {
      const [from, to] = key.split('->').map(s => s.trim());
      const fromSpeaker = analytics.speakers[from];
      return {
        label: `${fromSpeaker?.label ?? from} \u2192 ${analytics.speakers[to]?.label ?? to}`,
        count,
        color: fromSpeaker?.color ?? '#94a3b8',
      };
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 6);

  // Top pair description for paragraph
  const topPair = transitions[0];

  // Bottom synthesized paragraph — concise
  const paragraphParts: string[] = [];
  if (topPair) {
    paragraphParts.push(`Dominated by ${topPair.label} exchanges (${topPair.count}x).`);
  }
  if (clAbsent > 0) {
    paragraphParts.push(`${clAbsent}/${total} moments lacked closed-loop.`);
  }
  if (monologues > 0) {
    paragraphParts.push(`${monologues} monologue${monologues !== 1 ? 's' : ''}.`);
  }
  if (unansweredCount > 3) {
    paragraphParts.push(`${unansweredCount} questions unanswered.`);
  }

  const avgGap = analytics.turn_taking.avg_gap_seconds;

  return (
    <SlideShell title="Team Dynamics" accent="border-purple-500">
      <div className="space-y-5">
        <div className="grid grid-cols-2 gap-8">
          {/* Left column — Communication Health */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Communication Health</p>
            <div className="space-y-3">
              {/* Closed-Loop Rate */}
              <div className="bg-white border border-gray-100 rounded-xl p-3">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">Closed-Loop Rate</span>
                  <span className="text-lg font-bold text-gray-900">{closedLoopCount} / {total}</span>
                </div>
                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-1.5">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(clRate * 100, 100)}%`,
                      backgroundColor: clRate < 0.2 ? '#ef4444' : clRate < 0.5 ? '#f59e0b' : '#22c55e',
                    }}
                  />
                </div>
                <p className="text-xs text-gray-500">{clInterpretation}</p>
              </div>

              {/* Directives Given */}
              <div className="bg-white border border-gray-100 rounded-xl p-3">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">Directives Given</span>
                  <span className="text-lg font-bold text-gray-900">{directiveCount}</span>
                </div>
                <p className="text-xs text-gray-500">{directiveCount} directive{directiveCount !== 1 ? 's' : ''} issued during critical moments</p>
              </div>

              {/* Unanswered Questions */}
              <div className="bg-white border border-gray-100 rounded-xl p-3">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">Unanswered Questions</span>
                  <span className="text-lg font-bold text-gray-900">{unansweredCount}</span>
                </div>
                <p className="text-xs text-gray-500">{unansweredCount} clinical question{unansweredCount !== 1 ? 's' : ''} received no response</p>
              </div>

              {/* Avg Response Gap */}
              <div className="bg-white border border-gray-100 rounded-xl p-3">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-sm font-medium text-gray-800">Avg Response Gap</span>
                  <span className="text-lg font-bold text-gray-900">{avgGap.toFixed(1)}s</span>
                </div>
                <p className="text-xs text-gray-500">between speaker turns</p>
              </div>
            </div>
          </div>

          {/* Right column — Conversation Flow */}
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Conversation Flow</p>
            {transitions.length > 0 ? (
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={transitions}
                  layout="vertical"
                  margin={{ left: 8, right: 24 }}
                >
                  <XAxis type="number" tick={{ fontSize: 10 }} />
                  <YAxis
                    type="category"
                    dataKey="label"
                    tick={{ fontSize: 10 }}
                    width={120}
                  />
                  <Tooltip formatter={(v) => [`${v} transitions`, 'Count']} />
                  <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                    {transitions.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-gray-400 italic">No turn-taking data available.</p>
            )}
          </div>
        </div>

        {/* Bottom synthesized paragraph */}
        {paragraphParts.length > 0 && (
          <div className="bg-purple-50 rounded-xl p-4">
            <p className="text-sm text-gray-700 leading-relaxed">{paragraphParts.join(' ')}</p>
          </div>
        )}
      </div>
    </SlideShell>
  );
}
