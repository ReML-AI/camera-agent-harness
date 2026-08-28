import { useRef, useEffect, useCallback, useState } from 'react';
import { VideoOverlayData, OverlayKeyframe, OverlayPerson, OverlayPersonMeta } from '@/types';
import { Eye, Volume2, Square } from 'lucide-react';

interface Props {
  videoRef: React.RefObject<HTMLVideoElement>;
  overlayData: VideoOverlayData;
  containerWidth: number;
  containerHeight: number;
}

interface OverlayLayers {
  gaze: boolean;
  speaker: boolean;
  boxes: boolean;
}

const SPEAKER_COLORS: Record<string, string> = {
  SPEAKER_00: '#3B82F6',
  SPEAKER_01: '#10B981',
  SPEAKER_02: '#F59E0B',
  SPEAKER_03: '#A855F7',
};

const ROLE_COLORS: Record<string, string> = {
  'Student Nurse (Primary)': '#10B981',
  'Supervising Nurse/Doctor': '#3B82F6',
  'Patient/Mannequin': '#F59E0B',
  'Observer/Other': '#6B7280',
};

function getPersonColor(person: OverlayPerson, personsMeta: Record<string, OverlayPersonMeta>): string {
  if (person.personId.startsWith('SPEAKER_')) return SPEAKER_COLORS[person.personId] ?? '#6B7280';
  const meta = personsMeta[person.personId];
  return meta ? (ROLE_COLORS[meta.role] ?? meta.color ?? '#6B7280') : '#6B7280';
}

function getPersonLabel(person: OverlayPerson, personsMeta: Record<string, OverlayPersonMeta>): string {
  if (person.personId.startsWith('SPEAKER_')) {
    const num = parseInt(person.personId.split('_')[1]) + 1;
    return `Speaker ${String.fromCharCode(64 + num)}`;
  }
  const meta = personsMeta[person.personId];
  return meta ? (meta.label ?? meta.role) : person.personId;
}

function findNearestKeyframe(keyframes: OverlayKeyframe[], targetFrame: number): OverlayKeyframe | null {
  if (!keyframes.length) return null;
  let lo = 0, hi = keyframes.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (keyframes[mid].frame < targetFrame) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0 && targetFrame - keyframes[lo - 1].frame <= keyframes[lo].frame - targetFrame) {
    return keyframes[lo - 1];
  }
  return keyframes[lo];
}

/**
 * Compute where the video content actually renders inside the element when
 * CSS object-fit: contain is used.
 */
function getContentRect(
  containerW: number, containerH: number,
  videoW: number, videoH: number,
): { x: number; y: number; w: number; h: number } {
  if (!videoW || !videoH) return { x: 0, y: 0, w: containerW, h: containerH };
  const containerRatio = containerW / containerH;
  const videoRatio    = videoW / videoH;
  let w: number, h: number;
  if (containerRatio > videoRatio) {
    // Container wider — letterbox left/right
    h = containerH;
    w = h * videoRatio;
  } else {
    // Container taller — pillarbox top/bottom
    w = containerW;
    h = w / videoRatio;
  }
  return { x: (containerW - w) / 2, y: (containerH - h) / 2, w, h };
}

