import { OverlayKeyframe, OverlayPersonMeta } from '@/types';

interface Props {
  keyframe: OverlayKeyframe;
  personMeta: Record<string, OverlayPersonMeta>;
  width?: number;
  height?: number;
  /** Optional: highlight a specific person by ID */
  highlightPerson?: string;
}

/**
 * SVG "video frame" showing person positions, gaze arrows, and speaker indicators
 * from an overlay keyframe. Looks like an annotated screenshot.
 */
export function EvidenceScene({
  keyframe,
  personMeta,
  width = 280,
  height = 158,
  highlightPerson,
}: Props) {
  const persons = keyframe.persons;
  if (!persons || persons.length === 0) {
    return (
      <div
        className="rounded-lg bg-gray-800 flex items-center justify-center"
        style={{ width, height }}
      >
        <span className="text-[10px] text-gray-500">No visual data</span>
      </div>
    );
  }

  // Map normalized bbox coords (0-1) to SVG coords with padding
  const pad = 8;
  const sw = width - pad * 2;
  const sh = height - pad * 2;

  const toX = (n: number) => pad + n * sw;
  const toY = (n: number) => pad + n * sh;

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="rounded-lg flex-shrink-0"
      style={{ background: '#1a1a2e' }}
    >
      {/* Subtle grid lines for depth */}
      <line x1={0} y1={height * 0.5} x2={width} y2={height * 0.5} stroke="#ffffff08" strokeWidth={0.5} />
      <line x1={width * 0.5} y1={0} x2={width * 0.5} y2={height} stroke="#ffffff08" strokeWidth={0.5} />

      {persons.map((person) => {
        const meta = personMeta[person.personId];
        const color = meta?.color ?? '#94a3b8';
        const label = meta?.label ?? person.personId;

        const x1 = toX(person.bbox.x1);
        const y1 = toY(person.bbox.y1);
        const x2 = toX(person.bbox.x2);
        const y2 = toY(person.bbox.y2);
        const bw = x2 - x1;
        const bh = y2 - y1;
        const cx = x1 + bw / 2;
        const cy = y1 + bh / 2;

        const isHighlighted = highlightPerson === person.personId;
        const strokeW = isHighlighted ? 2.5 : 1.5;
        const opacity = highlightPerson && !isHighlighted ? 0.3 : 1;

        // Gaze arrow from head pose
        let gazeArrow = null;
        if (person.headPose) {
          const yaw = person.headPose.yaw;
          const pitch = person.headPose.pitch;
          const arrowLen = Math.max(bw, bh) * 0.8;
          const endX = cx + Math.sin((yaw * Math.PI) / 180) * arrowLen;
          const endY = cy - Math.sin((pitch * Math.PI) / 180) * arrowLen * 0.5;

          gazeArrow = (
            <line
              x1={cx}
              y1={cy}
              x2={endX}
              y2={endY}
              stroke="#f97316"
              strokeWidth={1.5}
              opacity={opacity}
              markerEnd="url(#arrowhead)"
            />
          );
        }

        return (
          <g key={person.personId} opacity={opacity}>
            {/* Person bounding box */}
            <rect
              x={x1}
              y={y1}
              width={bw}
              height={bh}
              fill={`${color}15`}
              stroke={color}
              strokeWidth={strokeW}
              rx={3}
            />

            {/* Label */}
            <text
              x={cx}
              y={y2 + 10}
              textAnchor="middle"
              fill={color}
              fontSize={8}
              fontWeight={600}
              fontFamily="system-ui, sans-serif"
            >
              {label.length > 12 ? label.slice(0, 10) + '..' : label}
            </text>

            {/* Speaker indicator */}
            {person.isSpeaking && (
              <>
                <circle cx={x2 - 4} cy={y1 + 4} r={4} fill="#ef4444" opacity={0.9} />
                <circle cx={x2 - 4} cy={y1 + 4} r={6} fill="none" stroke="#ef4444" strokeWidth={1} opacity={0.5}>
                  <animate attributeName="r" values="6;9;6" dur="1.5s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.5;0;0.5" dur="1.5s" repeatCount="indefinite" />
                </circle>
              </>
            )}

            {/* Gaze arrow */}
            {gazeArrow}
          </g>
        );
      })}

      {/* Arrow marker definition */}
      <defs>
        <marker id="arrowhead" markerWidth={6} markerHeight={4} refX={5} refY={2} orient="auto">
          <polygon points="0 0, 6 2, 0 4" fill="#f97316" />
        </marker>
      </defs>

      {/* Critical moment border */}
      {keyframe.isCriticalMoment && (
        <rect
          x={1}
          y={1}
          width={width - 2}
          height={height - 2}
          fill="none"
          stroke="#ef4444"
          strokeWidth={2}
          rx={8}
          opacity={0.6}
        />
      )}

      {/* Timestamp badge */}
      <rect x={width - 48} y={4} width={44} height={16} rx={4} fill="#00000080" />
      <text x={width - 26} y={15} textAnchor="middle" fill="#ffffffcc" fontSize={9} fontFamily="monospace">
        {formatTs(keyframe.timestamp)}
      </text>
    </svg>
  );
}

function formatTs(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}
