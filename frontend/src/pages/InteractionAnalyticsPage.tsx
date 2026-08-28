import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useSessionStore } from '@/stores/sessionStore';
import { SpeakerTimeline } from '@/components/interaction/SpeakerTimeline';
import { TalkTimeChart } from '@/components/interaction/TalkTimeChart';
import { TurnTakingFlow } from '@/components/interaction/TurnTakingFlow';
import { AttentionChart } from '@/components/interaction/AttentionChart';
import { GazeDistribution } from '@/components/interaction/GazeDistribution';
import { SpeakerTranscript } from '@/components/interaction/SpeakerTranscript';
import { InsightCards } from '@/components/interaction/InsightCards';
import { MomentList } from '@/components/interaction/MomentList';
import { MomentContextPanel } from '@/components/interaction/MomentContextPanel';
import { MomentContext } from '@/types';
import { Loader2, X, AlertCircle as AlertIcon } from 'lucide-react';

interface Props {
  sessionId: string;
}

export function InteractionAnalyticsPage({ sessionId }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const { currentTime, setCurrentTime, jumpToTime } = useSessionStore();
  const [localTime, setLocalTime] = useState(0);
  const [selectedMoment, setSelectedMoment] = useState<MomentContext | null>(null);

  const { data: analytics, isLoading, error } = useQuery({
    queryKey: ['interaction-analytics', sessionId],
    queryFn: () => api.getInteractionAnalytics(sessionId),
  });

  const { data: momentContexts, isLoading: momentsLoading, error: momentsError, refetch: refetchMoments } = useQuery({
    queryKey: ['moment-contexts', sessionId],
    queryFn: () => api.getMomentContexts(sessionId),
  });

  // Sync video with store time
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTimeUpdate = () => {
      setLocalTime(video.currentTime);
      setCurrentTime(video.currentTime);
    };
    video.addEventListener('timeupdate', onTimeUpdate);
    return () => video.removeEventListener('timeupdate', onTimeUpdate);
  }, [setCurrentTime]);

  // When jumpToTime is called, seek the video
  useEffect(() => {
    const video = videoRef.current;
    if (video && Math.abs(video.currentTime - currentTime) > 1) {
      video.currentTime = currentTime;
    }
  }, [currentTime]);

  const handleSeek = (time: number) => {
    const video = videoRef.current;
    if (video) {
      video.currentTime = time;
      video.play();
    }
    jumpToTime(time);
  };

  const handleMomentSelect = (moment: MomentContext) => {
    setSelectedMoment(moment);
    handleSeek(moment.timestamp);
  };

  const handleNarrativeUpdated = (momentId: number, narrative: string, tags: string[], prompt: string) => {
    if (selectedMoment && selectedMoment.moment_id === momentId) {
      setSelectedMoment({ ...selectedMoment, narrative, tags, discussion_prompt: prompt });
    }
  };

  const handleNavigate = (direction: 'prev' | 'next') => {
    if (!momentContexts || !selectedMoment) return;
    const moments = momentContexts.moments;
    const idx = moments.findIndex(m => m.moment_id === selectedMoment.moment_id);
    const nextIdx = direction === 'prev' ? idx - 1 : idx + 1;
    if (nextIdx >= 0 && nextIdx < moments.length) {
      handleMomentSelect(moments[nextIdx]);
    }
  };

  const selectedIndex = momentContexts?.moments.findIndex(m => m.moment_id === selectedMoment?.moment_id) ?? -1;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-blue-500" size={32} />
        <span className="ml-3 text-gray-500">Loading interaction analytics...</span>
      </div>
    );
  }

  if (error || !analytics) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-red-500 font-medium">Failed to load analytics</p>
          <p className="text-sm text-gray-400 mt-1">
            Make sure compute_interaction_analytics.py has been run.
          </p>
        </div>
      </div>
    );
  }

  const totalDuration = analytics.timeline_segments.length > 0
    ? Math.max(...analytics.timeline_segments.map((s) => s.end))
    : 1000;

  return (
    <div className="flex h-full">
      {/* Left sidebar: Moment List */}
      <div className="w-72 flex-shrink-0 border-r border-gray-200 bg-white overflow-hidden">
        {momentsLoading ? (
          <div className="flex flex-col items-center justify-center h-full">
            <Loader2 className="animate-spin text-blue-400" size={24} />
            <p className="text-xs text-gray-400 mt-2">Loading moments...</p>
          </div>
        ) : momentsError ? (
          <div className="flex flex-col items-center justify-center h-full px-4 text-center">
            <AlertIcon size={24} className="text-red-400 mb-2" />
            <p className="text-sm text-red-500 mb-2">Failed to load moments</p>
            <button
              className="text-xs px-3 py-1 rounded bg-gray-100 hover:bg-gray-200 text-gray-600"
              onClick={() => refetchMoments()}
            >
              Retry
            </button>
          </div>
        ) : momentContexts ? (
          <MomentList
            moments={momentContexts.moments}
            selectedId={selectedMoment?.moment_id ?? null}
            onSelect={handleMomentSelect}
            onNavigate={handleNavigate}
          />
        ) : null}
      </div>

      {/* Center: main analytics content */}
      <div className="flex-1 overflow-y-auto">
        <div className="p-6 space-y-6 max-w-[1600px] mx-auto">
          {/* Header */}
          <div>
            <h2 className="text-xl font-bold text-gray-900">Interaction Analytics</h2>
            <p className="text-sm text-gray-500">
              Session {sessionId} &mdash; {Object.keys(analytics.speakers).length} speakers,{' '}
              {analytics.timeline_segments.length} segments, {analytics.insights.length} insights
              {momentContexts && `, ${momentContexts.metadata.total_moments} moments analyzed`}
            </p>
          </div>

          {/* Video + Transcript row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Video Player */}
            <div className="bg-black rounded-lg overflow-hidden">
              <video
                ref={videoRef}
                src={api.getVideoUrl('cam1', sessionId)}
                className="w-full aspect-video"
                controls
              />
            </div>

            {/* Speaker Transcript */}
            <div className="bg-white rounded-lg border border-gray-200 p-4 flex flex-col" style={{ maxHeight: 400 }}>
              <h3 className="text-sm font-semibold text-gray-700 mb-2 flex-shrink-0">
                Speaker Transcript
              </h3>
              <div className="flex-1 overflow-hidden">
                <SpeakerTranscript
                  segments={analytics.timeline_segments}
                  speakers={analytics.speakers}
                  currentTime={localTime}
                  onSeek={handleSeek}
                />
              </div>
            </div>
          </div>

          {/* Speaker Timeline */}
          <SpeakerTimeline
            segments={analytics.timeline_segments}
            speakers={analytics.speakers}
            insights={analytics.insights}
            currentTime={localTime}
            totalDuration={totalDuration}
            onSeek={handleSeek}
          />

          {/* Charts row */}
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <TalkTimeChart speakers={analytics.speakers} />
            <TurnTakingFlow
              speakers={analytics.speakers}
              transitions={analytics.turn_taking.transitions}
              avgGap={analytics.turn_taking.avg_gap_seconds}
              avgOverlap={analytics.turn_taking.avg_overlap_seconds}
            />
            <AttentionChart
              speakers={analytics.speakers}
              attentionReceived={analytics.attention.speaker_attention_received}
            />
            <GazeDistribution
              speakers={analytics.speakers}
              gazeAttention={analytics.gaze_attention ?? {}}
            />
          </div>

          {/* Insights */}
          <InsightCards insights={analytics.insights} onSeek={handleSeek} />
        </div>
      </div>

      {/* Right panel: Moment Context Detail */}
      {selectedMoment && momentContexts && (
        <div className="w-96 flex-shrink-0 border-l border-gray-200 bg-white overflow-y-auto p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-700">Moment Detail</h3>
            <button
              className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
              onClick={() => setSelectedMoment(null)}
              title="Close panel"
            >
              <X size={16} />
            </button>
          </div>
          <MomentContextPanel
            moment={selectedMoment}
            speakerRoles={momentContexts.speaker_roles}
            sessionId={sessionId}
            onNarrativeUpdated={handleNarrativeUpdated}
            onNavigate={handleNavigate}
            hasPrev={selectedIndex > 0}
            hasNext={selectedIndex < momentContexts.moments.length - 1}
          />
        </div>
      )}
    </div>
  );
}
