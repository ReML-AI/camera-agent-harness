import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';
import { SpeakerInfo } from '@/types';

interface Props {
  speakers: Record<string, SpeakerInfo>;
  attentionReceived: Record<string, { avg_attention: number; samples: number }>;
}

export function AttentionChart({ speakers, attentionReceived }: Props) {
  const data = Object.entries(attentionReceived).map(([spk, info]) => ({
    name: speakers[spk]?.label || spk,
    attention: Math.round(info.avg_attention * 100),
    samples: info.samples,
    color: speakers[spk]?.color || '#6B7280',
  }));

  if (data.length === 0) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Attention Received</h3>
        <p className="text-xs text-gray-400 text-center py-8">No attention data available</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Attention Received While Speaking</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 10, right: 10 }}>
          <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} fontSize={10} />
          <YAxis type="category" dataKey="name" width={70} fontSize={11} />
          <Tooltip
            formatter={(value, _name, props) => [
              `${value}% (${(props.payload as any).samples} samples)`,
              'Attention',
            ]}
          />
          <Bar dataKey="attention" radius={[0, 4, 4, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
