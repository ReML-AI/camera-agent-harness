import { useState, useEffect } from 'react';
import { StudentSummary, FeedbackStatus } from '@/types';
import { User, Check, Clock, AlertCircle, RefreshCw, Search } from 'lucide-react';

interface Props {
  sessionId: string;
  selectedStudentId?: string;
  onSelectStudent: (student: StudentSummary) => void;
}

export const StudentSelector = ({ sessionId, selectedStudentId, onSelectStudent }: Props) => {
  const [students, setStudents] = useState<StudentSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<FeedbackStatus | 'all'>('all');

  useEffect(() => {
    fetchStudents();
  }, [sessionId]);

  const fetchStudents = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`/api/students/session/${sessionId}`);
      if (!response.ok) throw new Error('Failed to fetch students');
      const data = await response.json();
      setStudents(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const getStatusIcon = (status: FeedbackStatus) => {
    switch (status) {
      case 'final':
        return <Check size={14} className="text-green-600" />;
      case 'doctor_reviewed':
        return <Clock size={14} className="text-amber-600" />;
      case 'ai_generated':
        return <RefreshCw size={14} className="text-blue-600" />;
      default:
        return <AlertCircle size={14} className="text-gray-400" />;
    }
  };

  const getStatusLabel = (status: FeedbackStatus): string => {
    const labels: Record<FeedbackStatus, string> = {
      draft: 'Draft',
      ai_generated: 'AI Generated',
      doctor_reviewed: 'Under Review',
      final: 'Finalized'
    };
    return labels[status] || status;
  };

  const getStatusColor = (status: FeedbackStatus): string => {
    const colors: Record<FeedbackStatus, string> = {
      draft: 'bg-gray-100 text-gray-700',
      ai_generated: 'bg-blue-100 text-blue-700',
      doctor_reviewed: 'bg-amber-100 text-amber-700',
      final: 'bg-green-100 text-green-700'
    };
    return colors[status] || colors.draft;
  };

  const filteredStudents = students.filter(student => {
    const matchesSearch = searchQuery === '' ||
      student.student_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      student.student_name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      student.role.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesStatus = filterStatus === 'all' || student.feedback_status === filterStatus;

    return matchesSearch && matchesStatus;
  });

  if (loading) {
    return (
      <div className="p-4 text-center">
        <RefreshCw size={20} className="animate-spin mx-auto text-gray-400" />
        <p className="text-sm text-gray-500 mt-2">Loading students...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-center">
        <AlertCircle size={20} className="mx-auto text-red-400" />
        <p className="text-sm text-red-500 mt-2">{error}</p>
        <button
          onClick={fetchStudents}
          className="mt-2 text-sm text-blue-600 hover:underline"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white rounded-lg shadow-sm border border-gray-200">
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <h3 className="font-semibold text-gray-900">Students</h3>
        <p className="text-sm text-gray-500">{students.length} students in session</p>
      </div>

      {/* Search */}
      <div className="p-3 border-b border-gray-100">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search students..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Status filter */}
      <div className="px-3 py-2 border-b border-gray-100 flex gap-1 overflow-x-auto">
        {(['all', 'draft', 'ai_generated', 'doctor_reviewed', 'final'] as const).map(status => (
          <button
            key={status}
            onClick={() => setFilterStatus(status)}
            className={`px-2.5 py-1 text-xs rounded-full whitespace-nowrap transition-colors ${
              filterStatus === status
                ? 'bg-gray-900 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {status === 'all' ? 'All' : getStatusLabel(status as FeedbackStatus)}
          </button>
        ))}
      </div>

      {/* Student list */}
      <div className="flex-1 overflow-y-auto">
        {filteredStudents.length === 0 ? (
          <div className="p-4 text-center text-gray-500 text-sm">
            No students match your filters
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {filteredStudents.map(student => (
              <div
                key={student.student_id}
                onClick={() => onSelectStudent(student)}
                className={`p-3 cursor-pointer transition-colors ${
                  selectedStudentId === student.student_id
                    ? 'bg-blue-50 border-l-2 border-blue-600'
                    : 'hover:bg-gray-50 border-l-2 border-transparent'
                }`}
              >
                <div className="flex items-start gap-3">
                  {/* Thumbnail or avatar */}
                  {student.thumbnail_url ? (
                    <img
                      src={student.thumbnail_url}
                      alt={student.student_name || student.student_id}
                      className="w-10 h-10 rounded-full object-cover"
                    />
                  ) : (
                    <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center">
                      <User size={16} className="text-gray-500" />
                    </div>
                  )}

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 truncate">
                        {student.student_name || student.student_id}
                      </span>
                      {getStatusIcon(student.feedback_status)}
                    </div>
                    <p className="text-xs text-gray-500 truncate">{student.role}</p>

                    {/* Stats */}
                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                      <span>{student.total_observations} observations</span>
                      <span>{student.evidence_count} evidence</span>
                    </div>
                  </div>

                  {/* Status badge */}
                  <span className={`text-xs px-2 py-0.5 rounded-full ${getStatusColor(student.feedback_status)}`}>
                    {getStatusLabel(student.feedback_status)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer with summary */}
      <div className="p-3 border-t border-gray-200 bg-gray-50">
        <div className="grid grid-cols-4 gap-2 text-center text-xs">
          <div>
            <div className="font-semibold text-gray-900">
              {students.filter(s => s.feedback_status === 'final').length}
            </div>
            <div className="text-gray-500">Final</div>
          </div>
          <div>
            <div className="font-semibold text-gray-900">
              {students.filter(s => s.feedback_status === 'doctor_reviewed').length}
            </div>
            <div className="text-gray-500">Review</div>
          </div>
          <div>
            <div className="font-semibold text-gray-900">
              {students.filter(s => s.feedback_status === 'ai_generated').length}
            </div>
            <div className="text-gray-500">AI</div>
          </div>
          <div>
            <div className="font-semibold text-gray-900">
              {students.filter(s => s.feedback_status === 'draft').length}
            </div>
            <div className="text-gray-500">Draft</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default StudentSelector;
