import { useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useSessionStore } from '@/stores/sessionStore';
import { MomentContext, MomentContextsResponse, DebriefPlan } from '@/types';
import { SessionHeader } from '@/components/debrief/SessionHeader';
import { MomentTimeline } from '@/components/debrief/MomentTimeline';
import { MomentDetailPanel } from '@/components/debrief/MomentDetailPanel';
import { AIObservationPanel } from '@/components/debrief/AIObservationPanel';
import { VideoOverlay } from '@/components/debrief/VideoOverlay';
import { WorkflowDrawer } from '@/components/debrief/WorkflowDrawer';
import { FeedbackDrawerContent } from '@/components/debrief/FeedbackDrawerContent';
import { SpeakerTranscript } from '@/components/interaction/SpeakerTranscript';
import { MomentListPanel } from '@/components/debrief/MomentListPanel';
import ReviewPlayer from '@/components/ReviewPlayer';
import { Loader2, ChevronUp, ChevronDown, Star, UserCheck, Camera } from 'lucide-react';

type ToolView = 'debrief_report';

interface Props {
  sessionId: string;
  onSwitchView: (view: ToolView) => void;
}

const CAMERAS = [
  { id: 'cam1', label: 'Camera 1' },
  { id: 'cam2', label: 'Camera 2' },
  { id: 'cam3', label: 'Camera 3' },
  { id: 'monitor', label: 'Monitor' },
] as const;

