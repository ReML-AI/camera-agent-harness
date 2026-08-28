import { SpeakerInfo } from '@/types';

interface Props {
  speakers: Record<string, SpeakerInfo>;
  transitions: Record<string, number>;
  avgGap: number;
  avgOverlap: number;
}

export function TurnTakingFlow({ speakers, transitions, avgGap, avgOverlap }: Props) {
  const speakerIds = Object.keys(speakers);
  const maxCount = Math.max(...Object.values(transitions), 1);

  // Position speakers in a circle
  const cx = 120;
  const cy = 100;
  const radius = 65;
  const positions = speakerIds.map((_, i) => {
    const angle = (i / speakerIds.length) * 2 * Math.PI - Math.PI / 2;
    return { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Turn-Taking Flow</h3>
      <svg viewBox="0 0 240 200" className="w-full" style={{ maxHeight: 220 }}>
        {/* Arrows for transitions */}
        {Object.entries(transitions).map(([key, count]) => {
          const [fromId, toId] = key.split('->');
          const fromIdx = speakerIds.indexOf(fromId);
          const toIdx = speakerIds.indexOf(toId);
          if (fromIdx === -1 || toIdx === -1) return null;

          const from = positions[fromIdx];
          const to = positions[toIdx];
          const thickness = Math.max(1, (count / maxCount) * 6);
          const opacity = 0.3 + (count / maxCount) * 0.5;

          // Offset the line slightly so bidirectional arrows don't overlap
          const dx = to.x - from.x;
          const dy = to.y - from.y;
          const len = Math.sqrt(dx * dx + dy * dy);
          const nx = -dy / len * 4;
          const ny = dx / len * 4;

          // Shorten line to not overlap circles
          const shortenFrom = 18 / len;
          const shortenTo = 18 / len;
          const x1 = from.x + dx * shortenFrom + nx;
          const y1 = from.y + dy * shortenFrom + ny;
          const x2 = to.x - dx * shortenTo + nx;
          const y2 = to.y - dy * shortenTo + ny;

          return (
            <g key={key}>
              <line
                x1={x1} y1={y1} x2={x2} y2={y2}
                stroke={speakers[fromId]?.color || '#999'}
                strokeWidth={thickness}
                opacity={opacity}
                markerEnd="url(#arrowhead)"
              />
              <text
                x={(x1 + x2) / 2 + nx}
                y={(y1 + y2) / 2 + ny}
                fontSize={8}
                fill="#666"
                textAnchor="middle"
                dominantBaseline="middle"
              >
                {count}
              </text>
            </g>
          );
        })}

        {/* Speaker circles */}
        {speakerIds.map((spk, i) => {
          const pos = positions[i];
          const info = speakers[spk];
          return (
            <g key={spk}>
              <circle cx={pos.x} cy={pos.y} r={16} fill={info.color} opacity={0.9} />
              <text
                x={pos.x}
                y={pos.y}
                fontSize={9}
                fill="white"
                textAnchor="middle"
                dominantBaseline="middle"
                fontWeight="bold"
              >
                {info.label.split(' ')[1]}
              </text>
            </g>
          );
        })}

        {/* Arrow marker definition */}
        <defs>
          <marker id="arrowhead" markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
            <polygon points="0 0, 6 2, 0 4" fill="#666" />
          </marker>
        </defs>
      </svg>

      <div className="flex justify-around text-xs text-gray-500 mt-1">
        <span>Avg gap: {avgGap.toFixed(1)}s</span>
        <span>Avg overlap: {avgOverlap.toFixed(1)}s</span>
      </div>
    </div>
  );
}
