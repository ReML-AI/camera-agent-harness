import { useRef, useEffect, useState } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { api } from '@/services/api';
import { Play, Pause, ArrowLeft, ArrowRight, Maximize2, Volume2, VolumeX } from 'lucide-react';

const cameras = ['cam1', 'cam2', 'cam3', 'monitor'];
const cameraLabels: Record<string, string> = {
  cam1: 'Camera 1',
  cam2: 'Camera 2',
  cam3: 'Camera 3',
  monitor: 'Monitor',
};

export const VideoPlayer = () => {
  const { sessionId, currentTime, isPlaying, setCurrentTime, setIsPlaying } = useSessionStore();
  const [focusedCamera, setFocusedCamera] = useState<string | null>(null);
  const [isBuffering, setIsBuffering] = useState(false);
  const [isMuted, setIsMuted] = useState(false);

  const videoRefs = useRef<{ [key: string]: HTMLVideoElement | null }>({});
  const lastSyncTime = useRef<number>(0);
  const seekDebounceTimeout = useRef<ReturnType<typeof setTimeout>>();

  const primaryCamera = focusedCamera || 'cam1';

  // Sync primary camera time → store via native timeupdate event (fires ~4x/sec)
  useEffect(() => {
    const primary = videoRefs.current[primaryCamera];
    if (!primary) return;

    const onTimeUpdate = () => {
      const t = primary.currentTime;
      setCurrentTime(t);
      lastSyncTime.current = t;

      // Sync other videos
      cameras.forEach((cam) => {
        const video = videoRefs.current[cam];
        if (video && cam !== primaryCamera) {
          const diff = Math.abs(video.currentTime - t);
          if (diff > 1.0) {
            video.currentTime = t;
          }
        }
      });
    };

    primary.addEventListener('timeupdate', onTimeUpdate);
    return () => primary.removeEventListener('timeupdate', onTimeUpdate);
  }, [primaryCamera, setCurrentTime]);

  // Handle play/pause
  useEffect(() => {
    if (focusedCamera) {
      // In single mode, only control focused camera
      const video = videoRefs.current[focusedCamera];
      if (video) {
        if (isPlaying) {
          video.play().catch(console.error);
        } else {
          video.pause();
        }
      }
    } else {
      // In grid mode, control all cameras
      cameras.forEach((cam) => {
        const video = videoRefs.current[cam];
        if (video) {
          if (isPlaying) {
            video.play().catch(console.error);
          } else {
            video.pause();
          }
        }
      });
    }
  }, [isPlaying, focusedCamera]);

  // OPTIMIZED: Debounced seeking to reduce HTTP requests
  const debouncedSeek = (time: number) => {
    if (seekDebounceTimeout.current) {
      clearTimeout(seekDebounceTimeout.current);
    }

    seekDebounceTimeout.current = setTimeout(() => {
      if (focusedCamera) {
        // In single mode, only seek focused camera
        const video = videoRefs.current[focusedCamera];
        if (video && Math.abs(video.currentTime - time) > 2) {
          video.currentTime = time;
        }
      } else {
        // In grid mode, seek all cameras
        cameras.forEach((cam) => {
          const video = videoRefs.current[cam];
          if (video && Math.abs(video.currentTime - time) > 2) {
            video.currentTime = time;
          }
        });
      }
    }, 100); // Wait 100ms after last seek request
  };

  // Handle seeking with debouncing
  useEffect(() => {
    debouncedSeek(currentTime);
  }, [currentTime, focusedCamera]);

  // OPTIMIZED: Smart preload strategy based on mode
  useEffect(() => {
    cameras.forEach((cam) => {
      const video = videoRefs.current[cam];
      if (video) {
        if (focusedCamera) {
          // Single mode: only preload focused camera
          if (cam === focusedCamera) {
            video.preload = 'auto';
            if (video.networkState === video.NETWORK_IDLE) {
              video.load();
            }
          } else {
            video.preload = 'none';
          }
        } else {
          // Grid mode: preload primary (cam1), metadata for others
          if (cam === 'cam1') {
            video.preload = 'auto';
          } else {
            video.preload = 'metadata';
          }
        }
      }
    });
  }, [focusedCamera]);

  // OPTIMIZED: Update mute state without recreating elements
  useEffect(() => {
    cameras.forEach((cam) => {
      const video = videoRefs.current[cam];
      if (video) {
        if (isMuted) {
          // User manually muted: mute all
          video.muted = true;
        } else if (focusedCamera) {
          // Single mode: only focused camera has audio
          video.muted = cam !== focusedCamera;
        } else {
          // Grid mode: only cam1 has audio
          video.muted = cam !== 'cam1';
        }
      }
    });
  }, [focusedCamera, isMuted]);

  const togglePlay = () => {
    setIsPlaying(!isPlaying);
  };

  const navigateFocus = (direction: 'prev' | 'next') => {
    const currentIndex = cameras.indexOf(focusedCamera || 'cam1');
    const nextIndex = direction === 'next'
      ? (currentIndex + 1) % cameras.length
      : (currentIndex - 1 + cameras.length) % cameras.length;

    setFocusedCamera(cameras[nextIndex]);
  };

  // Render each video once, then reposition the focused view.
  // This prevents unmounting/remounting and preserves buffered data
  return (
    <div className="relative w-full h-full bg-black overflow-hidden">
      {/* Buffering Indicator */}
      {focusedCamera && isBuffering && (
        <div className="absolute inset-0 flex items-center justify-center z-30 bg-black/50 pointer-events-none">
          <div className="text-white text-sm">Loading...</div>
        </div>
      )}

      {/* Grid Mode Mute Button */}
      {!focusedCamera && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            setIsMuted(!isMuted);
          }}
          className="absolute bottom-4 right-4 z-30 p-3 bg-white/90 text-gray-900 rounded-lg hover:bg-white shadow-lg"
          title={isMuted ? "Unmute" : "Mute"}
        >
          {isMuted ? <VolumeX size={20} /> : <Volume2 size={20} />}
        </button>
      )}

      {/* Single Mode Controls */}
      {focusedCamera && (
        <>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setFocusedCamera(null);
            }}
            className="absolute top-4 left-4 z-30 px-4 py-2 bg-white/90 text-gray-900 rounded-lg hover:bg-white text-sm font-medium shadow-lg"
          >
            ← Back to Grid
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsMuted(!isMuted);
            }}
            className="absolute top-4 right-4 z-30 p-3 bg-white/90 text-gray-900 rounded-lg hover:bg-white shadow-lg"
            title={isMuted ? "Unmute" : "Mute"}
          >
            {isMuted ? <VolumeX size={20} /> : <Volume2 size={20} />}
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              navigateFocus('prev');
            }}
            className="absolute left-4 top-1/2 -translate-y-1/2 z-30 p-3 bg-white/90 text-gray-900 rounded-full hover:bg-white shadow-lg"
          >
            <ArrowLeft size={20} />
          </button>

          <button
            onClick={(e) => {
              e.stopPropagation();
              navigateFocus('next');
            }}
            className="absolute right-4 top-1/2 -translate-y-1/2 z-30 p-3 bg-white/90 text-gray-900 rounded-full hover:bg-white shadow-lg"
          >
            <ArrowRight size={20} />
          </button>
        </>
      )}

      {/* Grid Layout - Always rendered, contains all video elements */}
      <div className="grid grid-cols-2 gap-1 w-full h-full p-1">
        {cameras.map((camera) => {
          const isFocused = camera === focusedCamera;

          return (
            <div
              key={camera}
              className="relative group cursor-pointer bg-black overflow-hidden transition-all"
              onClick={() => !focusedCamera && setFocusedCamera(camera)}
              style={{
                // When focused, span all grid cells
                ...(isFocused && {
                  gridColumn: '1 / -1',
                  gridRow: '1 / -1',
                  zIndex: 20,
                  cursor: 'default',
                }),
                // Hide other videos when one is focused
                ...(focusedCamera && !isFocused && {
                  display: 'none',
                }),
              }}
            >
              {/* Camera Label - hide in single mode */}
              {!focusedCamera && (
                <div className="absolute top-2 left-2 z-10 px-2.5 py-1 bg-black/70 text-white text-xs rounded backdrop-blur">
                  {cameraLabels[camera]}
                </div>
              )}

              {/* Maximize Icon - only show in grid mode */}
              {!focusedCamera && (
                <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity z-10 bg-black/30">
                  <Maximize2 size={32} className="text-white" />
                </div>
              )}

              {/* Video Element - always mounted, never unmounted */}
              <video
                ref={(el) => (videoRefs.current[camera] = el)}
                src={api.getVideoUrl(camera, sessionId)}
                className="w-full h-full"
                style={{
                  objectFit: isFocused ? 'contain' : 'cover',
                }}
                muted={camera !== 'cam1'} // Initial mute state, updated by effect
                playsInline
                preload={camera === 'cam1' ? 'auto' : 'metadata'}
                onWaiting={() => {
                  if (camera === primaryCamera) setIsBuffering(true);
                }}
                onCanPlay={() => {
                  if (camera === primaryCamera) setIsBuffering(false);
                }}
                onLoadedData={() => {
                  if (camera === primaryCamera) setIsBuffering(false);
                }}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
};
