import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { SpeakerInfo } from '@/types';

const TARGET_COLORS: Record<string, string> = {
  patient: '#EF4444',
  monitor: '#8B5CF6',
  other:   '#9CA3AF',
};

interface Props {
  speakers: Record<string, SpeakerInfo>;
  gazeAttention: Record<string, Record<string, number>>;
}

export function GazeDistribution({ speakers, gazeAttention }: Props) {
  const speakerEntries = Object.entries(gazeAttention).filter(([spk]) => speakers[spk]);

  if (speakerEntries.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Gaze Targets</h3>
        <p className="text-xs text-gray-400 text-center py-8">No gaze data — run classify_gaze_targets.py</p>
      </div>
    );
  }

  const allTargets = Array.from(
    new Set(speakerEntries.flatMap(([, summary]) => Object.keys(summary)))
  );

  const data = speakerEntries.map(([spk, summary]) => ({
    name: speakers[spk]?.label || spk,
    ...summary,
  }));

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Gaze Targets While Speaking</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 10 }}>
          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} fontSize={10} />
          <YAxis type="category" dataKey="name" width={70} fontSize={11} />
          <Tooltip formatter={(value) => `${value}%`} />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {allTargets.map((target) => (
            <Bar
              key={target}
              dataKey={target}
              stackId="a"
              fill={TARGET_COLORS[target] || '#60A5FA'}
              name={target.charAt(0).toUpperCase() + target.slice(1)}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
