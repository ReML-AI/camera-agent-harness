import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/services/api';
import { useSessionStore } from '@/stores/sessionStore';
import { Star, Loader2, CheckCircle, ExternalLink, User } from 'lucide-react';

interface Props {
  sessionId: string;
  starredMomentIds: number[];
  onNavigateToReview: () => void;
}

const STATUS_BADGES: Record<string, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'bg-gray-100 text-gray-600' },
  ai_generated: { label: 'AI Generated', className: 'bg-blue-100 text-blue-700' },
  doctor_reviewed: { label: 'Reviewed', className: 'bg-green-100 text-green-700' },
  final: { label: 'Final', className: 'bg-green-100 text-green-800' },
};

export function FeedbackDrawerContent({ sessionId, starredMomentIds, onNavigateToReview }: Props) {
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(new Set());
  const [completedIds, setCompletedIds] = useState<Map<string, string>>(new Map()); // id → timestamp
  const [errors, setErrors] = useState<Map<string, string>>(new Map());

  const { data: students, isLoading } = useQuery({
    queryKey: ['students', sessionId],
    queryFn: () => api.getStudents(sessionId),
  });

  const handleGenerate = async (studentId: string) => {
    setGeneratingIds(prev => new Set(prev).add(studentId));
    setErrors(prev => { const m = new Map(prev); m.delete(studentId); return m; });
    try {
      await api.generateFeedback(studentId, sessionId);
      setCompletedIds(prev => new Map(prev).set(studentId, new Date().toLocaleTimeString()));
    } catch {
      setErrors(prev => new Map(prev).set(studentId, 'Generation failed. Check server logs.'));
    } finally {
      setGeneratingIds(prev => { const s = new Set(prev); s.delete(studentId); return s; });
    }
  };

  return (
    <div className="p-4 space-y-4">
      {/* Header banner */}
      <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
        <Star size={14} className="fill-amber-500 text-amber-500 flex-shrink-0" />
        <span className="text-sm text-amber-800 font-medium">
          {starredMomentIds.length} moment{starredMomentIds.length !== 1 ? 's' : ''} starred for debrief
        </span>
      </div>

      {/* Student list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 size={20} className="animate-spin text-blue-500" />
          <span className="ml-2 text-sm text-gray-500">Loading students...</span>
        </div>
      ) : !students?.length ? (
        <div className="text-center py-8">
          <User size={32} className="mx-auto text-gray-300 mb-2" />
          <p className="text-sm text-gray-500">No students found for this session.</p>
          <p className="text-xs text-gray-400 mt-1">Run the labeling pipeline to assign roles.</p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Students</p>
          {students.map((student) => {
            const isGenerating = generatingIds.has(student.student_id);
            const completedAt = completedIds.get(student.student_id);
            const error = errors.get(student.student_id);
            const badge = STATUS_BADGES[student.feedback_status] ?? STATUS_BADGES.draft;

            return (
              <div key={student.student_id} className="border border-gray-200 rounded-lg p-3">
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">
                      {student.student_name || student.student_id}
                    </p>
                    <p className="text-xs text-gray-500 truncate">{student.role}</p>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full flex-shrink-0 ${badge.className}`}>
                    {badge.label}
                  </span>
                </div>

                {/* Completion state */}
                {completedAt ? (
                  <div className="flex items-center gap-1.5 text-green-700 text-xs">
                    <CheckCircle size={13} />
                    <span>Generated at {completedAt}</span>
                  </div>
                ) : error ? (
                  <p className="text-xs text-red-600 mb-2">{error}</p>
                ) : null}

                <button
                  onClick={() => handleGenerate(student.student_id)}
                  disabled={isGenerating}
                  className={`mt-1.5 w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    isGenerating
                      ? 'bg-blue-100 text-blue-500 cursor-not-allowed'
                      : completedAt
                        ? 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        : 'bg-blue-600 text-white hover:bg-blue-700'
                  }`}
                >
                  {isGenerating ? (
                    <>
                      <Loader2 size={12} className="animate-spin" />
                      Generating… (30-60s)
                    </>
                  ) : completedAt ? (
                    'Regenerate'
                  ) : (
                    'Generate Feedback'
                  )}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Bottom action */}
      <div className="pt-2 border-t border-gray-100">
        <button
          onClick={() => {
            // Write last completed (or first) student ID as handoff context
            const lastCompleted = [...completedIds.keys()].pop();
            const handoffId = lastCompleted ?? students?.[0]?.student_id ?? null;
            if (handoffId) {
              useSessionStore.getState().setSelectedStudentId(handoffId);
            }
            onNavigateToReview();
          }}
          className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
        >
          Open Full Review
          <ExternalLink size={13} />
        </button>
      </div>
    </div>
  );
}
