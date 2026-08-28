import { useState } from 'react';
import { EvidenceLink, EvidenceChain } from '@/types';
import { Camera, Mic, Activity, Check, X, Clock, ChevronDown, ChevronRight, ExternalLink } from 'lucide-react';

interface Props {
  evidenceChain: EvidenceChain;
  onValidateEvidence?: (evidenceId: string, validated: boolean) => void;
  onJumpToVideo?: (startTime: number, endTime: number, cameraId?: string) => void;
}

export const EvidenceChainView = ({ evidenceChain, onValidateEvidence, onJumpToVideo }: Props) => {
  const [expandedLinks, setExpandedLinks] = useState<Set<string>>(new Set());
  const [filterSource, setFilterSource] = useState<'all' | 'video' | 'audio' | 'vitals'>('all');

  const toggleExpand = (momentId: string) => {
    const newExpanded = new Set(expandedLinks);
    if (newExpanded.has(momentId)) {
      newExpanded.delete(momentId);
    } else {
      newExpanded.add(momentId);
    }
    setExpandedLinks(newExpanded);
  };

  const getSourceIcon = (source: string) => {
    switch (source) {
      case 'video':
        return <Camera size={14} className="text-blue-600" />;
      case 'audio':
        return <Mic size={14} className="text-green-600" />;
      case 'vitals':
        return <Activity size={14} className="text-red-600" />;
      default:
        return <Camera size={14} className="text-gray-400" />;
    }
  };

  const formatTimestamp = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const getConfidenceColor = (confidence: number): string => {
    if (confidence >= 0.8) return 'text-green-600 bg-green-50';
    if (confidence >= 0.6) return 'text-amber-600 bg-amber-50';
    return 'text-red-600 bg-red-50';
  };

  const filteredLinks = evidenceChain.evidence_links.filter(link => {
    if (filterSource === 'all') return true;
    return link.detection_source === filterSource;
  });

  const validatedCount = evidenceChain.evidence_links.filter(l => l.doctor_validated).length;
  const totalCount = evidenceChain.evidence_links.length;

  return (
    <div className="space-y-4">
      {/* Header with stats */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">Evidence Chain</h3>
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1">
            <Check size={14} className="text-green-600" />
            {validatedCount}/{totalCount} validated
          </span>
        </div>
      </div>

      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-2">
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-gray-900">{evidenceChain.total_moments_referenced}</div>
          <div className="text-xs text-gray-500">Moments</div>
        </div>
        <div className="bg-blue-50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-blue-700">{evidenceChain.total_video_evidence}</div>
          <div className="text-xs text-blue-600">Video</div>
        </div>
        <div className="bg-green-50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-green-700">{evidenceChain.total_audio_evidence}</div>
          <div className="text-xs text-green-600">Audio</div>
        </div>
        <div className="bg-red-50 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-red-700">{evidenceChain.total_vitals_evidence}</div>
          <div className="text-xs text-red-600">Vitals</div>
        </div>
      </div>

      {/* Filter buttons */}
      <div className="flex gap-2">
        {(['all', 'video', 'audio', 'vitals'] as const).map(source => (
          <button
            key={source}
            onClick={() => setFilterSource(source)}
            className={`px-3 py-1.5 text-sm rounded-full transition-colors ${
              filterSource === source
                ? 'bg-gray-900 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {source.charAt(0).toUpperCase() + source.slice(1)}
          </button>
        ))}
      </div>

      {/* Evidence links list */}
      <div className="space-y-2">
        {filteredLinks.map((link, index) => {
          const isExpanded = expandedLinks.has(link.moment_id);

          return (
            <div
              key={link.moment_id}
              className={`border rounded-lg overflow-hidden transition-all ${
                link.doctor_validated
                  ? 'border-green-200 bg-green-50/30'
                  : 'border-gray-200 bg-white'
              }`}
            >
              {/* Link header */}
              <div
                className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
                onClick={() => toggleExpand(link.moment_id)}
              >
                {isExpanded ? (
                  <ChevronDown size={16} className="text-gray-400" />
                ) : (
                  <ChevronRight size={16} className="text-gray-400" />
                )}

                {getSourceIcon(link.detection_source)}

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900 text-sm truncate">
                      {link.ai_interpretation}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-xs text-gray-500">
                    <Clock size={12} />
                    <span>
                      {formatTimestamp(link.timestamp_start)} - {formatTimestamp(link.timestamp_end)}
                    </span>
                  </div>
                </div>

                <div className={`px-2 py-0.5 rounded text-xs font-medium ${getConfidenceColor(link.confidence_score)}`}>
                  {(link.confidence_score * 100).toFixed(0)}%
                </div>

                {link.doctor_validated && (
                  <Check size={16} className="text-green-600" />
                )}
              </div>

              {/* Expanded content */}
              {isExpanded && (
                <div className="px-4 py-3 border-t border-gray-100 bg-gray-50/50 space-y-3">
                  {/* Raw data preview */}
                  {link.raw_data && (
                    <div className="text-xs">
                      <div className="font-medium text-gray-700 mb-1">Raw Detection Data</div>
                      <pre className="bg-gray-100 rounded p-2 overflow-x-auto text-gray-600">
                        {JSON.stringify(link.raw_data, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Validation notes */}
                  {link.validation_notes && (
                    <div className="text-xs">
                      <div className="font-medium text-gray-700 mb-1">Doctor Notes</div>
                      <p className="text-gray-600 italic">"{link.validation_notes}"</p>
                    </div>
                  )}

                  {/* Action buttons */}
                  <div className="flex items-center gap-2 pt-2">
                    {onJumpToVideo && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onJumpToVideo(link.timestamp_start, link.timestamp_end);
                        }}
                        className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-blue-700 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
                      >
                        <ExternalLink size={12} />
                        View in Video
                      </button>
                    )}

                    {onValidateEvidence && !link.doctor_validated && (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onValidateEvidence(link.moment_id, true);
                          }}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-green-700 bg-green-50 rounded-lg hover:bg-green-100 transition-colors"
                        >
                          <Check size={12} />
                          Validate
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onValidateEvidence(link.moment_id, false);
                          }}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50 rounded-lg hover:bg-red-100 transition-colors"
                        >
                          <X size={12} />
                          Reject
                        </button>
                      </>
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {filteredLinks.length === 0 && (
          <div className="text-center py-8 text-gray-500">
            No evidence links found for this filter
          </div>
        )}
      </div>
    </div>
  );
};

export default EvidenceChainView;
