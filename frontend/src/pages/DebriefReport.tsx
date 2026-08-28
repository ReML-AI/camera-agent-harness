// frontend/src/pages/DebriefReport.tsx
import { useState, useEffect, useCallback, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useSessionStore } from '@/stores/sessionStore';
import { MomentContextsResponse, InteractionAnalytics, VideoOverlayData, OverlayKeyframe, OverlayPersonMeta, ReportManifest } from '@/types';
import { ChevronLeft, ChevronRight, Maximize2, Minimize2, X, Loader2 } from 'lucide-react';

import { CoverSlide } from '@/components/report/CoverSlide';
import { SessionOverviewSlide } from '@/components/report/SessionOverviewSlide';
import { CriticalMomentsSlide } from '@/components/report/CriticalMomentsSlide';
import { MomentDeepDiveSlide } from '@/components/report/MomentDeepDiveSlide';
import { TeamDynamicsSlide } from '@/components/report/TeamDynamicsSlide';
import { LearningOutcomesSlide } from '@/components/report/LearningOutcomesSlide';
import { ActionPlanSlide } from '@/components/report/ActionPlanSlide';
import { SpeakerIntroSlide } from '@/components/report/SpeakerIntroSlide';

interface Props {
  sessionId: string;
  onClose: () => void;
}

interface Slide {
  id: string;
  label: string;
}

function buildSlides(
  analytics: InteractionAnalytics,
  momentContexts: MomentContextsResponse,
  starredMomentIds: number[]
): Slide[] {
  const starredMoments = momentContexts.moments.filter(m =>
    starredMomentIds.includes(m.moment_id)
  );

  const slides: Slide[] = [
    { id: 'cover', label: 'Cover' },
    { id: 'speakers', label: 'Participants' },
    { id: 'overview', label: 'Overview' },
    { id: 'critical', label: 'Critical Moments' },
    ...starredMoments.map((m, i) => ({
      id: `moment_${m.moment_id}`,
      label: `Moment ${i + 1}`,
    })),
    { id: 'dynamics', label: 'Team Dynamics' },
    { id: 'outcomes', label: 'Learning Outcomes' },
    { id: 'action', label: 'Discussion Guide' },
  ];

  return slides;
}

