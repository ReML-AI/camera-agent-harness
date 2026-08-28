import { useState } from 'react';
import { MomentContext } from '@/types';
import {
  Users, Clock, VolumeX, Camera, FileText, Activity,
  ChevronDown, ChevronRight,
} from 'lucide-react';

interface Props {
  moment: MomentContext;
  speakerRoles: Record<string, { label: string; role: string }>;
}

function formatTime(s: number): string {
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`;
}

export function MomentDetailPanel({ moment, speakerRoles }: Props) {
  const [showConvo, setShowConvo] = useState(false);

  const getLabel = (speaker: string) =>
    speakerRoles[speaker]?.label ?? speaker;

  // Chronological utterances
  const utterances: { speaker: string; text: string }[] =
    moment.speech.chronological_utterances
      ? moment.speech.chronological_utterances.map(u => ({ speaker: u.speaker, text: u.text }))
      : Object.entries(moment.speech.per_speaker).flatMap(([spk, d]) =>
          (d.utterances || []).map((t: string) => ({ speaker: spk, text: t }))
        );

  const { dynamics } = moment;
  const hasVitals =
    moment.vitals.readings_in_window > 0 &&
    (moment.vitals.heart_rate || moment.vitals.spo2 || moment.vitals.blood_pressure);
  const speakerEntries = Object.entries(moment.speech.per_speaker)
    .sort((a, b) => b[1].talk_time_pct - a[1].talk_time_pct);

  return (
    <div className="space-y-4 text-xs">

      {/* ── Time ── */}
      <div className="flex items-center gap-2 text-gray-400">
        <span>{formatTime(moment.timestamp)} – {formatTime(moment.end_timestamp)}</span>
        <span>·</span>
        <span>{moment.duration.toFixed(1)}s</span>
        {dynamics?.silence_gaps?.some(g => g.duration > 3) && (
          <>
            <span>·</span>
            <span className="text-amber-600 flex items-center gap-0.5">
              <VolumeX size={11} />
              {Math.max(...(dynamics.silence_gaps?.map(g => g.duration) ?? [0])).toFixed(1)}s silence
            </span>
          </>
        )}
        {dynamics?.first_response_latency_seconds != null && dynamics.first_response_latency_seconds > 0 && (
          <>
            <span>·</span>
            <span className="text-blue-500 flex items-center gap-0.5">
              <Clock size={11} />{dynamics.first_response_latency_seconds.toFixed(1)}s latency
            </span>
          </>
        )}
      </div>

      {/* ── Evidence sources ── */}
      {moment.evidence && Object.keys(moment.evidence).length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 mb-2">
            <span className="font-semibold text-gray-700 uppercase tracking-wide text-[10px]">Evidence</span>
            <span className="text-gray-400">
              {moment.num_sources} source{(moment.num_sources ?? 0) !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="space-y-2">
            {Object.entries(moment.evidence).map(([source, srcData]) => {
              if (!srcData.detected) return null;
              const isVideo = source.startsWith('video_');
              const isTranscript = source === 'transcript';
              const isMonitor = source === 'monitor_ocr';
              const icon = isVideo ? <Camera size={11} className="text-blue-500" />
                : isTranscript ? <FileText size={11} className="text-green-500" />
                : isMonitor ? <Activity size={11} className="text-red-500" />
                : null;
              const label = source.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

              return (
                <div key={source} className="bg-gray-50 rounded-lg px-3 py-2 space-y-1">
                  <div className="flex items-center gap-1.5 font-medium text-gray-700">
                    {icon}
                    <span>{label}</span>
                  </div>
                  {srcData.data.map((item, idx) => (
                    <div key={idx} className="text-gray-500 pl-4">
                      {item.description && (
                        <p>&ldquo;{item.description}&rdquo;
                          {item.urgency_score != null && (
                            <span className="text-gray-400 ml-1">
                              (score: {item.urgency_score.toFixed(2)})
                            </span>
                          )}
                        </p>
                      )}
                      {item.text && (
                        <p className="italic">&ldquo;{item.text.slice(0, 150)}{(item.text.length ?? 0) > 150 ? '…' : ''}&rdquo;</p>
                      )}
                      {item.anomalies && item.anomalies.map((a, i) => (
                        <p key={i} className="text-red-600 font-medium">
                          {a.reason}
                        </p>
                      ))}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Speech: talk-time bars ── */}
      <div>
        <div className="flex items-center gap-1.5 mb-2">
          <span className="font-semibold text-gray-700 uppercase tracking-wide text-[10px]">Talk time</span>
          <span className="text-gray-400">
            {moment.speech.total_utterances} utt · {moment.speech.silence_seconds.toFixed(1)}s silence
          </span>
        </div>
        <div className="space-y-1.5">
          {speakerEntries.map(([spk, data]) => {
            const color = speakerRoles[spk] ? undefined : '#6B7280';
            return (
              <div key={spk} className="flex items-center gap-2">
                <span className="text-gray-600 w-28 truncate shrink-0">{getLabel(spk)}</span>
                <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{
                      width: `${Math.min(data.talk_time_pct, 100)}%`,
                      backgroundColor: color ?? '#3B82F6',
                    }}
                  />
                </div>
                <span className="text-gray-400 w-8 text-right tabular-nums">{Math.round(data.talk_time_pct)}%</span>
              </div>
            );
          })}
        </div>

        {/* Conversation toggle */}
        {utterances.length > 0 && (
          <button
            className="flex items-center gap-1 mt-2 text-blue-500 hover:text-blue-700"
            onClick={() => setShowConvo(v => !v)}
          >
            {showConvo ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
            {showConvo ? 'Hide' : 'View'} conversation ({utterances.length})
          </button>
        )}
        {showConvo && (
          <div className="mt-2 space-y-1 pl-3 border-l-2 border-blue-100 max-h-36 overflow-y-auto">
            {utterances.map((u, i) => (
              <p key={i} className="text-gray-600 leading-snug">
                <span className="font-medium text-gray-800">{getLabel(u.speaker)}:</span>{' '}
                <span className="italic">&ldquo;{u.text.slice(0, 180)}{u.text.length > 180 ? '…' : ''}&rdquo;</span>
              </p>
            ))}
          </div>
        )}
      </div>

      {/* ── Vitals (only if non-null readings) ── */}
      {hasVitals && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Users size={11} className="text-gray-400" />
            <span className="font-semibold text-gray-700 uppercase tracking-wide text-[10px]">Vitals</span>
          </div>
          <div className="flex gap-4 flex-wrap">
            {moment.vitals.heart_rate && (
              <span className="text-gray-700">HR <b>{moment.vitals.heart_rate.start}→{moment.vitals.heart_rate.end}</b> bpm</span>
            )}
            {moment.vitals.spo2 && (
              <span className={moment.vitals.spo2.end < 94 ? 'text-red-700 font-medium' : 'text-gray-700'}>
                SpO2 <b>{moment.vitals.spo2.start}→{moment.vitals.spo2.end}%</b>
              </span>
            )}
            {moment.vitals.blood_pressure && (
              <span className="text-gray-700">BP <b>{moment.vitals.blood_pressure.start}→{moment.vitals.blood_pressure.end}</b></span>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
