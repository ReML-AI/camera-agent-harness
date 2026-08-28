import { useRef, useMemo, useCallback } from 'react';
import { DiarizedSegment, SpeakerInfo, MomentContext, InteractionInsight } from '@/types';

interface Props {
  segments: DiarizedSegment[];
  speakers: Record<string, SpeakerInfo>;
  moments: MomentContext[];
  insights: InteractionInsight[];
  currentTime: number;
  totalDuration: number;
  selectedMomentId: number | null;
  starredMomentIds: number[];
  onSeek: (time: number) => void;
  onMomentSelect: (moment: MomentContext) => void;
}

const LANE_HEIGHT = 22;
const MARKER_ROW_HEIGHT = 28;
const INSIGHT_ROW_HEIGHT = 16;
const HEADER_WIDTH = 80;
const TIME_AXIS_HEIGHT = 20;

const INSIGHT_CONFIG: Record<string, { color: string; label: string }> = {
  no_attention:    { color: '#8B5CF6', label: 'No attention' },
  dominance_shift: { color: '#3B82F6', label: 'Dominance shift' },
  rapid_exchange:  { color: '#10B981', label: 'Rapid exchange' },
  overlap:         { color: '#EF4444', label: 'Overlap' },
};

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

interface MomentCluster {
  moments: MomentContext[];
  centerTimestamp: number;
  /** Representative moment — the most important one in the cluster */
  lead: MomentContext;
}

/** Group moments that are within `thresholdSecs` of each other into clusters */
function clusterMoments(moments: MomentContext[], thresholdSecs: number): MomentCluster[] {
  if (moments.length === 0) return [];
  const sorted = [...moments].sort((a, b) => a.timestamp - b.timestamp);
  const clusters: MomentCluster[] = [];
  let current: MomentContext[] = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const prev = sorted[i - 1];
    const curr = sorted[i];
    if (curr.timestamp - prev.timestamp <= thresholdSecs) {
      current.push(curr);
    } else {
      clusters.push(toCluster(current));
      current = [curr];
    }
  }
  clusters.push(toCluster(current));
  return clusters;
}

function toCluster(moments: MomentContext[]): MomentCluster {
  // Lead = critical first, then highest moment_id
  const lead = moments.find(m => m.importance === 'critical') ?? moments[0];
  const centerTimestamp =
    moments.reduce((sum, m) => sum + m.timestamp, 0) / moments.length;
  return { moments, centerTimestamp, lead };
}