export function DebriefReport({ sessionId, onClose }: Props) {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const { starredMomentIds } = useSessionStore();

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
  });

  const { data: reportManifest } = useQuery({
    queryKey: ['report-manifest', sessionId],
    queryFn: () => api.getReportManifest(sessionId),
  });

  const slides = analytics && momentContexts
    ? buildSlides(analytics, momentContexts, starredMomentIds)
    : [];

  const goTo = useCallback((idx: number) => {
    setCurrentSlide(Math.max(0, Math.min(slides.length - 1, idx)));
  }, [slides.length]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') goTo(currentSlide + 1);
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') goTo(currentSlide - 1);
      if (e.key === 'Escape') {
        if (document.fullscreenElement) return;
        onClose();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [currentSlide, goTo, onClose]);

  useEffect(() => {
    if (slides.length > 0 && currentSlide >= slides.length) {
      setCurrentSlide(slides.length - 1);
    }
  }, [slides.length, currentSlide]);

  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', onFsChange);
    return () => document.removeEventListener('fullscreenchange', onFsChange);
  }, []);

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  const isLoading = analyticsLoading || momentsLoading;

  if (isLoading) {
    return (
      <div className="fixed inset-0 z-50 bg-gray-900 flex items-center justify-center">
        <Loader2 className="animate-spin text-white" size={32} />
      </div>
    );
  }

  if (!analytics || !momentContexts) return null;

  const analyticsData: InteractionAnalytics = analytics;
  const contextsData: MomentContextsResponse = momentContexts;

  const starredMoments = contextsData.moments.filter(m =>
    starredMomentIds.includes(m.moment_id)
  );

  // Build moment_id → best keyframe lookup from overlay data
  const momentKeyframes = useMemo(() => {
    const map = new Map<number, OverlayKeyframe>();
    if (!overlayData) return map;
    for (const omMeta of overlayData.moments) {
      const midFrame = Math.round((omMeta.start_frame + omMeta.end_frame) / 2);
      // Find closest keyframe with person data
      let best: OverlayKeyframe | null = null;
      let bestDist = Infinity;
      for (const kf of overlayData.keyframes) {
        const dist = Math.abs(kf.frame - midFrame);
        if (dist < bestDist && kf.persons.length > 0) {
          bestDist = dist;
          best = kf;
        }
        // Early exit: keyframes are sorted, stop once we pass the mid + some margin
        if (kf.frame > midFrame + 100 && best) break;
      }
      if (best) map.set(omMeta.moment_id, best);
    }
    return map;
  }, [overlayData]);

  const personMeta: Record<string, OverlayPersonMeta> = overlayData?.persons ?? {};
  const manifest: ReportManifest = reportManifest ?? { session_id: sessionId, speakers: {}, moments: {} };

  // Build moment_id → annotated frame URL map
  const momentFrameUrls = useMemo(() => {
    const map = new Map<number, string>();
    if (!reportManifest) return map;
    for (const [mid, asset] of Object.entries(reportManifest.moments)) {
      const filename = asset.file.split('/').pop();
      if (filename) {
        map.set(Number(mid), api.getReportAssetUrl(sessionId, 'moments', filename));
      }
    }
    return map;
  }, [reportManifest, sessionId]);

  function renderSlide(slide: Slide) {
    if (slide.id === 'cover') {
      return (
        <CoverSlide
          sessionId={sessionId}
          analytics={analyticsData}
          totalMoments={contextsData.metadata.total_moments}
        />
      );
    }
    if (slide.id === 'speakers') {
      return (
        <SpeakerIntroSlide
          sessionId={sessionId}
          analytics={analyticsData}
          manifest={manifest}
          speakerRoles={contextsData.speaker_roles}
        />
      );
    }
    if (slide.id === 'overview') {
      return (
        <SessionOverviewSlide
          analytics={analyticsData}
          moments={contextsData.moments}
          starredMomentIds={starredMomentIds}
        />
      );
    }
    if (slide.id === 'critical') {
      return (
        <CriticalMomentsSlide
          moments={contextsData.moments}
          momentKeyframes={momentKeyframes}
          personMeta={personMeta}
          momentFrameUrls={momentFrameUrls}
        />
      );
    }
    if (slide.id.startsWith('moment_')) {
      const momentId = parseInt(slide.id.replace('moment_', ''), 10);
      const moment = contextsData.moments.find(m => m.moment_id === momentId);
      const idx = starredMoments.findIndex(m => m.moment_id === momentId);
      if (!moment) return null;
      return (
        <MomentDeepDiveSlide
          moment={moment}
          index={idx}
          total={starredMoments.length}
          speakerRoles={contextsData.speaker_roles}
        />
      );
    }
    if (slide.id === 'dynamics') {
      return (
        <TeamDynamicsSlide
          analytics={analyticsData}
          moments={contextsData.moments}
        />
      );
    }
    if (slide.id === 'outcomes') {
      return (
        <LearningOutcomesSlide
          moments={contextsData.moments}
          momentKeyframes={momentKeyframes}
          personMeta={personMeta}
          momentFrameUrls={momentFrameUrls}
        />
      );
    }
    if (slide.id === 'action') {
      return (
        <ActionPlanSlide
          moments={contextsData.moments}
          analytics={analyticsData}
          speakerRoles={contextsData.speaker_roles}
        />
      );
    }
    return null;
  }

  const currentSlideObj = slides[currentSlide];

  return (
    <div className="fixed inset-0 z-50 bg-gray-900 flex flex-col">
      {/* Top bar */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 bg-gray-800 text-white">
        <span className="text-sm font-medium text-gray-300">
          {currentSlideObj?.label}
        </span>

        <div className="flex items-center gap-1.5">
          {slides.map((s, i) => (
            <button
              key={s.id}
              onClick={() => goTo(i)}
              className={`w-2 h-2 rounded-full transition-colors ${
                i === currentSlide ? 'bg-white' : 'bg-gray-600 hover:bg-gray-400'
              }`}
              title={s.label}
            />
          ))}
          <span className="ml-3 text-xs text-gray-400">
            {currentSlide + 1} / {slides.length}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={toggleFullscreen} className="p-1.5 rounded hover:bg-gray-700 text-gray-400">
            {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-gray-700 text-gray-400">
            <X size={16} />
          </button>
        </div>
      </div>

      {/* Slide content — 150% zoom, scrollable */}
      <div className="flex-1 overflow-auto bg-gray-950">
        <div className="h-full" style={{ zoom: 1.5 }}>
          {currentSlideObj && renderSlide(currentSlideObj)}
        </div>
      </div>

      {/* Bottom nav */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-3 bg-gray-800">
        <button
          onClick={() => goTo(currentSlide - 1)}
          disabled={currentSlide === 0}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-gray-300 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <ChevronLeft size={16} />
          Previous
        </button>

        <div className="hidden md:flex gap-1">
          {slides.map((s, i) => (
            <button
              key={s.id}
              onClick={() => goTo(i)}
              className={`px-3 py-1 rounded text-xs transition-colors ${
                i === currentSlide
                  ? 'bg-white text-gray-900 font-semibold'
                  : 'text-gray-400 hover:bg-gray-700'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>

        <button
          onClick={() => goTo(currentSlide + 1)}
          disabled={currentSlide === slides.length - 1}
          className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-medium text-gray-300 hover:bg-gray-700 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          Next
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  );
}