export function DebriefView({ sessionId, onSwitchView }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoContainerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  const { currentTime, setCurrentTime, jumpToTime, starredMomentIds, setStarredMomentIds } = useSessionStore();
  const [localTime, setLocalTime] = useState(0);
  const [selectedMoment, setSelectedMoment] = useState<MomentContext | null>(null);
  const [selectedCamera, setSelectedCamera] = useState('cam1');
  const [videoDimensions, setVideoDimensions] = useState({ width: 0, height: 0 });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [centerView, setCenterView] = useState<'video' | 'review_clips'>('video');
  const starredSet = useMemo(() => new Set(starredMomentIds), [starredMomentIds]);

  const { data: analytics, isLoading: analyticsLoading } = useQuery({
    queryKey: ['interaction-analytics', sessionId],
    queryFn: () => api.getInteractionAnalytics(sessionId),
  });

  const { data: momentContexts, isLoading: momentsLoading } = useQuery({
    queryKey: ['moment-contexts', sessionId],
    queryFn: () => api.getMomentContexts(sessionId),
  });

  const { data: overlayData } = useQuery({
    queryKey: ['video-overlay', sessionId],
    queryFn: () => api.getVideoOverlay(sessionId),
    staleTime: Infinity,
  });

  const isLoading = analyticsLoading || momentsLoading;

  const { data: debriefPlan } = useQuery({
    queryKey: ['debrief-plan', sessionId],
    queryFn: () => api.getDebriefPlan(sessionId),
  });

  const savePlanMutation = useMutation({
    mutationFn: (plan: DebriefPlan) => api.saveDebriefPlan(sessionId, plan),
  });

  // Initialize starred moments from loaded plan
  useEffect(() => {
    if (debriefPlan?.starred_moment_ids) {
      setStarredMomentIds(debriefPlan.starred_moment_ids);
    }
  }, [debriefPlan, setStarredMomentIds]);

  // Track video container dimensions for overlay sizing
  useEffect(() => {
    const container = videoContainerRef.current;
    if (!container) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setVideoDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [isLoading]);

  // Sync video → store
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const onTimeUpdate = () => {
      setLocalTime(video.currentTime);
      setCurrentTime(video.currentTime);
    };
    video.addEventListener('timeupdate', onTimeUpdate);
    return () => video.removeEventListener('timeupdate', onTimeUpdate);
  }, [setCurrentTime, isLoading]);

  // Store → video seek
  useEffect(() => {
    const video = videoRef.current;
    if (video && Math.abs(video.currentTime - currentTime) > 1) {
      video.currentTime = currentTime;
    }
  }, [currentTime]);

  // Preserve playback position when switching cameras
  const handleCameraChange = useCallback((camId: string) => {
    const video = videoRef.current;
    const wasPlaying = video && !video.paused;
    const time = video?.currentTime ?? 0;
    setSelectedCamera(camId);
    // After React re-renders with new src, restore time
    requestAnimationFrame(() => {
      const v = videoRef.current;
      if (v) {
        v.currentTime = time;
        if (wasPlaying) v.play();
      }
    });
  }, []);

  const handleSeek = useCallback((time: number) => {
    const video = videoRef.current;
    if (video) {
      video.currentTime = time;
      video.play();
    }
    jumpToTime(time);
  }, [jumpToTime]);

  const handleMomentSelect = useCallback((moment: MomentContext) => {
    setSelectedMoment(moment);
    handleSeek(moment.timestamp);
  }, [handleSeek]);

  const moments = useMemo(() => momentContexts?.moments ?? [], [momentContexts]);
  const selectedIndex = selectedMoment
    ? moments.findIndex(m => m.moment_id === selectedMoment.moment_id)
    : -1;

  const handleNavigate = useCallback((direction: 'prev' | 'next') => {
    if (!selectedMoment) return;
    const nextIdx = direction === 'prev' ? selectedIndex - 1 : selectedIndex + 1;
    if (nextIdx >= 0 && nextIdx < moments.length) {
      handleMomentSelect(moments[nextIdx]);
    }
  }, [selectedMoment, selectedIndex, moments, handleMomentSelect]);

  const handleNarrativeUpdated = useCallback((momentId: number, narrative: string, tags: string[], prompt: string) => {
    if (selectedMoment && selectedMoment.moment_id === momentId) {
      setSelectedMoment({ ...selectedMoment, narrative, tags, discussion_prompt: prompt });
    }
    // Update TanStack Query cache so navigating away and back preserves the new narrative
    queryClient.setQueryData<MomentContextsResponse>(['moment-contexts', sessionId], (old) => {
      if (!old) return old;
      return {
        ...old,
        moments: old.moments.map(m =>
          m.moment_id === momentId ? { ...m, narrative, tags, discussion_prompt: prompt } : m
        ),
      };
    });
  }, [selectedMoment, queryClient, sessionId]);

  const toggleStar = useCallback((momentId: number) => {
    const next = new Set(starredSet);
    if (next.has(momentId)) next.delete(momentId);
    else next.add(momentId);
    const nextIds = Array.from(next);
    setStarredMomentIds(nextIds);
    savePlanMutation.mutate({
      session_id: sessionId,
      starred_moment_ids: nextIds,
      moment_order: nextIds,
      notes: debriefPlan?.notes ?? {},
      updated_at: new Date().toISOString(),
    });
  }, [starredSet, setStarredMomentIds, sessionId, debriefPlan, savePlanMutation]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      // Don't capture when typing in inputs, textareas, or contenteditable
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target.isContentEditable
      ) return;

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          handleNavigate('prev');
          break;
        case 'ArrowRight':
          e.preventDefault();
          handleNavigate('next');
          break;
        case ' ':
          // Only intercept Space when no interactive element is focused (preserve button a11y)
          if (target === document.body || target.closest('[data-debrief-root]')) {
            e.preventDefault();
            if (videoRef.current) {
              if (videoRef.current.paused) videoRef.current.play();
              else videoRef.current.pause();
            }
          }
          break;
        case 's':
        case 'S':
          // Don't fire star when a button/link is focused
          if (target instanceof HTMLButtonElement || target instanceof HTMLAnchorElement) break;
          if (selectedMoment) toggleStar(selectedMoment.moment_id);
          break;
        case 'Escape':
          if (drawerOpen) {
            setDrawerOpen(false);
          } else {
            setSelectedMoment(null);
          }
          break;
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handleNavigate, selectedMoment, toggleStar, drawerOpen]);

  const totalDuration = analytics?.timeline_segments.length
    ? analytics.timeline_segments.reduce((max, s) => (s.end > max ? s.end : max), 0)
    : 1000;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <Loader2 className="animate-spin text-blue-500" size={32} />
        <span className="ml-3 text-gray-500">Loading debrief data...</span>
      </div>
    );
  }

  if (!analytics) {
    return (
      <div className="flex items-center justify-center h-full bg-gray-50">
        <div className="text-center">
          <p className="text-red-500 font-medium">Failed to load analytics</p>
          <p className="text-sm text-gray-400 mt-1">Run compute_interaction_analytics.py first.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-gray-50 overflow-hidden" data-debrief-root>
      <SessionHeader
        sessionId={sessionId}
        analytics={analytics}
        momentContexts={momentContexts}
        starredCount={starredMomentIds.length}
        onSelectTool={onSwitchView}
      />

      {/* 3-panel workspace */}
      <div className="flex-1 flex overflow-hidden min-h-0">

        {/* LEFT: Moments list */}
        <div className="w-60 flex-shrink-0 overflow-hidden">
          <MomentListPanel
            moments={moments}
            selectedMomentId={selectedMoment?.moment_id ?? null}
            starredMomentIds={starredMomentIds}
            onSelect={handleMomentSelect}
            onToggleStar={toggleStar}
          />
        </div>

        {/* CENTER: Video + timeline + transcript / Review Clips */}
        <div className="flex-1 flex flex-col overflow-hidden border-x border-gray-200 min-w-0">
          {/* Toggle bar */}
          <div className="flex-shrink-0 flex gap-1 bg-gray-50 border-b border-gray-200 px-3 py-1.5">
            <button
              onClick={() => setCenterView('video')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                centerView === 'video'
                  ? 'bg-white text-gray-900 shadow-sm border border-gray-200'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Video
            </button>
            <button
              onClick={() => setCenterView('review_clips')}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                centerView === 'review_clips'
                  ? 'bg-white text-gray-900 shadow-sm border border-gray-200'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              Review Clips
            </button>
          </div>

          {centerView === 'review_clips' ? (
            <div className="flex-1 overflow-y-auto p-3">
              <ReviewPlayer sessionId={sessionId} />
            </div>
          ) : (
            <>
              {/* Video + overlay */}
              <div ref={videoContainerRef} className="bg-black flex-shrink-0 relative">
                <video
                  ref={videoRef}
                  src={api.getVideoUrl(selectedCamera, sessionId)}
                  className="w-full max-h-[280px] object-contain"
                  controls
                />
                {overlayData && selectedCamera !== 'monitor' && videoDimensions.width > 0 && (
                  <VideoOverlay
                    videoRef={videoRef}
                    overlayData={overlayData}
                    containerWidth={videoDimensions.width}
                    containerHeight={videoDimensions.height}
                  />
                )}
                {/* Camera selector */}
                <div className="absolute top-2 left-2 z-20">
                  <div className="flex items-center gap-1 bg-black/70 rounded px-2 py-1">
                    <Camera size={12} className="text-white" />
                    <select
                      value={selectedCamera}
                      onChange={(e) => handleCameraChange(e.target.value)}
                      className="bg-transparent text-white text-xs font-medium outline-none cursor-pointer appearance-none pr-4"
                      style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='white'/%3E%3C/svg%3E")`, backgroundRepeat: 'no-repeat', backgroundPosition: 'right center' }}
                    >
                      {CAMERAS.map(cam => (
                        <option key={cam.id} value={cam.id} className="bg-gray-800 text-white">
                          {cam.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              {/* Timeline */}
              <div className="flex-shrink-0 px-3 py-2 bg-white border-b border-gray-200">
                <MomentTimeline
                  segments={analytics.timeline_segments}
                  speakers={analytics.speakers}
                  moments={moments}
                  insights={analytics.insights}
                  currentTime={localTime}
                  totalDuration={totalDuration}
                  selectedMomentId={selectedMoment?.moment_id ?? null}
                  starredMomentIds={starredMomentIds}
                  onSeek={handleSeek}
                  onMomentSelect={handleMomentSelect}
                />
              </div>

              {/* Transcript */}
              <div className="flex-1 bg-white overflow-hidden flex flex-col min-h-0">
                <div className="px-3 py-1.5 border-b border-gray-100 flex-shrink-0">
                  <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Transcript</h3>
                </div>
                <div className="flex-1 overflow-hidden px-1">
                  <SpeakerTranscript
                    segments={analytics.timeline_segments}
                    speakers={analytics.speakers}
                    currentTime={localTime}
                    onSeek={handleSeek}
                  />
                </div>
              </div>
            </>
          )}
        </div>

        {/* RIGHT: Moment detail */}
        <div className="w-96 flex-shrink-0 flex flex-col overflow-hidden bg-white">
          {selectedMoment && momentContexts ? (
            <>
              {/* Moment header */}
              <div className="px-4 py-3 border-b border-gray-100 flex-shrink-0">
                <div className="flex items-center justify-between">
                  <div>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      selectedMoment.importance === 'critical'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-amber-100 text-amber-700'
                    }`}>
                      {selectedMoment.importance}
                    </span>
                    <h3 className="text-sm font-semibold text-gray-900 mt-1">
                      {selectedMoment.category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    </h3>
                  </div>
                  <div className="flex items-center gap-1 text-gray-400">
                    <button
                      onClick={() => handleNavigate('prev')}
                      disabled={selectedIndex <= 0}
                      className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
                    >
                      <ChevronUp size={14} />
                    </button>
                    <span className="text-xs">{selectedIndex + 1}/{moments.length}</span>
                    <button
                      onClick={() => handleNavigate('next')}
                      disabled={selectedIndex >= moments.length - 1}
                      className="p-1 rounded hover:bg-gray-100 disabled:opacity-30"
                    >
                      <ChevronDown size={14} />
                    </button>
                  </div>
                </div>
              </div>

              {/* Scrollable detail */}
              <div className="flex-1 overflow-y-auto">
                <div className="p-4 border-b border-gray-100">
                  <MomentDetailPanel
                    moment={selectedMoment}
                    speakerRoles={momentContexts.speaker_roles}
                  />
                </div>
                <div className="p-4">
                  <AIObservationPanel
                    moment={selectedMoment}
                    sessionId={sessionId}
                    momentIndex={selectedIndex}
                    totalMoments={moments.length}
                    isStarred={starredSet.has(selectedMoment.moment_id)}
                    onNavigate={handleNavigate}
                    hasPrev={selectedIndex > 0}
                    hasNext={selectedIndex < moments.length - 1}
                    onNarrativeUpdated={handleNarrativeUpdated}
                    onToggleStar={toggleStar}
                  />
                </div>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-sm text-gray-400 text-center px-4">
                Select a moment from the list to view details
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Workflow action bar */}
      {starredMomentIds.length > 0 && (
        <div className="flex-shrink-0 bg-blue-50 border-t border-blue-200 px-4 py-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-sm text-blue-800">
            <Star size={14} className="fill-blue-500 text-blue-500" />
            <span className="font-medium">{starredMomentIds.length} moment{starredMomentIds.length !== 1 ? 's' : ''} starred for debrief</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setDrawerOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium bg-blue-600 text-white hover:bg-blue-700 transition-colors"
            >
              <UserCheck size={14} />
              Generate Feedback
            </button>
          </div>
        </div>
      )}

      {/* Feedback drawer */}
      <WorkflowDrawer
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="Generate Student Feedback"
      >
        <FeedbackDrawerContent
          sessionId={sessionId}
          starredMomentIds={starredMomentIds}
          onNavigateToReview={() => {
            setDrawerOpen(false);
          }}
        />
      </WorkflowDrawer>
    </div>
  );
}
