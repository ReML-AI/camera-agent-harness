import { useState, useEffect } from 'react';
import { StudentSummary, StudentFeedback, TimestampedObservation } from '@/types';
import { StudentSelector } from '@/components/StudentSelector';
import { RichFeedbackPanel } from '@/components/FeedbackPanel';
import { EvidenceChainView } from '@/components/EvidenceChain';
import { RefreshCw, AlertCircle, ArrowLeft, Play } from 'lucide-react';

interface Props {
  sessionId: string;
  onBack?: () => void;
  onJumpToVideo?: (startTime: number, endTime: number, cameraId?: string) => void;
}

export const StudentFeedbackPage = ({ sessionId, onBack, onJumpToVideo }: Props) => {
  const [selectedStudent, setSelectedStudent] = useState<StudentSummary | null>(null);
  const [feedback, setFeedback] = useState<StudentFeedback | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState<'feedback' | 'evidence'>('feedback');

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
          setError('No feedback generated yet for this student');
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

  const handleValidateEvidence = async (evidenceId: string, validated: boolean) => {
    if (!selectedStudent || !feedback) return;

    try {
      const response = await fetch(
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

      if (response.ok) {
        // Refresh feedback to get updated validation status
        fetchStudentFeedback(selectedStudent.student_id);
      }
    } catch (err) {
      console.error('Failed to validate evidence:', err);
    }
  };

  const handleObservationClick = (observation: TimestampedObservation) => {
    if (onJumpToVideo && observation.timestamp_start) {
      onJumpToVideo(
        observation.timestamp_start,
        observation.timestamp_end || observation.timestamp_start + 5
      );
    }
  };

  const handleGenerateFeedback = async () => {
    if (!selectedStudent) return;

    setLoading(true);
    try {
      const response = await fetch(
        `/api/students/${selectedStudent.student_id}/generate?session_id=${sessionId}`,
        { method: 'POST' }
      );

      if (response.ok) {
        // Poll for completion or show message
        setError('Feedback generation started. Please refresh in a moment.');
      }
    } catch (err) {
      setError('Failed to start feedback generation');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-full flex bg-gray-50">
      {/* Left sidebar: Student selector */}
      <div className="w-80 flex-shrink-0 border-r border-gray-200">
        {onBack && (
          <button
            onClick={onBack}
            className="flex items-center gap-2 px-4 py-3 text-sm text-gray-600 hover:text-gray-900 border-b border-gray-200 w-full"
          >
            <ArrowLeft size={16} />
            Back to Session
          </button>
        )}
        <StudentSelector
          sessionId={sessionId}
          selectedStudentId={selectedStudent?.student_id}
          onSelectStudent={setSelectedStudent}
        />
      </div>

      {/* Main content area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {!selectedStudent ? (
          <div className="flex-1 flex items-center justify-center text-gray-500">
            <div className="text-center">
              <p className="text-lg">Select a student to view feedback</p>
              <p className="text-sm mt-1">Choose from the list on the left</p>
            </div>
          </div>
        ) : (
          <>
            {/* Header with view toggle */}
            <div className="flex items-center justify-between px-6 py-4 bg-white border-b border-gray-200">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  {selectedStudent.student_name || selectedStudent.student_id}
                </h2>
                <p className="text-sm text-gray-500">{selectedStudent.role}</p>
              </div>

              <div className="flex items-center gap-3">
                {/* View toggle */}
                <div className="flex rounded-lg border border-gray-200 overflow-hidden">
                  <button
                    onClick={() => setActiveView('feedback')}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      activeView === 'feedback'
                        ? 'bg-gray-900 text-white'
                        : 'bg-white text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Feedback
                  </button>
                  <button
                    onClick={() => setActiveView('evidence')}
                    className={`px-4 py-2 text-sm font-medium transition-colors ${
                      activeView === 'evidence'
                        ? 'bg-gray-900 text-white'
                        : 'bg-white text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    Evidence
                  </button>
                </div>

                {/* Generate button */}
                {(!feedback || feedback.status === 'draft') && (
                  <button
                    onClick={handleGenerateFeedback}
                    disabled={loading}
                    className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
                  >
                    {loading ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : (
                      <Play size={16} />
                    )}
                    Generate Feedback
                  </button>
                )}
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6">
              {loading ? (
                <div className="flex items-center justify-center h-64">
                  <RefreshCw size={24} className="animate-spin text-gray-400" />
                </div>
              ) : error && !feedback ? (
                <div className="flex items-center justify-center h-64">
                  <div className="text-center">
                    <AlertCircle size={32} className="mx-auto text-amber-400" />
                    <p className="mt-2 text-gray-600">{error}</p>
                    {selectedStudent.feedback_status === 'draft' && (
                      <button
                        onClick={handleGenerateFeedback}
                        className="mt-4 px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700"
                      >
                        Generate Feedback Now
                      </button>
                    )}
                  </div>
                </div>
              ) : feedback ? (
                activeView === 'feedback' ? (
                  <RichFeedbackPanel
                    feedback={feedback}
                    onObservationClick={handleObservationClick}
                    isEditable={feedback.status !== 'final'}
                  />
                ) : (
                  <EvidenceChainView
                    evidenceChain={feedback.evidence_chain}
                    onValidateEvidence={handleValidateEvidence}
                    onJumpToVideo={onJumpToVideo}
                  />
                )
              ) : (
                <div className="flex items-center justify-center h-64 text-gray-500">
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

export default StudentFeedbackPage;
