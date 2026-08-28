import { CriticalMoment } from '@/types';
import { Camera, FileText, Activity } from 'lucide-react';

interface Props {
  moment: CriticalMoment | null;
}

export const EvidencePanel = ({ moment }: Props) => {
  if (!moment) {
    return null;
  }

  const getSeverityColor = (severity: string) => {
    return severity === 'critical' ? 'text-red-600' : 'text-amber-600';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="space-y-3">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Moment #{moment.id}</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {moment.start_time_formatted} – {moment.end_time_formatted}
            </p>
          </div>
          <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
            moment.severity === 'critical'
              ? 'bg-red-50 text-red-700'
              : 'bg-amber-50 text-amber-700'
          }`}>
            {moment.severity.toUpperCase()}
          </span>
        </div>

        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span>Confidence: {(moment.confidence * 100).toFixed(0)}%</span>
          <span>·</span>
          <span>{moment.num_sources} source{moment.num_sources !== 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Clinical Significance */}
      <div className="bg-blue-50 border border-blue-100 rounded-lg p-4">
        <h3 className="text-xs font-semibold text-blue-900 mb-2">Clinical Significance</h3>
        <p className="text-sm text-blue-800 leading-relaxed">{moment.clinical_significance}</p>
      </div>

      {/* Evidence Sources - collapsible */}
      <div>
        <h3 className="text-sm font-semibold text-gray-900 mb-3">Evidence</h3>

        <div className="space-y-3">
          {Object.entries(moment.sources).map(([source, data]) => (
            <details
              key={source}
              className="group bg-gray-50 rounded-lg border border-gray-200 overflow-hidden"
              open={moment.num_sources <= 2}
            >
              <summary className="px-4 py-3 cursor-pointer hover:bg-gray-100 transition-colors flex items-center gap-2">
                {source.includes('video') && <Camera size={14} className="text-blue-600" />}
                {source.includes('transcript') && <FileText size={14} className="text-green-600" />}
                {source.includes('monitor') && <Activity size={14} className="text-red-600" />}
                <span className="text-sm font-medium text-gray-700">
                  {source.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                </span>
                <span className="ml-auto text-xs text-gray-400 group-open:hidden">
                  Show details
                </span>
              </summary>

              <div className="px-4 py-3 border-t border-gray-200 bg-white">
                {data.data && data.data.length > 0 ? (
                  <div className="space-y-3 text-sm">
                    {data.data.map((item: any, idx: number) => (
                      <div key={idx} className="space-y-1">
                        {item.description && (
                          <p className="text-gray-700">"{item.description}"</p>
                        )}
                        {item.text && (
                          <p className="text-gray-700">"{item.text}"</p>
                        )}
                        {item.urgency_score && (
                          <p className="text-xs text-gray-500">
                            Urgency score: {item.urgency_score.toFixed(2)}
                          </p>
                        )}
                        {item.anomalies && item.anomalies.length > 0 && (
                          <div className="text-xs text-red-600 space-y-0.5">
                            {item.anomalies.map((a: any, i: number) => (
                              <div key={i}>• {a.reason}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-gray-400">No detailed data available</p>
                )}
              </div>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
};
