import { useState, useEffect, useRef } from 'react';
import { StudentSummary, StudentFeedback } from '@/types';
import { useSessionStore } from '@/stores/sessionStore';
import { StudentSelector } from '@/components/StudentSelector';
import { DoctorReviewPanel } from '@/components/DoctorReview';
import { EvidenceChainView } from '@/components/EvidenceChain';
import { StudentPresentationMode } from '@/components/PresentationMode';
import {
  ArrowLeft,
  Play,
  Presentation,
  RefreshCw,
  AlertCircle,
  Video,
  FileText,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

interface Props {
  sessionId: string;
  evaluatorId: string;
  onBack?: () => void;
}

interface DoctorAction {
  action_type: string;
  timestamp: Date;
  section: string;
  field_path?: string;
  original_content: any;
  modified_content: any;
  time_spent_seconds: number;
}

export const DoctorReviewPage = ({ sessionId, evaluatorId, onBack }: Props) => {
  const [selectedStudent, setSelectedStudent] = useState<StudentSummary | null>(null);
  const [feedback, setFeedback] = useState<StudentFeedback | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activePanel, setActivePanel] = useState<'review' | 'evidence' | 'video'>('review');
  const [showPresentation, setShowPresentation] = useState(false);
  const [videoTime, setVideoTime] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  // Capture handoff context once on mount (one-shot bridge from DebriefView)
  const handoffRef = useRef({
    time: useSessionStore.getState().currentTime,
    studentId: useSessionStore.getState().selectedStudentId,
  });

  // Auto-select student on mount
  useEffect(() => {
    const { studentId: handoffStudentId } = handoffRef.current;
    if (handoffStudentId) {
      // Clear one-shot so navigating back doesn't re-trigger
      useSessionStore.getState().setSelectedStudentId(null);
    }

    const autoSelect = async () => {
      try {
        const response = await fetch(`/api/students/session/${sessionId}`);
        if (!response.ok) return;
        const students: StudentSummary[] = await response.json();
        if (!students.length) return;

        if (handoffStudentId) {
          const target = students.find(s => s.student_id === handoffStudentId);
          if (target) { setSelectedStudent(target); return; }
        }

        // Fall back: first non-draft, else first
        const nonDraft = students.find(s => s.feedback_status !== 'draft');
        setSelectedStudent(nonDraft ?? students[0]);
      } catch {
        // silent — StudentSelector still shows the list
      }
    };

    autoSelect();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Apply handoff video time when video panel becomes active
  useEffect(() => {
    const { time: handoffTime } = handoffRef.current;
    if (activePanel === 'video' && videoRef.current && handoffTime > 0) {
      videoRef.current.currentTime = handoffTime;
    }
  }, [activePanel]);

  useEffect(() => {
    if (selectedStudent) {
      fetchStudentFeedback(selectedStudent.student_id);
    }
  }, [selectedStudent]);

  const fetchStudentFeedback = async (studentId: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/students/${studentId}/feedback?session_id=${sessionId}`
      );
      if (!response.ok) {
        if (response.status === 404) {
          setFeedback(null);
          setError('No feedback generated yet. Generate feedback first.');
          return;
        }
        throw new Error('Failed to fetch feedback');
      }
      const data = await response.json();
      setFeedback(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setFeedback(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveReview = async (updatedFeedback: StudentFeedback, actions: DoctorAction[]) => {
    if (!selectedStudent) return;

    try {
      // Save feedback updates
      const feedbackResponse = await fetch(
        `/api/students/${selectedStudent.student_id}/edit?session_id=${sessionId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            section: 'full_feedback',
            field_path: '',
            original_value: feedback,
            new_value: updatedFeedback,
            evaluator_id: evaluatorId
          })
        }
      );

      if (!feedbackResponse.ok) {
        throw new Error('Failed to save feedback');
      }

      // Preserve educator actions as an audit trail; no model-training path consumes it.
      for (const action of actions) {
        await fetch('/api/interactions/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            interaction_type: 'educator_amendment',
            data: {
              student_id: selectedStudent.student_id,
              evaluator_id: evaluatorId,
              action_type: action.action_type,
              section: action.section,
              field_path: action.field_path,
              original_content: action.original_content,
              modified_content: action.modified_content,
              time_spent_seconds: action.time_spent_seconds,
              timestamp: action.timestamp.toISOString()
            }
          })
        });
      }

      // Refresh feedback
      await fetchStudentFeedback(selectedStudent.student_id);

      alert('Review saved successfully!');
    } catch (err) {
      console.error('Failed to save:', err);
      alert('Failed to save review. Please try again.');
    }
  };

  const handleJumpToVideo = (startTime: number, endTime: number) => {
    setVideoTime(startTime);
    setActivePanel('video');
    if (videoRef.current) {
      videoRef.current.currentTime = startTime;
      videoRef.current.play();
    }
  };

  const handleValidateEvidence = async (evidenceId: string, validated: boolean) => {
    if (!selectedStudent) return;

    try {
      await fetch(
        `/api/students/${selectedStudent.student_id}/validate-evidence?session_id=${sessionId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            evidence_id: evidenceId,
            validated,
            notes: null
          })
        }
      );

      // Log as an immutable educator audit action.
      await fetch('/api/interactions/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          interaction_type: 'educator_evidence_action',
          data: {
            student_id: selectedStudent.student_id,
            evaluator_id: evaluatorId,
            action_type: validated ? 'validate_evidence' : 'reject_evidence',
            section: 'evidence_chain',
            field_path: evidenceId,
            original_content: { validated: !validated },
            modified_content: { validated },
            time_spent_seconds: 0
          }
        })
      });

      await fetchStudentFeedback(selectedStudent.student_id);
    } catch (err) {
      console.error('Failed to validate evidence:', err);
    }
  };

  if (showPresentation && feedback) {
    return (
      <StudentPresentationMode
        sessionId={feedback.session_id}
        studentId={feedback.student_id}
        onClose={() => setShowPresentation(false)}
        onVideoTimeChange={(time) => {
          setVideoTime(time);
          if (videoRef.current) {
            videoRef.current.currentTime = time;
          }
        }}
      />
    );
  }

  return (
    <div className="h-screen flex bg-gray-100">
      {/* Left Sidebar: Student Selector */}
      <div className={`${sidebarCollapsed ? 'w-12' : 'w-72'} flex-shrink-0 bg-white border-r border-gray-200 flex flex-col transition-all duration-200`}>
        {onBack && !sidebarCollapsed && (
          <button
            onClick={onBack}
            className="flex items-center gap-2 px-4 py-3 text-sm text-gray-600 hover:text-gray-900 border-b border-gray-200"
          >
            <ArrowLeft size={16} />
            Back
          </button>
        )}

        <button
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 bg-white border border-gray-200 rounded-r-lg p-1 shadow-sm hover:bg-gray-50"
          style={{ left: sidebarCollapsed ? '48px' : '288px' }}
        >
          {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>

        {!sidebarCollapsed && (
          <div className="flex-1 overflow-hidden">
            <StudentSelector
              sessionId={sessionId}
              selectedStudentId={selectedStudent?.student_id}
              onSelectStudent={setSelectedStudent}
            />
          </div>
        )}
      </div>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selectedStudent ? (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <FileText size={48} className="mx-auto text-gray-300 mb-4" />
              <p className="text-lg">Select a student to review</p>
              <p className="text-sm mt-1">Choose from the list on the left</p>
            </div>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="bg-white border-b border-gray-200 px-6 py-4">
              <div className="flex items-center justify-between">
                <div>
                  <h1 className="text-xl font-semibold text-gray-900">
                    Doctor Review
                  </h1>
                  <p className="text-sm text-gray-500">
                    {selectedStudent.student_name || selectedStudent.student_id} • {selectedStudent.role}
                  </p>
                </div>

                <div className="flex items-center gap-3">
                  {/* Panel Toggle */}
                  <div className="flex rounded-lg border border-gray-200 overflow-hidden">
                    <button
                      onClick={() => setActivePanel('review')}
                      className={`px-4 py-2 text-sm font-medium flex items-center gap-2 ${
                        activePanel === 'review'
                          ? 'bg-blue-600 text-white'
                          : 'bg-white text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      <FileText size={16} />
                      Review
                    </button>
                    <button
                      onClick={() => setActivePanel('evidence')}
                      className={`px-4 py-2 text-sm font-medium flex items-center gap-2 ${
                        activePanel === 'evidence'
                          ? 'bg-blue-600 text-white'
                          : 'bg-white text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      <AlertCircle size={16} />
                      Evidence
                    </button>
                    <button
                      onClick={() => setActivePanel('video')}
                      className={`px-4 py-2 text-sm font-medium flex items-center gap-2 ${
                        activePanel === 'video'
                          ? 'bg-blue-600 text-white'
                          : 'bg-white text-gray-600 hover:bg-gray-50'
                      }`}
                    >
                      <Video size={16} />
                      Video
                    </button>
                  </div>

                  {/* Presentation Button */}
                  {feedback && (
                    <button
                      onClick={() => setShowPresentation(true)}
                      className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 flex items-center gap-2 text-sm font-medium"
                    >
                      <Presentation size={16} />
                      Present
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-hidden flex">
              {loading ? (
                <div className="flex-1 flex items-center justify-center">
                  <RefreshCw size={24} className="animate-spin text-gray-400" />
                </div>
              ) : error && !feedback ? (
                <div className="flex-1 flex items-center justify-center">
                  <div className="text-center">
                    <AlertCircle size={32} className="mx-auto text-amber-400 mb-2" />
                    <p className="text-gray-600">{error}</p>
                  </div>
                </div>
              ) : feedback ? (
                <>
                  {/* Review Panel */}
                  {activePanel === 'review' && (
                    <div className="flex-1 p-6 overflow-y-auto">
                      <DoctorReviewPanel
                        feedback={feedback}
                        sessionId={sessionId}
                        evaluatorId={evaluatorId}
                        onSave={handleSaveReview}
                        onJumpToVideo={handleJumpToVideo}
                      />
                    </div>
                  )}

                  {/* Evidence Panel */}
                  {activePanel === 'evidence' && (
                    <div className="flex-1 p-6 overflow-y-auto">
                      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
                        <EvidenceChainView
                          evidenceChain={feedback.evidence_chain}
                          onValidateEvidence={handleValidateEvidence}
                          onJumpToVideo={handleJumpToVideo}
                        />
                      </div>
                    </div>
                  )}

                  {/* Video Panel */}
                  {activePanel === 'video' && (
                    <div className="flex-1 p-6 overflow-y-auto">
                      <div className="bg-black rounded-lg overflow-hidden aspect-video max-h-[60vh]">
                        <video
                          ref={videoRef}
                          src={`/api/videos/cam1`}
                          className="w-full h-full"
                          controls
                          playsInline
                        />
                      </div>

                      {/* Video clips from evidence */}
                      <div className="mt-4 bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                        <h3 className="font-semibold text-gray-900 mb-3">Evidence Clips</h3>
                        <div className="grid grid-cols-3 gap-3">
                          {feedback.evidence_chain.evidence_links.slice(0, 9).map((link, idx) => (
                            <button
                              key={idx}
                              onClick={() => handleJumpToVideo(link.timestamp_start, link.timestamp_end)}
                              className="p-3 bg-gray-50 rounded-lg hover:bg-gray-100 text-left transition-colors"
                            >
                              <div className="flex items-center gap-2 text-sm font-medium text-gray-900">
                                <Play size={14} className="text-blue-600" />
                                {Math.floor(link.timestamp_start / 60)}:{(link.timestamp_start % 60).toFixed(0).padStart(2, '0')}
                              </div>
                              <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                                {link.ai_interpretation}
                              </p>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex-1 flex items-center justify-center text-gray-500">
                  No feedback available
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default DoctorReviewPage;
