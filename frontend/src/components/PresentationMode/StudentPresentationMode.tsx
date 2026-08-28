import React, { useState, useEffect, useRef } from 'react';
import { api } from '@/services/api';
import {
  ChevronLeft,
  ChevronRight,
  X,
  Download,
  Play,
  Pause,
  CheckCircle,
  AlertCircle,
  Lightbulb,
  Clock,
  Video,
  User,
  Activity,
  Users,
  Brain,
  Target,
  BookOpen,
  MessageCircle,
  Star,
  Loader2
} from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

interface Slide {
  slide_number: number;
  type: string;
  title: string;
  subtitle?: string;
  content: any;
  video_clip?: {
    start: number;
    end: number;
    duration?: number;
    cameras?: string[];
    camera?: string;
  };
  presenter_notes?: string | string[];
  discussion_prompts?: string[];
  duration_suggestion?: number; // seconds
  [key: string]: any;
}

interface StudentPresentationModeProps {
  sessionId: string;
  studentId: string;
  onClose: () => void;
  onVideoTimeChange?: (time: number) => void;
}

// ============================================================================
// Helper Functions
// ============================================================================

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const getRatingLabel = (rating: number): string => {
  const labels: Record<number, string> = {
    1: 'Needs Improvement',
    2: 'Below Average',
    3: 'Average',
    4: 'Above Average',
    5: 'Excellent'
  };
  return labels[rating] || 'Not Rated';
};

const getRatingColor = (rating: number): string => {
  if (rating >= 4) return 'text-green-600 bg-green-50';
  if (rating >= 3) return 'text-amber-600 bg-amber-50';
  return 'text-red-600 bg-red-50';
};

// ============================================================================
// Slide Components
// ============================================================================

const TitleSlide: React.FC<{ slide: Slide }> = ({ slide }) => (
  <div className="flex flex-col items-center justify-center h-full px-16 py-12 bg-gradient-to-br from-blue-50 to-white">
    <div className="max-w-4xl w-full text-center">
      <div className="mb-8">
        <div className="w-20 h-20 mx-auto bg-blue-100 rounded-full flex items-center justify-center mb-6">
          <User size={40} className="text-blue-600" />
        </div>
        <h1 className="text-5xl font-bold text-gray-900 mb-4">{slide.title}</h1>
        <p className="text-3xl text-blue-600 font-medium">{slide.subtitle}</p>
      </div>

      <div className="mt-12 pt-8 border-t border-gray-200">
        <div className="grid grid-cols-2 gap-8 text-left max-w-2xl mx-auto">
          <div>
            <p className="text-sm text-gray-500 uppercase tracking-wide font-semibold mb-1">Role</p>
            <p className="text-xl text-gray-900">{slide.content.role}</p>
          </div>
          <div>
            <p className="text-sm text-gray-500 uppercase tracking-wide font-semibold mb-1">Scenario</p>
            <p className="text-xl text-gray-900">{slide.content.scenario_type || 'Clinical Simulation'}</p>
          </div>
        </div>
      </div>
    </div>
  </div>
);

