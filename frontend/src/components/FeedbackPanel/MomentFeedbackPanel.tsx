import React, { useState, useEffect } from 'react';
import { CriticalMoment, FeedbackItem } from '@/types';
import { useFeedbackStore } from '@/stores/feedbackStore';
import { api } from '@/services/api';
import { Check, X, Edit2, ThumbsUp, ThumbsDown } from 'lucide-react';

interface Props {
  moment: CriticalMoment | null;
  sessionId: string;
  evaluatorId: string;
}

interface MomentEvaluation {
  momentRelevant: boolean | null;
  editedDescription: string;
  studentFeedback: {
    positive: string;
    negative: string;
    learningPoints: string;
  };
}

export const FeedbackPanel: React.FC<Props> = ({ moment, sessionId, evaluatorId }) => {
  const { feedbackItems, setFeedbackItems } = useFeedbackStore();

  const [evaluation, setEvaluation] = useState<MomentEvaluation>({
    momentRelevant: null,
    editedDescription: '',
    studentFeedback: {
      positive: '',
      negative: '',
      learningPoints: '',
    },
  });

  // Preserve original AI-generated values separately from educator amendments.
  const [originalAI, setOriginalAI] = useState({
    clinical_significance: '',
    positive: '',
    negative: '',
    learningPoints: '',
  });

  // Track ALL implicit signals per PLAN Section 3.2
  const [implicitSignals, setImplicitSignals] = useState({
    momentStartTime: 0,
    editStartTimes: {
      positive: 0,
      negative: 0,
      learningPoints: 0,
      description: 0,
    },
    totalEditDuration: 0,
    rewatchCount: 0,
    expandedEvidence: false,
  });

  useEffect(() => {
    if (moment) {
      // Track when moment is shown
      const startTime = Date.now();
      setImplicitSignals(prev => ({
        ...prev,
        momentStartTime: startTime,
        rewatchCount: 0,
        totalEditDuration: 0,
        expandedEvidence: false,
      }));

      // Initialize with AI-generated feedback
      const aiSuggestion = generateAIFeedback(moment);

      // Store original AI values
      setOriginalAI({
        clinical_significance: moment.clinical_significance,
        positive: aiSuggestion.positive,
        negative: aiSuggestion.negative,
        learningPoints: aiSuggestion.learningPoints,
      });

      setEvaluation({
        momentRelevant: null,
        editedDescription: moment.clinical_significance,
        studentFeedback: {
          positive: aiSuggestion.positive,
          negative: aiSuggestion.negative,
          learningPoints: aiSuggestion.learningPoints,
        },
      });

      // Record review navigation as a basic audit interaction. Preference learning is
      // explicitly outside the paper artifact.
      return () => {
        if (implicitSignals.momentStartTime > 0) {
          const watchDuration = (Date.now() - implicitSignals.momentStartTime) / 1000;

          api.logInteraction({
            session_id: sessionId,
            moment_id: moment.id,
            interaction_type: 'review_navigation',
            data: {
              watch_duration: watchDuration,
              skipped: evaluation.momentRelevant === false,
            },
          });
        }
      };
    }
  }, [moment, sessionId]);

  if (!moment) {
    return null;
  }

  const handleSave = async () => {
    await api.saveFeedback({
      session_id: sessionId,
      moment_id: moment.id,
      feedback_items: [
        { text: evaluation.studentFeedback.positive, type: 'positive' },
        { text: evaluation.studentFeedback.negative, type: 'negative' },
        { text: evaluation.studentFeedback.learningPoints, type: 'learning_point' },
      ],
      rubric_scores: {},
      comments: evaluation.editedDescription,
      evaluator_id: evaluatorId,
    });

    await api.logInteraction({
      session_id: sessionId,
      moment_id: moment.id,
      interaction_type: 'evaluation_complete',
      data: {
        moment_relevant: evaluation.momentRelevant,
        edited_description: evaluation.editedDescription !== moment.clinical_significance,
        original_clinical_significance: originalAI.clinical_significance,
      },
    });

    alert('Evaluation saved successfully!');
  };

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-gray-900">Doctor Evaluation</h2>

      {/* 1. Moment Relevance */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-3">
          Is this moment relevant for debrief?
        </h3>
        <div className="flex gap-3">
          <button
            onClick={() => setEvaluation({ ...evaluation, momentRelevant: true })}
            className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-all ${
              evaluation.momentRelevant === true
                ? 'bg-green-600 text-white shadow-md'
                : 'bg-white border-2 border-gray-300 text-gray-700 hover:border-green-500'
            }`}
          >
            <ThumbsUp size={18} />
            Yes, Relevant
          </button>
          <button
            onClick={() => setEvaluation({ ...evaluation, momentRelevant: false })}
            className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-lg font-medium transition-all ${
              evaluation.momentRelevant === false
                ? 'bg-red-600 text-white shadow-md'
                : 'bg-white border-2 border-gray-300 text-gray-700 hover:border-red-500'
            }`}
          >
            <ThumbsDown size={18} />
            No, Skip
          </button>
        </div>
      </div>

      {/* Only show rest if relevant */}
      {evaluation.momentRelevant !== false && (
        <>
          {/* 2. Edit Reason/Description */}
          <div>
            <label className="text-sm font-semibold text-gray-700 block mb-2">
              Clinical Significance / Reason for Selection
            </label>
            <textarea
              value={evaluation.editedDescription}
              onChange={(e) => setEvaluation({ ...evaluation, editedDescription: e.target.value })}
              onFocus={() => {
                setImplicitSignals(prev => ({
                  ...prev,
                  editStartTimes: { ...prev.editStartTimes, description: Date.now() }
                }));
              }}
              onBlur={() => {
                if (implicitSignals.editStartTimes.description > 0) {
                  const duration = (Date.now() - implicitSignals.editStartTimes.description) / 1000;
                  setImplicitSignals(prev => ({
                    ...prev,
                    totalEditDuration: prev.totalEditDuration + duration,
                    editStartTimes: { ...prev.editStartTimes, description: 0 }
                  }));
                }
              }}
              className="w-full bg-white border border-gray-300 rounded-lg p-3 text-sm text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent min-h-[80px]"
              placeholder="Explain why this moment is clinically significant..."
            />
          </div>

          {/* 3. Student Feedback */}
          <div className="space-y-4 border-t border-gray-200 pt-4">
            <h3 className="text-sm font-semibold text-gray-700">Feedback to Student</h3>

            {/* Positive Feedback */}
            <div>
              <label className="text-xs font-medium text-green-700 block mb-2 flex items-center gap-1">
                <Check size={14} />
                What went well?
              </label>
              <textarea
                value={evaluation.studentFeedback.positive}
                onChange={(e) =>
                  setEvaluation({
                    ...evaluation,
                    studentFeedback: { ...evaluation.studentFeedback, positive: e.target.value },
                  })
                }
                onFocus={() => {
                  setImplicitSignals(prev => ({
                    ...prev,
                    editStartTimes: { ...prev.editStartTimes, positive: Date.now() }
                  }));
                }}
                onBlur={() => {
                  if (implicitSignals.editStartTimes.positive > 0) {
                    const duration = (Date.now() - implicitSignals.editStartTimes.positive) / 1000;
                    setImplicitSignals(prev => ({
                      ...prev,
                      totalEditDuration: prev.totalEditDuration + duration,
                      editStartTimes: { ...prev.editStartTimes, positive: 0 }
                    }));
                  }
                }}
                className="w-full bg-white border border-gray-300 rounded-lg p-3 text-sm text-gray-900 focus:ring-2 focus:ring-green-500 focus:border-transparent"
                rows={3}
                placeholder="Strengths and positive observations..."
              />
            </div>

            {/* Areas for Improvement */}
            <div>
              <label className="text-xs font-medium text-red-700 block mb-2 flex items-center gap-1">
                <X size={14} />
                Areas for improvement?
              </label>
              <textarea
                value={evaluation.studentFeedback.negative}
                onChange={(e) =>
                  setEvaluation({
                    ...evaluation,
                    studentFeedback: { ...evaluation.studentFeedback, negative: e.target.value },
                  })
                }
                onFocus={() => {
                  setImplicitSignals(prev => ({
                    ...prev,
                    editStartTimes: { ...prev.editStartTimes, negative: Date.now() }
                  }));
                }}
                onBlur={() => {
                  if (implicitSignals.editStartTimes.negative > 0) {
                    const duration = (Date.now() - implicitSignals.editStartTimes.negative) / 1000;
                    setImplicitSignals(prev => ({
                      ...prev,
                      totalEditDuration: prev.totalEditDuration + duration,
                      editStartTimes: { ...prev.editStartTimes, negative: 0 }
                    }));
                  }
                }}
                className="w-full bg-white border border-gray-300 rounded-lg p-3 text-sm text-gray-900 focus:ring-2 focus:ring-red-500 focus:border-transparent"
                rows={3}
                placeholder="What could be improved..."
              />
            </div>

            {/* Learning Points */}
            <div>
              <label className="text-xs font-medium text-blue-700 block mb-2 flex items-center gap-1">
                <Edit2 size={14} />
                Key learning points
              </label>
              <textarea
                value={evaluation.studentFeedback.learningPoints}
                onChange={(e) =>
                  setEvaluation({
                    ...evaluation,
                    studentFeedback: { ...evaluation.studentFeedback, learningPoints: e.target.value },
                  })
                }
                onFocus={() => {
                  setImplicitSignals(prev => ({
                    ...prev,
                    editStartTimes: { ...prev.editStartTimes, learningPoints: Date.now() }
                  }));
                }}
                onBlur={() => {
                  if (implicitSignals.editStartTimes.learningPoints > 0) {
                    const duration = (Date.now() - implicitSignals.editStartTimes.learningPoints) / 1000;
                    setImplicitSignals(prev => ({
                      ...prev,
                      totalEditDuration: prev.totalEditDuration + duration,
                      editStartTimes: { ...prev.editStartTimes, learningPoints: 0 }
                    }));
                  }
                }}
                className="w-full bg-white border border-gray-300 rounded-lg p-3 text-sm text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                rows={3}
                placeholder="Key takeaways and action items..."
              />
            </div>
          </div>

          <button
            onClick={handleSave}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 rounded-lg transition-colors shadow-sm"
          >
            Save Evaluation
          </button>
        </>
      )}
    </div>
  );
};

// Helper to generate AI feedback suggestions
function generateAIFeedback(moment: CriticalMoment): {
  positive: string;
  negative: string;
  learningPoints: string;
} {
  let positive = '';
  let negative = '';
  let learningPoints = '';

  if (moment.num_sources >= 3) {
    positive = 'Strong multi-source evidence confirms team coordination during this critical event.';
  }

  if (moment.summary.toLowerCase().includes('cpr')) {
    positive += (positive ? ' ' : '') + 'Team initiated CPR compressions appropriately.';
    learningPoints = 'Review ACLS protocol timing to optimize compression-to-ventilation ratios.';
  }

  if (moment.summary.toLowerCase().includes('communication')) {
    positive += (positive ? ' ' : '') + 'Clear verbal communication observed between team members.';
  }

  if (moment.confidence < 0.5) {
    negative = 'Limited evidence available - consider reviewing the full context.';
  }

  // Default suggestions if empty
  if (!positive) positive = 'Review the team\'s response during this moment.';
  if (!negative) negative = 'Consider timing and coordination opportunities.';
  if (!learningPoints) learningPoints = 'Discuss as a team what could be optimized in similar scenarios.';

  return { positive, negative, learningPoints };
}

export default FeedbackPanel;
