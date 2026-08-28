import { useSessionStore } from '@/stores/sessionStore';
import { useRef, useEffect, useState, useCallback, forwardRef, useImperativeHandle } from 'react';
import { api } from '@/services/api';
import { VideoOverlayData } from '@/types';
import { VideoOverlay } from './VideoOverlay';
import { Maximize2, Minimize2, Grid3x3, Camera } from 'lucide-react';

const CAMERAS = ['cam1', 'cam2', 'cam3', 'monitor'] as const;
type CameraId = typeof CAMERAS[number];

const CAMERA_LABELS: Record<CameraId, string> = {
  cam1: 'Camera 1',
  cam2: 'Camera 2',
  cam3: 'Camera 3',
  monitor: 'Monitor',
};

export interface MultiCameraPanelHandle {
  /** The primary (focused) video element for time sync */
  getPrimaryVideo: () => HTMLVideoElement | null;
  /** Seek all cameras to a given time */
  seekAll: (time: number) => void;
}

interface Props {
  overlayData?: VideoOverlayData;
  onTimeUpdate?: (time: number) => void;
}

export const MultiCameraPanel = forwardRef<MultiCameraPanelHandle, Props>(
  function MultiCameraPanel({ overlayData, onTimeUpdate }, ref) {
    const { sessionId } = useSessionStore();
    const videoRefs = useRef<Record<CameraId, HTMLVideoElement | null>>({
      cam1: null, cam2: null, cam3: null, monitor: null,
    });
    const [focusedCamera, setFocusedCamera] = useState<CameraId | null>(null);
    const [isGridMode, setIsGridMode] = useState(true);
    const [focusContainerSize, setFocusContainerSize] = useState({ width: 0, height: 0 });
    const focusContainerRef = useRef<HTMLDivElement>(null);
    const syncingRef = useRef(false);

    const primaryCamera: CameraId = focusedCamera ?? 'cam1';

    useImperativeHandle(ref, () => ({
      getPrimaryVideo: () => videoRefs.current[primaryCamera],
      seekAll: (time: number) => {
        CAMERAS.forEach(cam => {
          const v = videoRefs.current[cam];
          if (v) v.currentTime = time;
        });
      },
    }));

    // Sync all cameras to the primary camera's time
    const syncCameras = useCallback(() => {
      if (syncingRef.current) return;
      const primary = videoRefs.current[primaryCamera];
      if (!primary) return;
      syncingRef.current = true;
      CAMERAS.forEach(cam => {
        if (cam === primaryCamera) return;
        const v = videoRefs.current[cam];
        if (v && Math.abs(v.currentTime - primary.currentTime) > 0.3) {
          v.currentTime = primary.currentTime;
        }
      });
      syncingRef.current = false;
    }, [primaryCamera]);

    // Play/pause all when primary plays/pauses
    useEffect(() => {
      const primary = videoRefs.current[primaryCamera];
      if (!primary) return;

      const onPlay = () => {
        syncCameras();
        CAMERAS.forEach(cam => {
          if (cam !== primaryCamera) videoRefs.current[cam]?.play();
        });
      };
      const onPause = () => {
        CAMERAS.forEach(cam => {
          if (cam !== primaryCamera) videoRefs.current[cam]?.pause();
        });
      };
      const onSeeked = () => syncCameras();
      const onTimeUpdate = () => {
        if (!syncingRef.current) {
          // Periodic drift correction
          syncCameras();
        }
      };

      primary.addEventListener('play', onPlay);
      primary.addEventListener('pause', onPause);
      primary.addEventListener('seeked', onSeeked);
      primary.addEventListener('timeupdate', onTimeUpdate);
      return () => {
        primary.removeEventListener('play', onPlay);
        primary.removeEventListener('pause', onPause);
        primary.removeEventListener('seeked', onSeeked);
        primary.removeEventListener('timeupdate', onTimeUpdate);
      };
    }, [primaryCamera, syncCameras]);

    // Forward time updates from primary video
    useEffect(() => {
      const primary = videoRefs.current[primaryCamera];
      if (!primary || !onTimeUpdate) return;
      const handler = () => onTimeUpdate(primary.currentTime);
      primary.addEventListener('timeupdate', handler);
      return () => primary.removeEventListener('timeupdate', handler);
    }, [primaryCamera, onTimeUpdate]);

    // Track focus container size for overlay
    useEffect(() => {
      const container = focusContainerRef.current;
      if (!container) return;
      const observer = new ResizeObserver(entries => {
        const entry = entries[0];
        if (entry) {
          setFocusContainerSize({
            width: entry.contentRect.width,
            height: entry.contentRect.height,
          });
        }
      });
      observer.observe(container);
      return () => observer.disconnect();
    }, [focusedCamera, isGridMode]);

    const handleCameraClick = useCallback((cam: CameraId) => {
      if (isGridMode) {
        // Switch to focus mode on this camera
        setIsGridMode(false);
        setFocusedCamera(cam);
      } else if (focusedCamera === cam) {
        // Clicking focused camera goes back to grid
        setIsGridMode(true);
        setFocusedCamera(null);
      } else {
        // Switch focus to different camera
        setFocusedCamera(cam);
      }
    }, [isGridMode, focusedCamera]);

    const toggleMode = useCallback(() => {
      if (isGridMode) {
        setIsGridMode(false);
        setFocusedCamera('cam1');
      } else {
        setIsGridMode(true);
        setFocusedCamera(null);
      }
    }, [isGridMode]);

    const setVideoRef = useCallback((cam: CameraId) => (el: HTMLVideoElement | null) => {
      videoRefs.current[cam] = el;
    }, []);

    // ── Grid Mode ──
    if (isGridMode) {
      return (
        <div className="bg-black flex-shrink-0 relative">
          {/* Mode toggle */}
          <div className="absolute top-2 right-2 z-20 flex gap-1">
            <button
              onClick={toggleMode}
              className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-black/60 text-gray-200 hover:bg-black/80 transition-colors"
              title="Switch to focus mode"
            >
              <Maximize2 size={10} />
              Focus
            </button>
          </div>

          <div className="grid grid-cols-2 gap-0.5 bg-gray-800 max-h-[320px]">
            {CAMERAS.map(cam => (
              <div
                key={cam}
                className="relative cursor-pointer group"
                onClick={() => handleCameraClick(cam)}
              >
                <video
                  ref={setVideoRef(cam)}
                  src={api.getVideoUrl(cam, sessionId)}
                  className="w-full h-full object-contain bg-black"
                  controls={false}
                  muted={cam !== 'cam1'}
                  playsInline
                  preload="auto"
                />
                {/* Camera label */}
                <div className="absolute bottom-1 left-1 px-1.5 py-0.5 rounded text-[9px] font-medium bg-black/70 text-white flex items-center gap-1">
                  <Camera size={8} />
                  {CAMERA_LABELS[cam]}
                </div>
                {/* Hover highlight */}
                <div className="absolute inset-0 border-2 border-transparent group-hover:border-blue-400 transition-colors pointer-events-none" />
              </div>
            ))}
          </div>

          {/* Shared controls for primary camera */}
          <div className="absolute bottom-0 left-0 right-0 z-10">
            <video
              ref={el => {
                // Hidden controls-only video synced to cam1
                // Use the camera-one media ref for playback controls.
              }}
              style={{ display: 'none' }}
            />
          </div>
        </div>
      );
    }

    // ── Focus Mode ──
    const thumbnailCameras = CAMERAS.filter(c => c !== focusedCamera);

    return (
      <div className="bg-black flex-shrink-0 relative">
        {/* Mode toggle */}
        <div className="absolute top-2 right-2 z-20 flex gap-1">
          <button
            onClick={toggleMode}
            className="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-black/60 text-gray-200 hover:bg-black/80 transition-colors"
            title="Switch to grid mode"
          >
            <Grid3x3 size={10} />
            Grid
          </button>
        </div>

        {/* Focused camera */}
        <div ref={focusContainerRef} className="relative">
          <video
            ref={setVideoRef(focusedCamera!)}
            src={api.getVideoUrl(focusedCamera!, sessionId)}
            className="w-full max-h-[240px] object-contain"
            controls
            muted={focusedCamera !== 'cam1'}
            playsInline
            preload="auto"
          />
          {/* Overlay on focused camera (cam1/cam2/cam3 only, not monitor) */}
          {overlayData && focusedCamera !== 'monitor' && focusContainerSize.width > 0 && (
            <VideoOverlay
              videoRef={{ current: videoRefs.current[focusedCamera!] } as React.RefObject<HTMLVideoElement>}
              overlayData={overlayData}
              containerWidth={focusContainerSize.width}
              containerHeight={focusContainerSize.height}
            />
          )}
          {/* Focused camera label */}
          <div className="absolute top-2 left-2 px-2 py-1 rounded text-[10px] font-semibold bg-blue-600/90 text-white flex items-center gap-1">
            <Camera size={10} />
            {CAMERA_LABELS[focusedCamera!]}
          </div>
        </div>

        {/* Thumbnail strip */}
        <div className="flex gap-0.5 bg-gray-800 h-[70px]">
          {thumbnailCameras.map(cam => (
            <div
              key={cam}
              className="relative flex-1 cursor-pointer group"
              onClick={() => handleCameraClick(cam)}
            >
              <video
                ref={setVideoRef(cam)}
                src={api.getVideoUrl(cam, sessionId)}
                className="w-full h-full object-contain bg-black"
                controls={false}
                muted
                playsInline
                preload="auto"
              />
              <div className="absolute bottom-0.5 left-0.5 px-1 py-0.5 rounded text-[8px] font-medium bg-black/70 text-white">
                {CAMERA_LABELS[cam]}
              </div>
              <div className="absolute inset-0 border border-transparent group-hover:border-blue-400 transition-colors pointer-events-none" />
            </div>
          ))}
        </div>
      </div>
    );
  }
);
