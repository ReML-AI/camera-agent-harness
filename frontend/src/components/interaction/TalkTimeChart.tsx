import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from 'recharts';
import { SpeakerInfo } from '@/types';

interface Props {
  speakers: Record<string, SpeakerInfo>;
}

export function TalkTimeChart({ speakers }: Props) {
  const data = Object.entries(speakers).map(([id, info]) => ({
    name: info.label,
    value: info.total_talk_time,
    color: info.color,
    percentage: info.talk_percentage,
    segments: info.segment_count,
  }));

  const totalTime = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Talk Time Distribution</h3>
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            dataKey="value"
            stroke="none"
          >
            {data.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            formatter={(value, _name, props) => [
              `${Math.round(value as number)}s (${(props.payload as any).percentage}%)`,
              (props.payload as any).name,
            ]}
          />
          <Legend
            formatter={(value: string, entry: any) => {
              const item = data.find((d) => d.name === value);
              return (
                <span className="text-xs text-gray-600">
                  {value} — {item ? `${Math.round(item.value)}s` : ''}
                </span>
              );
            }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="text-center text-xs text-gray-400 -mt-2">
        Total: {Math.round(totalTime)}s ({Math.round(totalTime / 60)}m)
      </div>
    </div>
  );
}
