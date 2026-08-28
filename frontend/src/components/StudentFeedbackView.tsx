import { CriticalMoment } from '@/types';
import { Check, X, BookOpen, Clock } from 'lucide-react';

interface StudentFeedback {
  positive: string;
  negative: string;
  learningPoints: string;
}

interface Props {
  moment: CriticalMoment;
  feedback: StudentFeedback | null;
  studentName?: string;
}

export const StudentFeedbackView = ({ moment, feedback, studentName = 'Student' }: Props) => {
  if (!feedback) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-6 text-center">
        <p className="text-gray-500 text-sm">
          No feedback available for this moment yet.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-50 to-blue-100 border border-blue-200 rounded-lg p-4">
        <h3 className="text-lg font-semibold text-blue-900 mb-1">
          Feedback for {studentName}
        </h3>
        <p className="text-sm text-blue-700 flex items-center gap-2">
          <Clock size={14} />
          Moment at {moment.start_time_formatted} - {moment.end_time_formatted}
        </p>
      </div>

      {/* Positive Feedback */}
      {feedback.positive && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 bg-green-600 rounded-full flex items-center justify-center">
              <Check size={18} className="text-white" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-green-900 mb-2">
                What You Did Well
              </h4>
              <p className="text-sm text-green-800 leading-relaxed">
                {feedback.positive}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Areas for Improvement */}
      {feedback.negative && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 bg-amber-600 rounded-full flex items-center justify-center">
              <X size={18} className="text-white" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-amber-900 mb-2">
                Areas for Growth
              </h4>
              <p className="text-sm text-amber-800 leading-relaxed">
                {feedback.negative}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Learning Points */}
      {feedback.learningPoints && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center">
              <BookOpen size={18} className="text-white" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-semibold text-blue-900 mb-2">
                Key Takeaways
              </h4>
              <p className="text-sm text-blue-800 leading-relaxed">
                {feedback.learningPoints}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Action Items */}
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-gray-900 mb-3">
          Recommended Next Steps
        </h4>
        <ul className="space-y-2 text-sm text-gray-700">
          <li className="flex items-start gap-2">
            <span className="text-blue-600 font-bold">1.</span>
            <span>Review the video of this moment to identify what went well and what could improve</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-blue-600 font-bold">2.</span>
            <span>Discuss with your team how to apply these learnings in future scenarios</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="text-blue-600 font-bold">3.</span>
            <span>Practice the identified skills in your next simulation session</span>
          </li>
        </ul>
      </div>
    </div>
  );
};
