interface Props {
  /** team_gaze from MomentGaze: { patient: 12, monitor: 84, other: 4 } */
  gazeDistribution: Record<string, number>;
  width?: number;
}

const GAZE_COLORS: Record<string, string> = {
  patient: '#22c55e',
  monitor: '#3b82f6',
  person: '#a855f7',
  other: '#94a3b8',
};

const GAZE_LABELS: Record<string, string> = {
  patient: 'Patient',
  monitor: 'Monitor',
  person: 'Person',
  other: 'Other',
};

/**
 * Compact stacked bar showing where the team was looking during a moment.
 * Proves attention-related claims visually.
 */
export function GazeBar({ gazeDistribution, width = 200 }: Props) {
  const entries = Object.entries(gazeDistribution)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1]);

  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  if (total === 0) return null;

  return (
    <div style={{ width }}>
      {/* Stacked bar */}
      <div className="flex h-2.5 rounded-full overflow-hidden">
        {entries.map(([key, val]) => (
          <div
            key={key}
            style={{
              width: `${(val / total) * 100}%`,
              backgroundColor: GAZE_COLORS[key] ?? '#94a3b8',
            }}
            title={`${GAZE_LABELS[key] ?? key}: ${Math.round((val / total) * 100)}%`}
          />
        ))}
      </div>
      {/* Legend */}
      <div className="flex gap-2 mt-1">
        {entries.map(([key, val]) => (
          <span key={key} className="flex items-center gap-1">
            <span
              className="w-1.5 h-1.5 rounded-full inline-block"
              style={{ backgroundColor: GAZE_COLORS[key] ?? '#94a3b8' }}
            />
            <span className="text-[9px] text-gray-500">
              {GAZE_LABELS[key] ?? key} {Math.round((val / total) * 100)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