const ScenarioSlide: React.FC<{ slide: Slide }> = ({ slide }) => (
  <div className="h-full px-16 py-12 overflow-y-auto">
    <h1 className="text-4xl font-bold text-gray-900 mb-8">{slide.title}</h1>

    <div className="grid grid-cols-2 gap-8">
      <div className="space-y-6">
        <div className="bg-blue-50 border-l-4 border-blue-600 p-6 rounded-r-lg">
          <h3 className="text-sm font-bold text-blue-900 uppercase tracking-wide mb-3">
            Patient Presentation
          </h3>
          <p className="text-lg text-gray-900">{slide.content.patient_presentation}</p>
        </div>

        <div className="bg-gray-50 border-l-4 border-gray-400 p-6 rounded-r-lg">
          <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-3">
            Clinical Context
          </h3>
          <p className="text-lg text-gray-900">{slide.content.clinical_context}</p>
        </div>
      </div>

      <div>
        <h3 className="text-sm font-bold text-gray-700 uppercase tracking-wide mb-4">
          Learning Objectives
        </h3>
        <div className="space-y-3">
          {slide.content.learning_objectives?.map((obj: string, idx: number) => (
            <div key={idx} className="flex items-start gap-3 bg-white p-4 rounded-lg border border-gray-200">
              <div className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold flex-shrink-0">
                {idx + 1}
              </div>
              <p className="text-gray-900">{obj}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  </div>
);

const ClinicalSkillSlide: React.FC<{ slide: Slide; onPlayClip?: () => void }> = ({ slide, onPlayClip }) => {
  const content = slide.content || {};
  // Server sends rating, client may send performance_rating
  const rating = content.rating ?? content.performance_rating ?? 0;
  const summary = content.summary || '';
  const observations = content.observations || [];

  return (
    <div className="h-full flex px-12 py-10 gap-10">
      {/* Left: Video and context */}
      <div className="w-1/2 flex flex-col">
        <div className="mb-4">
          <div className="flex items-center gap-3 mb-2">
            <Activity size={24} className="text-blue-600" />
            <h1 className="text-3xl font-bold text-gray-900">{slide.title}</h1>
          </div>
          {slide.subtitle && (
            <p className="text-gray-500 ml-9">{slide.subtitle}</p>
          )}
        </div>

        {/* Rating */}
        <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full mb-4 ${getRatingColor(rating)}`}>
          <div className="flex">
            {[1, 2, 3, 4, 5].map(star => (
              <Star
                key={star}
                size={16}
                className={star <= rating ? 'fill-current' : 'opacity-30'}
              />
            ))}
          </div>
          <span className="font-medium">{getRatingLabel(rating)}</span>
        </div>

        {/* Video placeholder */}
        {slide.video_clip && slide.video_clip.start != null && (
          <div className="flex-1 bg-gray-900 rounded-xl overflow-hidden relative min-h-[300px]">
            <div className="absolute inset-0 flex items-center justify-center">
              <button
                onClick={onPlayClip}
                className="flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Play size={20} />
                Play Clip ({formatTime(slide.video_clip.start)} - {formatTime(slide.video_clip.end)})
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Right: Observations and feedback */}
      <div className="w-1/2 flex flex-col justify-center space-y-4">
        {summary && (
          <div className="bg-blue-50 border-l-4 border-blue-600 p-5 rounded-r-lg">
            <p className="text-lg text-gray-900">{summary}</p>
          </div>
        )}

        {observations.length > 0 && (
          <div>
            <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wide mb-3">
              Observations
            </h3>
            <div className="space-y-3 max-h-[300px] overflow-y-auto">
              {observations.map((obs: any, idx: number) => (
                <div key={idx} className="bg-white p-4 rounded-lg border border-gray-200">
                  <p className="text-gray-900 mb-2">{obs.description}</p>
                  <div className="flex items-center gap-2 text-sm text-gray-500">
                    <Clock size={14} />
                    <span>{obs.timestamp}</span>
                    {obs.evidence_source && (
                      <span className="px-2 py-0.5 bg-gray-100 rounded text-xs uppercase">
                        {obs.evidence_source}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const ABCDESlide: React.FC<{ slide: Slide }> = ({ slide }) => {
  const abcde = slide.content;
  const components = [
    { key: 'airway', label: 'A - Airway', data: abcde.airway },
    { key: 'breathing', label: 'B - Breathing', data: abcde.breathing },
    { key: 'circulation', label: 'C - Circulation', data: abcde.circulation },
    { key: 'disability', label: 'D - Disability', data: abcde.disability },
    { key: 'exposure', label: 'E - Exposure', data: abcde.exposure }
  ];

  return (
    <div className="h-full px-12 py-10 overflow-y-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-gray-900">{slide.title}</h1>
        <div className={`flex items-center gap-2 px-4 py-2 rounded-full ${
          abcde.overall_sequence_followed ? 'bg-green-100 text-green-700' : 'bg-amber-100 text-amber-700'
        }`}>
          {abcde.overall_sequence_followed ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
          <span className="font-medium">
            {abcde.overall_sequence_followed ? 'Sequence Followed' : 'Sequence Incomplete'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-4">
        {components.map(({ key, label, data }) => (
          <div key={key} className="bg-white rounded-lg border-2 border-gray-200 overflow-hidden">
            <div className="bg-gray-100 px-4 py-3 border-b border-gray-200">
              <h3 className="font-bold text-gray-900">{label}</h3>
            </div>
            <div className="p-4 space-y-3">
              <p className="text-sm text-gray-700">{data.status}</p>
              {data.rating && (
                <div className="flex">
                  {[1, 2, 3, 4, 5].map(star => (
                    <Star
                      key={star}
                      size={14}
                      className={star <= data.rating ? 'text-amber-400 fill-amber-400' : 'text-gray-300'}
                    />
                  ))}
                </div>
              )}
              {data.actions_taken?.length > 0 && (
                <div className="text-xs text-gray-500">
                  {data.actions_taken.length} action(s)
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const NTSOverviewSlide: React.FC<{ slide: Slide }> = ({ slide }) => {
  const nts = slide.content || {};
  const components = [
    { name: 'Communication', key: 'communication', icon: MessageCircle },
    { name: 'Teamwork', key: 'teamwork', icon: Users },
    { name: 'Leadership', key: 'leadership', icon: User },
    { name: 'Situational Awareness', key: 'situational_awareness', icon: Brain },
    { name: 'Decision Making', key: 'decision_making', icon: Target }
  ];

  return (
    <div className="h-full px-12 py-10">
      <h1 className="text-3xl font-bold text-gray-900 mb-8">{slide.title}</h1>

      <div className="grid grid-cols-5 gap-6">
        {components.map(({ name, key, icon: Icon }) => {
          const data = nts[key] || {};
          const rating = data.rating || 0;
          return (
            <div key={name} className="text-center">
              <div className="w-20 h-20 mx-auto bg-blue-50 rounded-full flex items-center justify-center mb-4">
                <Icon size={32} className="text-blue-600" />
              </div>
              <h3 className="font-medium text-gray-900 mb-2">{name}</h3>
              <div className="flex justify-center mb-2">
                {[1, 2, 3, 4, 5].map(star => (
                  <Star
                    key={star}
                    size={16}
                    className={star <= rating ? 'text-amber-400 fill-amber-400' : 'text-gray-300'}
                  />
                ))}
              </div>
              <p className="text-sm text-gray-500">{getRatingLabel(rating)}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const NTSSkillSlide: React.FC<{ slide: Slide }> = ({ slide }) => {
  const content = slide.content || {};
  const rating = content.rating || 0;
  const strengths = content.strengths || [];
  const areas = content.areas_for_improvement || [];
  const observations = content.observations || [];

  return (
    <div className="h-full px-12 py-10">
      <div className="flex items-center gap-3 mb-6">
        <Users size={28} className="text-blue-600" />
        <h1 className="text-3xl font-bold text-gray-900">{slide.title}</h1>
        <div className={`ml-auto px-4 py-2 rounded-full ${getRatingColor(rating)}`}>
          <div className="flex items-center gap-2">
            {[1, 2, 3, 4, 5].map(star => (
              <Star
                key={star}
                size={16}
                className={star <= rating ? 'fill-current' : 'opacity-30'}
              />
            ))}
            <span className="font-medium ml-2">{getRatingLabel(rating)}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8">
        <div className="space-y-4">
          {strengths.length > 0 && (
            <div className="bg-green-50 border-l-4 border-green-600 p-5 rounded-r-lg">
              <h3 className="flex items-center gap-2 text-sm font-bold text-green-900 uppercase tracking-wide mb-3">
                <CheckCircle size={18} />
                Strengths
              </h3>
              <ul className="space-y-2">
                {strengths.map((s: string, idx: number) => (
                  <li key={idx} className="text-green-800">{s}</li>
                ))}
              </ul>
            </div>
          )}

          {areas.length > 0 && (
            <div className="bg-amber-50 border-l-4 border-amber-600 p-5 rounded-r-lg">
              <h3 className="flex items-center gap-2 text-sm font-bold text-amber-900 uppercase tracking-wide mb-3">
                <AlertCircle size={18} />
                Areas for Improvement
              </h3>
              <ul className="space-y-2">
                {areas.map((a: string, idx: number) => (
                  <li key={idx} className="text-amber-800">{a}</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div>
          {observations.length > 0 && (
            <>
              <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wide mb-3">
                Observations
              </h3>
              <div className="space-y-3 max-h-[400px] overflow-y-auto">
                {observations.map((obs: any, idx: number) => (
                  <div key={idx} className="bg-white p-4 rounded-lg border border-gray-200">
                    <p className="text-gray-900 mb-2">{obs.description}</p>
                    <div className="flex items-center gap-2 text-sm text-gray-500">
                      <Clock size={14} />
                      <span>{obs.timestamp}</span>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const CRMSlide: React.FC<{ slide: Slide }> = ({ slide }) => {
  const crm = slide.content;

  const principles = [
    { key: 'knew_environment', label: 'Knew Environment' },
    { key: 'mobilized_resources', label: 'Mobilized Resources' },
    { key: 'prevented_fixation', label: 'Prevented Fixation' },
    { key: 'cross_checked', label: 'Cross-Checked' },
    { key: 'used_cognitive_aids', label: 'Used Cognitive Aids' },
    { key: 're_evaluated', label: 'Re-evaluated' },
    { key: 'set_priorities', label: 'Set Priorities' }
  ];

  return (
    <div className="h-full px-12 py-10">
      <div className="flex items-center gap-3 mb-6">
        <Brain size={28} className="text-purple-600" />
        <h1 className="text-3xl font-bold text-gray-900">{slide.title}</h1>
      </div>

      <div className="grid grid-cols-2 gap-8">
        <div>
          <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wide mb-4">
            CRM Principles
          </h3>
          <div className="grid grid-cols-2 gap-2">
            {principles.map(({ key, label }) => {
              const value = crm[key];
              if (value === undefined || value === null) return null;

              return (
                <div
                  key={key}
                  className={`flex items-center gap-2 p-3 rounded-lg ${
                    value ? 'bg-green-50' : 'bg-red-50'
                  }`}
                >
                  {value ? (
                    <CheckCircle size={16} className="text-green-600" />
                  ) : (
                    <AlertCircle size={16} className="text-red-600" />
                  )}
                  <span className={`text-sm font-medium ${value ? 'text-green-700' : 'text-red-700'}`}>
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-4">
          {crm.strengths?.length > 0 && (
            <div className="bg-green-50 border-l-4 border-green-600 p-5 rounded-r-lg">
              <h3 className="text-sm font-bold text-green-900 uppercase tracking-wide mb-2">
                Strengths
              </h3>
              <ul className="space-y-1">
                {crm.strengths.map((s: string, idx: number) => (
                  <li key={idx} className="text-green-800">• {s}</li>
                ))}
              </ul>
            </div>
          )}

          {crm.areas_for_development?.length > 0 && (
            <div className="bg-amber-50 border-l-4 border-amber-600 p-5 rounded-r-lg">
              <h3 className="text-sm font-bold text-amber-900 uppercase tracking-wide mb-2">
                Areas for Development
              </h3>
              <ul className="space-y-1">
                {crm.areas_for_development.map((a: string, idx: number) => (
                  <li key={idx} className="text-amber-800">• {a}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const LearningOutcomesSlide: React.FC<{ slide: Slide }> = ({ slide }) => {
  const outcomes = slide.content;

  return (
    <div className="h-full px-12 py-10">
      <div className="flex items-center gap-3 mb-8">
        <Target size={28} className="text-blue-600" />
        <h1 className="text-3xl font-bold text-gray-900">{slide.title}</h1>
      </div>

      <div className="grid grid-cols-2 gap-8">
        {outcomes.key_achievements?.length > 0 && (
          <div className="bg-green-50 rounded-xl p-6">
            <h3 className="flex items-center gap-2 text-lg font-bold text-green-900 mb-4">
              <CheckCircle size={20} />
              Key Achievements
            </h3>
            <ul className="space-y-3">
              {outcomes.key_achievements.map((a: string, idx: number) => (
                <li key={idx} className="flex items-start gap-2 text-green-800">
                  <span className="text-green-600 mt-1">✓</span>
                  {a}
                </li>
              ))}
            </ul>
          </div>
        )}

        {outcomes.areas_for_improvement?.length > 0 && (
          <div className="bg-amber-50 rounded-xl p-6">
            <h3 className="flex items-center gap-2 text-lg font-bold text-amber-900 mb-4">
              <AlertCircle size={20} />
              Areas for Improvement
            </h3>
            <ul className="space-y-3">
              {outcomes.areas_for_improvement.map((a: string, idx: number) => (
                <li key={idx} className="flex items-start gap-2 text-amber-800">
                  <span className="text-amber-600 mt-1">→</span>
                  {a}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};

const ActionPlanSlide: React.FC<{ slide: Slide }> = ({ slide }) => (
  <div className="h-full px-12 py-10">
    <h1 className="text-3xl font-bold text-gray-900 mb-2">{slide.title}</h1>
    {slide.subtitle && <p className="text-gray-500 mb-8">{slide.subtitle}</p>}

    <div className="max-w-3xl">
      <div className="space-y-4">
        {slide.content.action_items?.map((item: string, idx: number) => (
          <div key={idx} className="flex items-start gap-4 bg-white p-5 rounded-xl border-2 border-gray-200">
            <div className="w-10 h-10 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold flex-shrink-0">
              {idx + 1}
            </div>
            <p className="text-lg text-gray-900 pt-1">{item}</p>
          </div>
        ))}
      </div>
    </div>
  </div>
);

const DiscussionSlide: React.FC<{ slide: Slide }> = ({ slide }) => (
  <div className="h-full flex flex-col items-center justify-center px-16 py-12 bg-gradient-to-br from-purple-50 to-white">
    <div className="text-center max-w-3xl">
      <MessageCircle size={48} className="mx-auto text-purple-600 mb-6" />
      <h1 className="text-4xl font-bold text-gray-900 mb-4">{slide.title}</h1>
      <p className="text-xl text-gray-500 mb-12">{slide.subtitle}</p>

      <div className="grid grid-cols-2 gap-6 text-left">
        {slide.content.prompts?.map((prompt: string, idx: number) => (
          <div key={idx} className="bg-white p-6 rounded-xl border-2 border-purple-200">
            <p className="text-lg text-gray-900 italic">"{prompt}"</p>
          </div>
        ))}
      </div>
    </div>
  </div>
);

const SummarySlide: React.FC<{ slide: Slide }> = ({ slide }) => (
  <div className="h-full flex flex-col items-center justify-center px-16 py-12 bg-gradient-to-br from-green-50 to-white">
    <div className="text-center max-w-3xl">
      <CheckCircle size={48} className="mx-auto text-green-600 mb-6" />
      <h1 className="text-4xl font-bold text-gray-900 mb-4">{slide.title}</h1>

      {slide.content.debrief_summary && (
        <p className="text-xl text-gray-600 mb-12 leading-relaxed">
          {slide.content.debrief_summary}
        </p>
      )}

      <div className="grid grid-cols-2 gap-8 text-left">
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <div className="text-3xl font-bold text-green-600 mb-2">
            {slide.content.key_achievements?.length || 0}
          </div>
          <div className="text-gray-600">Key Achievements</div>
        </div>
        <div className="bg-white p-6 rounded-xl border border-gray-200">
          <div className="text-3xl font-bold text-blue-600 mb-2">
            {slide.content.evidence_count || 0}
          </div>
          <div className="text-gray-600">Evidence Links</div>
        </div>
      </div>
    </div>
  </div>
);

// ============================================================================
// Main Component
// ============================================================================

export const StudentPresentationMode: React.FC<StudentPresentationModeProps> = ({
  sessionId,
  studentId,
  onClose,
  onVideoTimeChange
}) => {
  const [slides, setSlides] = useState<Slide[]>([]);
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const currentSlide = slides[currentSlideIndex];

  useEffect(() => {
    const fetchSlides = async () => {
      try {
        setLoadError(null);
        const response = await api.generateStudentSlides({
          session_id: sessionId,
          student_id: studentId,
        });
        setSlides(response.slides);
      } catch (error) {
        console.error('Failed to load slides from API:', error);
        setLoadError('Failed to load slides. Please try again.');
      }
    };
    fetchSlides();
  }, [sessionId, studentId]);

  const exportToPowerPoint = async () => {
    try {
      setExporting(true);
      const blob = await api.exportStudentToPowerPoint({
        session_id: sessionId,
        student_id: studentId,
      });

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `debrief-${studentId}-${sessionId}.pptx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setExporting(false);
    }
  };

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight' || e.key === ' ') {
        nextSlide();
      } else if (e.key === 'ArrowLeft') {
        prevSlide();
      } else if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentSlideIndex, slides.length]);

  const goToSlide = (index: number) => {
    if (index >= 0 && index < slides.length) {
      setCurrentSlideIndex(index);
    }
  };

  const nextSlide = () => goToSlide(currentSlideIndex + 1);
  const prevSlide = () => goToSlide(currentSlideIndex - 1);

  const playVideoClip = () => {
    if (currentSlide?.video_clip && onVideoTimeChange) {
      onVideoTimeChange(currentSlide.video_clip.start);
    }
  };

  if (loadError) {
    return (
      <div className="fixed inset-0 bg-white z-50 flex items-center justify-center">
        <div className="text-center">
          <AlertCircle size={48} className="mx-auto text-red-500 mb-4" />
          <div className="text-gray-700 text-lg font-medium mb-4">{loadError}</div>
          <button
            onClick={onClose}
            className="px-6 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  if (slides.length === 0) {
    return (
      <div className="fixed inset-0 bg-white z-50 flex items-center justify-center">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto"></div>
          <div className="text-gray-700 text-lg font-medium mt-4">Loading slides...</div>
        </div>
      </div>
    );
  }

  const renderSlide = () => {
    if (!currentSlide) return null;

    switch (currentSlide.type) {
      case 'title':
        return <TitleSlide slide={currentSlide} />;
      case 'scenario':
        return <ScenarioSlide slide={currentSlide} />;
      case 'clinical_skill':
        return <ClinicalSkillSlide slide={currentSlide} onPlayClip={playVideoClip} />;
      case 'abcde':
        return <ABCDESlide slide={currentSlide} />;
      case 'nts_overview':
        return <NTSOverviewSlide slide={currentSlide} />;
      case 'nts_skill':
        return <NTSSkillSlide slide={currentSlide} />;
      case 'crm':
        return <CRMSlide slide={currentSlide} />;
      case 'learning_outcomes':
        return <LearningOutcomesSlide slide={currentSlide} />;
      case 'action_plan':
        return <ActionPlanSlide slide={currentSlide} />;
      case 'discussion':
        return <DiscussionSlide slide={currentSlide} />;
      case 'summary':
        return <SummarySlide slide={currentSlide} />;
      default:
        return <div className="p-8">Unknown slide type</div>;
    }
  };

  return (
    <div className="fixed inset-0 bg-white z-50 flex flex-col">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">
            Slide {currentSlideIndex + 1} of {slides.length}
          </span>
          {currentSlide?.duration_suggestion && (
            <span className="text-xs text-gray-400 flex items-center gap-1">
              <Clock size={12} />
              ~{Math.ceil(currentSlide.duration_suggestion / 60)} min
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={exportToPowerPoint}
            disabled={exporting}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {exporting ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Exporting...
              </>
            ) : (
              <>
                <Download size={16} />
                Export to PowerPoint
              </>
            )}
          </button>
          <button
            onClick={onClose}
            className="p-2 text-gray-600 hover:text-gray-900 transition-colors"
          >
            <X size={24} />
          </button>
        </div>
      </div>

      {/* Slide Content */}
      <div className="flex-1 overflow-hidden">
        {renderSlide()}
      </div>

      {/* Presenter Notes (if any) */}
      {currentSlide?.presenter_notes && (
        <div className="bg-gray-50 border-t border-gray-200 px-6 py-3">
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-1">Presenter Notes</div>
          {typeof currentSlide.presenter_notes === 'string' ? (
            <p className="text-sm text-gray-700">{currentSlide.presenter_notes}</p>
          ) : Array.isArray(currentSlide.presenter_notes) ? (
            <ul className="text-sm text-gray-700 space-y-1">
              {currentSlide.presenter_notes.map((note: string, idx: number) => (
                <li key={idx}>• {note}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      {/* Navigation Footer */}
      <div className="bg-white border-t border-gray-200 px-8 py-4 flex items-center justify-between flex-shrink-0">
        <button
          onClick={prevSlide}
          disabled={currentSlideIndex === 0}
          className="flex items-center gap-2 px-6 py-2 text-gray-700 hover:text-gray-900 transition-colors disabled:opacity-30 disabled:cursor-not-allowed rounded-lg hover:bg-gray-50"
        >
          <ChevronLeft size={20} />
          Previous
        </button>

        <div className="flex items-center gap-1">
          {slides.map((_, index) => (
            <button
              key={index}
              onClick={() => goToSlide(index)}
              className={`h-2 rounded-full transition-all ${
                index === currentSlideIndex
                  ? 'bg-blue-600 w-8'
                  : 'bg-gray-300 hover:bg-gray-400 w-2'
              }`}
            />
          ))}
        </div>

        <button
          onClick={nextSlide}
          disabled={currentSlideIndex === slides.length - 1}
          className="flex items-center gap-2 px-6 py-2 text-gray-700 hover:text-gray-900 transition-colors disabled:opacity-30 disabled:cursor-not-allowed rounded-lg hover:bg-gray-50"
        >
          Next
          <ChevronRight size={20} />
        </button>
      </div>
    </div>
  );
};

export default StudentPresentationMode;