export function MomentTimeline({
  segments, speakers, moments, insights, currentTime, totalDuration,
  selectedMomentId, starredMomentIds, onSeek, onMomentSelect,
}: Props) {
  const starredSet = useMemo(() => new Set(starredMomentIds), [starredMomentIds]);
  const containerRef = useRef<HTMLDivElement>(null);
  const speakerOrder = useMemo(() => Object.keys(speakers), [speakers]);

  const timeToX = useCallback((t: number) => (t / totalDuration) * 100, [totalDuration]);

  // Cluster threshold: ~2% of total duration (prevents visual overlap at typical widths)
  const clusterThreshold = totalDuration * 0.022;
  const clusters = useMemo(
    () => clusterMoments(moments, clusterThreshold),
    [moments, clusterThreshold],
  );

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - HEADER_WIDTH;
    const trackWidth = rect.width - HEADER_WIDTH;
    if (x > 0 && trackWidth > 0) {
      onSeek((x / trackWidth) * totalDuration);
    }
  };

  const currentX = timeToX(currentTime);

  const tickInterval = totalDuration > 600 ? 120 : totalDuration > 300 ? 60 : 30;
  const ticks = useMemo(() => {
    const arr: number[] = [];
    for (let t = 0; t <= totalDuration; t += tickInterval) arr.push(t);
    return arr;
  }, [totalDuration, tickInterval]);

  const filteredInsights = useMemo(
    () => insights.filter(ins => ins.type !== 'long_silence'),
    [insights],
  );
  const hasInsights = filteredInsights.length > 0;
  const totalHeight =
    MARKER_ROW_HEIGHT +
    speakerOrder.length * LANE_HEIGHT +
    (hasInsights ? INSIGHT_ROW_HEIGHT : 0) +
    TIME_AXIS_HEIGHT;

  return (
    <div className="bg-white rounded-lg border border-gray-200 px-3 py-2">
      <div
        ref={containerRef}
        className="relative cursor-crosshair select-none"
        style={{ height: totalHeight }}
        onClick={handleTimelineClick}
      >
        {/* ── Moment clusters row ── */}
        <div
          className="absolute flex items-center"
          style={{ top: 0, left: HEADER_WIDTH, right: 0, height: MARKER_ROW_HEIGHT }}
        >
          {clusters.map((cluster, ci) => {
            const { lead, moments: clusterMoments, centerTimestamp } = cluster;
            const isSelected = clusterMoments.some(m => m.moment_id === selectedMomentId);
            const isCritical = clusterMoments.some(m => m.importance === 'critical');
            const hasStarred = clusterMoments.some(m => starredSet.has(m.moment_id));
            const hasNarrative = clusterMoments.some(m => Boolean(m.narrative));
            const count = clusterMoments.length;
            const isMulti = count > 1;

            const tooltipLines = clusterMoments
              .map(m => `${m.category} @ ${formatTime(m.timestamp)}`)
              .join('\n');

            return (
              <div
                key={ci}
                className="absolute cursor-pointer"
                style={{
                  left: `${timeToX(centerTimestamp)}%`,
                  top: '50%',
                  transform: `translateX(-50%) translateY(-50%) ${isSelected ? 'scale(1.45)' : 'scale(1)'}`,
                  transition: 'transform 0.15s',
                  zIndex: isSelected ? 20 : 10,
                }}
                onClick={(e) => { e.stopPropagation(); onMomentSelect(lead); }}
                title={tooltipLines}
              >
                {/* Star indicator */}
                {hasStarred && (
                  <div className="absolute" style={{ top: -9, left: '50%', transform: 'translateX(-50%)' }}>
                    <svg width="6" height="6" viewBox="0 0 6 6">
                      <polygon points="3,0 3.7,2.2 6,2.2 4.1,3.5 4.8,5.8 3,4.5 1.2,5.8 1.9,3.5 0,2.2 2.3,2.2" fill="#F59E0B" />
                    </svg>
                  </div>
                )}

                {/* Diamond — bigger when multi-moment cluster */}
                <svg
                  width={isMulti ? 16 : 12}
                  height={isMulti ? 16 : 12}
                  viewBox="0 0 12 12"
                  style={{ display: 'block' }}
                >
                  <path
                    d="M6 1 L11 6 L6 11 L1 6 Z"
                    fill={isCritical ? '#EF4444' : '#F59E0B'}
                    fillOpacity={hasNarrative ? 1 : 0.45}
                    stroke={isSelected ? '#1D4ED8' : 'white'}
                    strokeWidth={isSelected ? 2 : 1}
                  />
                </svg>

                {/* Cluster count badge */}
                {isMulti && (
                  <div
                    className="absolute text-white font-bold"
                    style={{
                      top: -5,
                      right: -7,
                      fontSize: 8,
                      lineHeight: '12px',
                      minWidth: 12,
                      height: 12,
                      borderRadius: 6,
                      backgroundColor: isCritical ? '#EF4444' : '#F59E0B',
                      textAlign: 'center',
                      paddingInline: 2,
                      border: '1px solid white',
                    }}
                  >
                    {count}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* ── Speaker swim lanes ── */}
        {speakerOrder.map((spk, i) => {
          const info = speakers[spk];
          const top = MARKER_ROW_HEIGHT + i * LANE_HEIGHT;
          return (
            <div
              key={spk}
              className="absolute flex items-center"
              style={{ top, height: LANE_HEIGHT, left: 0, right: 0 }}
            >
              <div
                className="text-[10px] font-medium text-gray-500 flex-shrink-0 truncate flex items-center gap-1"
                style={{ width: HEADER_WIDTH }}
              >
                <span className="inline-block w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: info.color }} />
                {info.label}
              </div>
              <div className="flex-1 relative h-4 bg-gray-50 rounded-sm">
                {segments
                  .filter((s) => s.speaker === spk)
                  .map((seg, j) => (
                    <div
                      key={j}
                      className="absolute top-0 h-full rounded-sm opacity-70 hover:opacity-100 transition-opacity"
                      style={{
                        left: `${timeToX(seg.start)}%`,
                        width: `${Math.max(timeToX(seg.end - seg.start), 0.2)}%`,
                        backgroundColor: info.color,
                      }}
                    />
                  ))}
              </div>
            </div>
          );
        })}

        {/* ── Insight markers ── */}
        {hasInsights && (
          <div
            className="absolute flex items-center"
            style={{
              top: MARKER_ROW_HEIGHT + speakerOrder.length * LANE_HEIGHT,
              left: HEADER_WIDTH,
              right: 0,
              height: INSIGHT_ROW_HEIGHT,
            }}
          >
            <div
              className="absolute text-[9px] text-gray-400 flex items-center"
              style={{ left: -HEADER_WIDTH, width: HEADER_WIDTH }}
            >
              Insights
            </div>
            {filteredInsights.map((ins, i) => {
              const cfg = INSIGHT_CONFIG[ins.type] ?? { color: '#6B7280', label: ins.type };
              return (
                <div
                  key={i}
                  className="absolute cursor-default group"
                  style={{ left: `${timeToX(ins.timestamp)}%`, transform: 'translateX(-50%)' }}
                  title={ins.description}
                  onClick={(e) => { e.stopPropagation(); onSeek(ins.timestamp); }}
                >
                  <div className="w-2 h-2 rounded-full cursor-pointer" style={{ backgroundColor: cfg.color }} />
                  <div className="absolute bottom-3 left-1/2 -translate-x-1/2 hidden group-hover:block bg-gray-800 text-white text-[9px] rounded px-1.5 py-0.5 whitespace-nowrap z-50 pointer-events-none">
                    {cfg.label}: {ins.description.slice(0, 60)}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* ── Current time indicator ── */}
        <div
          className="absolute w-0.5 bg-blue-600 z-30 pointer-events-none"
          style={{
            left: `calc(${HEADER_WIDTH}px + (100% - ${HEADER_WIDTH}px) * ${currentX / 100})`,
            top: 0,
            height: MARKER_ROW_HEIGHT + speakerOrder.length * LANE_HEIGHT + (hasInsights ? INSIGHT_ROW_HEIGHT : 0),
          }}
        >
          <div className="absolute -top-0 left-1 bg-blue-600 text-white text-[9px] px-1 rounded whitespace-nowrap">
            {formatTime(currentTime)}
          </div>
        </div>

        {/* ── Time axis ── */}
        <div
          className="absolute text-[10px] text-gray-400"
          style={{
            top: MARKER_ROW_HEIGHT + speakerOrder.length * LANE_HEIGHT + (hasInsights ? INSIGHT_ROW_HEIGHT : 0) + 4,
            left: HEADER_WIDTH,
            right: 0,
            height: TIME_AXIS_HEIGHT,
          }}
        >
          {ticks.map((t) => (
            <span key={t} className="absolute" style={{ left: `${timeToX(t)}%`, transform: 'translateX(-50%)' }}>
              {formatTime(t)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
