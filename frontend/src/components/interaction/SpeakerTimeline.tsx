import { useRef, useMemo } from 'react';
import { DiarizedSegment, SpeakerInfo, InteractionInsight } from '@/types';

interface Props {
  segments: DiarizedSegment[];
  speakers: Record<string, SpeakerInfo>;
  insights: InteractionInsight[];
  currentTime: number;
  totalDuration: number;
  onSeek: (time: number) => void;
}

const INSIGHT_ICONS: Record<string, string> = {
  long_silence: '⏸',
  rapid_exchange: '⚡',
  dominance_shift: '🔄',
  no_attention: '👁',
  overlap: '🔀',
};

export function SpeakerTimeline({ segments, speakers, insights, currentTime, totalDuration, onSeek }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  const speakerOrder = useMemo(() => Object.keys(speakers), [speakers]);
  const laneHeight = 28;
  const headerWidth = 90;

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - headerWidth;
    const width = rect.width - headerWidth;
    if (x > 0 && width > 0) {
      const time = (x / width) * totalDuration;
      onSeek(time);
    }
  };

  const timeToPercent = (t: number) => (t / totalDuration) * 100;
  const currentPercent = timeToPercent(currentTime);

  // Time axis labels
  const tickCount = 10;
  const tickInterval = totalDuration / tickCount;
  const ticks = Array.from({ length: tickCount + 1 }, (_, i) => i * tickInterval);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-3">Speaker Timeline</h3>
      <div
        ref={containerRef}
        className="relative cursor-crosshair select-none"
        onClick={handleClick}
        style={{ height: speakerOrder.length * laneHeight + 30 }}
      >
        {/* Speaker lanes */}
        {speakerOrder.map((spk, i) => {
          const info = speakers[spk];
          return (
            <div
              key={spk}
              className="absolute flex items-center"
              style={{ top: i * laneHeight, height: laneHeight, left: 0, right: 0 }}
            >
              {/* Label */}
              <div
                className="text-xs font-medium text-gray-600 flex-shrink-0 truncate"
                style={{ width: headerWidth }}
              >
                <span
                  className="inline-block w-2.5 h-2.5 rounded-full mr-1.5"
                  style={{ backgroundColor: info.color }}
                />
                {info.label}
              </div>

              {/* Lane background */}
              <div className="flex-1 relative h-5 bg-gray-50 rounded-sm">
                {/* Segments */}
                {segments
                  .filter((s) => s.speaker === spk)
                  .map((seg, j) => (
                    <div
                      key={j}
                      className="absolute top-0 h-full rounded-sm opacity-80 hover:opacity-100 transition-opacity"
                      style={{
                        left: `${timeToPercent(seg.start)}%`,
                        width: `${Math.max(timeToPercent(seg.end - seg.start), 0.3)}%`,
                        backgroundColor: info.color,
                      }}
                      title={`${seg.text.slice(0, 80)} (${formatTime(seg.start)} - ${formatTime(seg.end)})`}
                    />
                  ))}
              </div>
            </div>
          );
        })}

        {/* Insight markers */}
        {insights.map((ins, i) => (
          <div
            key={i}
            className="absolute z-10 text-xs cursor-pointer hover:scale-125 transition-transform"
            style={{
              left: `calc(${headerWidth}px + ${timeToPercent(ins.timestamp)}% * (100% - ${headerWidth}px) / 100)`,
              bottom: 2,
              transform: 'translateX(-50%)',
            }}
            title={ins.description}
            onClick={(e) => {
              e.stopPropagation();
              onSeek(ins.timestamp);
            }}
          >
            {INSIGHT_ICONS[ins.type] || '◆'}
          </div>
        ))}

        {/* Current time indicator */}
        <div
          className="absolute top-0 w-0.5 bg-red-500 z-20 pointer-events-none"
          style={{
            left: `calc(${headerWidth}px + (100% - ${headerWidth}px) * ${currentPercent / 100})`,
            height: speakerOrder.length * laneHeight,
          }}
        />

        {/* Time axis */}
        <div
          className="absolute flex justify-between text-[10px] text-gray-400"
          style={{
            top: speakerOrder.length * laneHeight + 4,
            left: headerWidth,
            right: 0,
          }}
        >
          {ticks.map((t, i) => (
            <span key={i}>{formatTime(t)}</span>
          ))}
        </div>
      </div>
    </div>
  );
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}
