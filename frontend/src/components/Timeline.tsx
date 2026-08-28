import React from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { CriticalMoment } from '@/types';
import { api } from '@/services/api';
import { Play, Pause } from 'lucide-react';

export const Timeline = () => {
  const { sessionId, moments, currentTime, jumpToTime, isPlaying, setIsPlaying } = useSessionStore();

  const totalDuration = Math.max(1, ...moments.map((moment) => moment.end_time));
  const getPosition = (time: number) => (time / totalDuration) * 100;

  const handleMarkerClick = (moment: CriticalMoment) => {
    jumpToTime(moment.start_time);
    api.logInteraction({
      session_id: sessionId,
      moment_id: moment.id,
      interaction_type: 'highlight_click',
      data: {
        from_timestamp: currentTime,
        to_timestamp: moment.start_time,
      },
    });
  };

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const percentage = clickX / rect.width;
    const newTime = percentage * totalDuration;

    jumpToTime(Math.max(0, Math.min(newTime, totalDuration)));
  };

  return (
    <div className="space-y-3">
      {/* Timeline */}
      <div className="space-y-2">
        {/* Current time display */}
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span className="font-medium">{formatTime(currentTime)}</span>
          <span className="text-gray-400">{moments.length} critical moments</span>
          <span className="font-medium">{formatTime(totalDuration)}</span>
        </div>

        {/* Timeline bar - bigger and clickable */}
        <div
          className="relative w-full h-8 bg-gray-200 rounded-lg overflow-hidden cursor-pointer"
          onClick={handleTimelineClick}
        >
          {/* Highlight markers */}
          {moments.map((moment) => (
            <div
              key={moment.id}
              className="absolute top-0 bottom-0 group cursor-pointer"
              style={{
                left: `${getPosition(moment.start_time)}%`,
                width: `${Math.max(getPosition(moment.end_time - moment.start_time), 0.5)}%`,
              }}
              onClick={() => handleMarkerClick(moment)}
            >
              <div
                className={`h-full ${
                  moment.severity === 'critical'
                    ? 'bg-red-500 hover:bg-red-600'
                    : 'bg-amber-400 hover:bg-amber-500'
                } transition-colors`}
              />

              {/* Tooltip on hover */}
              <div className="absolute bottom-full mb-2 left-1/2 -translate-x-1/2 hidden group-hover:block z-20 pointer-events-none">
                <div className="bg-gray-900 text-white text-xs p-3 rounded-lg shadow-xl max-w-xs whitespace-normal">
                  <div className="font-semibold mb-1">{moment.start_time_formatted}</div>
                  <div className={`text-xs mb-1 ${
                    moment.severity === 'critical' ? 'text-red-300' : 'text-amber-300'
                  }`}>
                    {moment.severity.toUpperCase()} · {moment.num_sources} source{moment.num_sources !== 1 ? 's' : ''}
                  </div>
                  <div className="text-gray-300 text-xs leading-relaxed">
                    {moment.summary.length > 100 ? moment.summary.slice(0, 100) + '...' : moment.summary}
                  </div>
                </div>
              </div>
            </div>
          ))}

          {/* Current position indicator */}
          <div
            className="absolute top-0 bottom-0 w-1 bg-blue-600 z-10 pointer-events-none"
            style={{ left: `${getPosition(currentTime)}%` }}
          >
            <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 bg-blue-600 rounded-full shadow-md" />
          </div>
        </div>
      </div>
    </div>
  );
};

// Export separate PlayButton component
export const PlayButton = () => {
  const { isPlaying, setIsPlaying } = useSessionStore();

  return (
    <button
      onClick={() => setIsPlaying(!isPlaying)}
      className="p-4 bg-blue-600 hover:bg-blue-700 text-white rounded-full shadow-lg transition-colors"
    >
      {isPlaying ? <Pause size={24} /> : <Play size={24} />}
    </button>
  );
};
