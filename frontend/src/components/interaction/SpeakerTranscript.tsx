import { useEffect, useRef, useMemo } from 'react';
import { DiarizedSegment, SpeakerInfo } from '@/types';

interface Props {
  segments: DiarizedSegment[];
  speakers: Record<string, SpeakerInfo>;
  currentTime: number;
  onSeek: (time: number) => void;
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

export function SpeakerTranscript({ segments, speakers, currentTime, onSeek }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const lastScrolledIdx = useRef<number>(-1);
  // Track whether user is manually scrolling so we don't fight them
  const userScrolling = useRef(false);
  const userScrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Find active segment index — binary-search friendly since segments are sorted by start
  const activeIdx = useMemo(() => {
    for (let i = 0; i < segments.length; i++) {
      if (currentTime >= segments[i].start && currentTime <= segments[i].end) return i;
    }
    // Between segments — find the last one that started before currentTime
    for (let i = segments.length - 1; i >= 0; i--) {
      if (segments[i].start <= currentTime) return i;
    }
    return -1;
  }, [segments, currentTime]);

  // Scroll only when activeIdx changes (not every frame)
  useEffect(() => {
    if (activeIdx === -1 || activeIdx === lastScrolledIdx.current) return;
    if (userScrolling.current) return;

    const container = containerRef.current;
    const el = rowRefs.current[activeIdx];
    if (!container || !el) return;

    lastScrolledIdx.current = activeIdx;

    // Use getBoundingClientRect for accurate position relative to the scrollable container
    const containerRect = container.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const elRelTop = elRect.top - containerRect.top;
    const targetScrollTop = container.scrollTop + elRelTop - container.clientHeight / 3;

    container.scrollTo({ top: targetScrollTop, behavior: 'smooth' });
  }, [activeIdx]);

  // Detect manual user scroll — pause auto-scroll for 3s
  const handleScroll = () => {
    userScrolling.current = true;
    if (userScrollTimer.current) clearTimeout(userScrollTimer.current);
    userScrollTimer.current = setTimeout(() => {
      userScrolling.current = false;
    }, 3000);
  };

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="overflow-y-auto h-full space-y-0.5 pr-1"
    >
      {segments.map((seg, i) => {
        const info = speakers[seg.speaker];
        const isActive = i === activeIdx;
        const isPast = i < activeIdx;

        return (
          <div
            key={i}
            ref={el => { rowRefs.current[i] = el; }}
            className={`flex gap-2 px-2 py-1.5 rounded cursor-pointer transition-all duration-150 text-sm ${
              isActive
                ? 'bg-blue-50 ring-1 ring-blue-200'
                : 'hover:bg-gray-50'
            }`}
            onClick={() => onSeek(seg.start)}
          >
            {/* Speaker color bar */}
            <div
              className="w-0.5 rounded-full flex-shrink-0 self-stretch"
              style={{ backgroundColor: info?.color ?? '#6B7280', opacity: isPast ? 0.35 : 1 }}
            />

            <div className={`min-w-0 flex-1 transition-opacity duration-150 ${isPast ? 'opacity-40' : 'opacity-100'}`}>
              <div className="flex items-baseline gap-2">
                <span
                  className="text-[11px] font-semibold"
                  style={{ color: info?.color ?? '#6B7280' }}
                >
                  {info?.label ?? seg.speaker}
                </span>
                <span className="text-[10px] text-gray-400 tabular-nums">{formatTime(seg.start)}</span>
              </div>
              <p className={`text-xs leading-relaxed ${isActive ? 'text-gray-900 font-medium' : 'text-gray-600'}`}>
                {seg.text}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
