import { useState } from 'react';
import { CriticalMoment } from '@/types';
import { FileDown, FileText, Loader } from 'lucide-react';

interface Props {
  sessionId: string;
  moments: CriticalMoment[];
  evaluations: Map<number, any>;
}

export const ReportGenerator = ({ sessionId, moments, evaluations }: Props) => {
  const [generating, setGenerating] = useState(false);
  const [reportContent, setReportContent] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);

    try {
      // Prepare evaluation data
      const evaluationsArray = moments.map((moment) => {
        const evaluation = evaluations.get(moment.id) || {};
        return {
          moment_relevant: evaluation.momentRelevant,
          edited_description: evaluation.editedDescription || moment.clinical_significance,
          student_feedback: evaluation.studentFeedback || {
            positive: '',
            negative: '',
            learningPoints: '',
          },
          rubric_scores: evaluation.rubricScores || {},
        };
      });

      const response = await fetch('/api/reports/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          moments: moments.map((m) => ({
            id: m.id,
            start_time_formatted: m.start_time_formatted,
            end_time_formatted: m.end_time_formatted,
            clinical_significance: m.clinical_significance,
            num_sources: m.num_sources,
            confidence: m.confidence,
          })),
          evaluations: evaluationsArray,
          student_name: 'Clinical Training Student',
          evaluator_name: 'Dr. Evaluator',
        }),
      });

      const data = await response.json();
      setReportContent(data.content);
      setShowPreview(true);
    } catch (error) {
      console.error('Failed to generate report:', error);
      alert('Failed to generate report. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownload = () => {
    if (!reportContent) return;

    const blob = new Blob([reportContent], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `debrief_report_${sessionId}_${Date.now()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <button
        onClick={handleGenerate}
        disabled={generating}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white font-semibold rounded-lg transition-colors shadow-sm"
      >
        {generating ? (
          <>
            <Loader size={18} className="animate-spin" />
            Generating Report...
          </>
        ) : (
          <>
            <FileText size={18} />
            Generate Debrief Report
          </>
        )}
      </button>

      {showPreview && reportContent && (
        <div className="border border-gray-200 rounded-lg bg-white overflow-hidden">
          <div className="bg-gray-50 border-b border-gray-200 px-4 py-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-gray-700">Report Preview</h3>
            <button
              onClick={handleDownload}
              className="flex items-center gap-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm rounded-md transition-colors"
            >
              <FileDown size={14} />
              Download Markdown
            </button>
          </div>
          <div className="p-4 max-h-96 overflow-y-auto">
            <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono leading-relaxed">
              {reportContent}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
