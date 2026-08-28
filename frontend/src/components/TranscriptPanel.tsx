import { useEffect, useState } from 'react';
import { useSessionStore } from '@/stores/sessionStore';
import { TranscriptSegment } from '@/types';

export const TranscriptPanel = () => {
  const { transcript, currentTime } = useSessionStore();
  const [currentSegment, setCurrentSegment] = useState<TranscriptSegment | null>(null);

  useEffect(() => {
    // Find current segment based on time
    const segment = transcript.find(
      (seg) => currentTime >= seg.start && currentTime <= seg.end
    );
    setCurrentSegment(segment || null);
  }, [currentTime, transcript]);

  return (
    <div className="p-4">
      {currentSegment ? (
        <div className="space-y-1">
          {currentSegment.speaker && (
            <div className="text-xs font-medium text-gray-500">{currentSegment.speaker}</div>
          )}
          <div className="text-sm text-gray-900 leading-relaxed">{currentSegment.text}</div>
        </div>
      ) : (
        <div className="text-sm text-gray-400 italic">No transcript at current time</div>
      )}
    </div>
  );
};