export function VideoOverlay({ videoRef, overlayData, containerWidth, containerHeight }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [layers, setLayers] = useState<OverlayLayers>({ gaze: true, speaker: true, boxes: true });
  // Keep a ref so drawOverlay always sees latest layers without triggering re-subscriptions
  const layersRef = useRef(layers);
  useEffect(() => { layersRef.current = layers; }, [layers]);

  const drawOverlay = useCallback(
    (ctx: CanvasRenderingContext2D, keyframe: OverlayKeyframe, videoW: number, videoH: number) => {
      ctx.clearRect(0, 0, containerWidth, containerHeight);

      if (!keyframe.persons.length && !keyframe.isCriticalMoment) return;

      // Map normalized bbox coords → actual canvas coords using object-contain rect
      const rect = getContentRect(containerWidth, containerHeight, videoW, videoH);

      // Critical moment border
      if (keyframe.isCriticalMoment) {
        const alpha = 0.4 + 0.3 * Math.sin(Date.now() / 300);
        ctx.strokeStyle = `rgba(239,68,68,${alpha})`;
        ctx.lineWidth = 4;
        ctx.strokeRect(2, 2, containerWidth - 4, containerHeight - 4);
        ctx.fillStyle = 'rgba(239,68,68,0.85)';
        ctx.font = 'bold 11px system-ui, sans-serif';
        const label = 'CRITICAL MOMENT';
        const tw = ctx.measureText(label).width;
        ctx.fillRect(containerWidth - tw - 16, 4, tw + 12, 20);
        ctx.fillStyle = '#fff';
        ctx.fillText(label, containerWidth - tw - 10, 18);
      }

      const l = layersRef.current;

      for (const person of keyframe.persons) {
        const color = getPersonColor(person, overlayData.persons);
        // Map normalized (0–1) coords to canvas coords via content rect
        const x1 = rect.x + person.bbox.x1 * rect.w;
        const y1 = rect.y + person.bbox.y1 * rect.h;
        const x2 = rect.x + person.bbox.x2 * rect.w;
        const y2 = rect.y + person.bbox.y2 * rect.h;
        const w  = x2 - x1;
        const h  = y2 - y1;

        // Bounding box
        if (l.boxes) {
          ctx.strokeStyle = color;
          ctx.lineWidth = 2;
          ctx.strokeRect(x1, y1, w, h);

          const label = getPersonLabel(person, overlayData.persons);
          ctx.font = 'bold 10px system-ui, sans-serif';
          const tw = ctx.measureText(label).width;
          ctx.fillStyle = color;
          ctx.fillRect(x1, Math.max(0, y1 - 16), tw + 8, 16);
          ctx.fillStyle = '#fff';
          ctx.fillText(label, x1 + 4, Math.max(12, y1 - 4));
        }

        // Speaker: pulsing dashed border
        if (l.speaker && person.isSpeaking) {
          const pulse = 0.5 + 0.5 * Math.sin(Date.now() / 200);
          ctx.strokeStyle = `rgba(239,68,68,${0.6 + 0.4 * pulse})`;
          ctx.lineWidth = 3;
          ctx.setLineDash([8, 4]);
          ctx.strokeRect(x1 - 4, y1 - 20, w + 8, h + 24);
          ctx.setLineDash([]);
          ctx.fillStyle = '#EF4444';
          ctx.beginPath();
          ctx.arc(x2 + 6, y1 - 4, 5, 0, Math.PI * 2);
          ctx.fill();
        }

        // Gaze arrow
        if (l.gaze && person.headPose) {
          const { yaw } = person.headPose;
          const cx = x1 + w / 2;
          const cy = y1 + h / 2;
          const arrowLen = Math.min(w, h) * 1.2;
          const rad = (yaw * Math.PI) / 180;
          const ex = cx + Math.sin(rad) * arrowLen;
          const ey = cy;
          const angle = Math.atan2(ey - cy, ex - cx);
          ctx.strokeStyle = '#F97316';
          ctx.lineWidth = 2;
          ctx.globalAlpha = 0.9;
          ctx.beginPath();
          ctx.moveTo(cx, cy);
          ctx.lineTo(ex, ey);
          ctx.stroke();
          ctx.beginPath();
          ctx.moveTo(ex, ey);
          ctx.lineTo(ex - 8 * Math.cos(angle - Math.PI / 6), ey - 8 * Math.sin(angle - Math.PI / 6));
          ctx.moveTo(ex, ey);
          ctx.lineTo(ex - 8 * Math.cos(angle + Math.PI / 6), ey - 8 * Math.sin(angle + Math.PI / 6));
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
      }
    },
    [containerWidth, containerHeight, overlayData.persons],
  );

  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const drawAtTime = (t: number) => {
      const frame = Math.round(t * overlayData.fps);
      const kf = findNearestKeyframe(overlayData.keyframes, frame);
      if (kf) {
        drawOverlay(ctx, kf, video.videoWidth || 960, video.videoHeight || 540);
      } else {
        ctx.clearRect(0, 0, containerWidth, containerHeight);
      }
    };

    // Draw once immediately (handles already-loaded / paused state)
    drawAtTime(video.currentTime);

    let rvcId: number;

    if ('requestVideoFrameCallback' in video) {
      // rVFC: fires on every decoded frame while playing — precise sync
      const onVideoFrame = (_: number, meta: { mediaTime: number }) => {
        drawAtTime(meta.mediaTime);
        rvcId = (video as any).requestVideoFrameCallback(onVideoFrame);
      };
      rvcId = (video as any).requestVideoFrameCallback(onVideoFrame);

      // Also redraw on seek/pause so overlay doesn't disappear when video is still
      const redraw = () => drawAtTime(video.currentTime);
      video.addEventListener('seeked',      redraw);
      video.addEventListener('pause',       redraw);
      video.addEventListener('loadeddata',  redraw);

      return () => {
        (video as any).cancelVideoFrameCallback(rvcId);
        video.removeEventListener('seeked',     redraw);
        video.removeEventListener('pause',      redraw);
        video.removeEventListener('loadeddata', redraw);
      };
    } else {
      // rAF fallback — draw every frame regardless of play/pause state
      const vid = video as HTMLVideoElement;
      let animId: number;
      const onFrame = () => {
        drawAtTime(vid.currentTime);
        animId = requestAnimationFrame(onFrame);
      };
      animId = requestAnimationFrame(onFrame);
      return () => cancelAnimationFrame(animId);
    }
  }, [videoRef, overlayData, drawOverlay, containerWidth, containerHeight]);

  const toggleLayer = (layer: keyof OverlayLayers) =>
    setLayers(prev => ({ ...prev, [layer]: !prev[layer] }));

  return (
    <>
      <canvas
        ref={canvasRef}
        width={containerWidth}
        height={containerHeight}
        style={{ position: 'absolute', top: 0, left: 0, pointerEvents: 'none' }}
      />

      {/* Toggle buttons */}
      <div className="absolute bottom-10 left-2 flex gap-1" style={{ pointerEvents: 'auto' }}>
        {([
          { key: 'boxes'   as const, icon: Square,   label: 'Boxes' },
          { key: 'gaze'    as const, icon: Eye,       label: 'Gaze'  },
          { key: 'speaker' as const, icon: Volume2,   label: 'Speaker' },
        ] as const).map(({ key, icon: Icon, label }) => (
          <button
            key={key}
            onClick={() => toggleLayer(key)}
            title={`Toggle ${label}`}
            className={`flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors ${
              layers[key]
                ? 'bg-blue-600 text-white'
                : 'bg-black/60 text-gray-300 hover:bg-black/80'
            }`}
          >
            <Icon size={10} />
            {label}
          </button>
        ))}
      </div>
    </>
  );
}
