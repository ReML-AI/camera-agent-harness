import { InteractionAnalytics, ReportManifest } from '@/types';
import { api } from '@/services/api';
import { ImageZoom } from './ImageZoom';

interface Props {
  sessionId: string;
  analytics: InteractionAnalytics;
  manifest: ReportManifest;
  speakerRoles: Record<string, { label: string; role: string }>;
}

export function SpeakerIntroSlide({ sessionId, analytics, manifest, speakerRoles }: Props) {
  const speakers = Object.entries(analytics.speakers)
    .sort((a, b) => (b[1].talk_percentage ?? 0) - (a[1].talk_percentage ?? 0));

  return (
    <div className="h-full bg-white flex flex-col p-6 gap-4">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-gray-100 pb-3">
        <h2 className="text-2xl font-bold text-gray-900 tracking-tight">Participants</h2>
        <p className="text-gray-500 text-sm mt-0.5">Clinical simulation team — role overview</p>
      </div>

      {/* 4-column speaker cards */}
      <div className="flex-1 grid grid-cols-4 gap-4 min-h-0">
        {speakers.map(([speakerId, spk]) => {
          const asset = manifest.speakers[speakerId];
          const role = speakerRoles[speakerId]?.role ?? 'Unknown';

          const spotlightUrl = asset
            ? api.getReportAssetUrl(sessionId, 'speakers', `${speakerId}.jpg`)
            : null;
          const cropUrl = asset
            ? api.getReportAssetUrl(sessionId, 'speakers', `${speakerId}_crop.jpg`)
            : null;

          return (
            <div
              key={speakerId}
              className="flex flex-col rounded-xl overflow-hidden border border-gray-200 shadow-sm"
            >
              {/* ── Top: full spotlight scene (zoomable) ── */}
              <div className="relative bg-black" style={{ aspectRatio: '16/9' }}>
                {spotlightUrl ? (
                  <ImageZoom src={spotlightUrl} alt={`${spk.label} in scene`} className="w-full h-full">
                    <img
                      src={spotlightUrl}
                      alt={`${spk.label} in scene`}
                      className="w-full h-full object-cover"
                    />
                  </ImageZoom>
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-gray-900">
                    <span className="text-gray-600 text-sm">No frame</span>
                  </div>
                )}

                {/* Color accent bar at top */}
                <div
                  className="absolute top-0 left-0 right-0 h-1 pointer-events-none"
                  style={{ backgroundColor: spk.color }}
                />

                {/* Speaker label badge */}
                <div
                  className="absolute top-2 right-2 text-white text-xs font-bold px-2 py-0.5 rounded-full pointer-events-none"
                  style={{ backgroundColor: spk.color }}
                >
                  {spk.label}
                </div>
              </div>

              {/* ── Bottom: body crop + info ── */}
              <div className="flex flex-1 gap-3 p-3 bg-gray-50 border-t border-gray-100">
                {/* Body crop (zoomable) */}
                <div
                  className="flex-shrink-0 w-16 h-24 rounded-lg overflow-hidden ring-2"
                  style={{ '--tw-ring-color': spk.color } as React.CSSProperties}
                >
                  {cropUrl ? (
                    <ImageZoom src={cropUrl} alt={`${spk.label} portrait`} className="w-full h-full">
                      <img
                        src={cropUrl}
                        alt={`${spk.label} portrait`}
                        className="w-full h-full object-cover"
                      />
                    </ImageZoom>
                  ) : (
                    <div
                      className="w-full h-full flex items-center justify-center text-white text-lg font-bold"
                      style={{ backgroundColor: spk.color + '30' }}
                    >
                      {spk.label.charAt(spk.label.length - 1)}
                    </div>
                  )}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0 flex flex-col justify-between">
                  <div>
                    <p className="text-gray-900 font-semibold text-sm truncate">{spk.label}</p>
                    <p className="text-gray-500 text-xs leading-tight mt-0.5 line-clamp-2">{role}</p>
                  </div>

                  {/* Talk-time bar */}
                  <div>
                    <div className="flex justify-between text-[10px] mb-1">
                      <span className="text-gray-400">Talk time</span>
                      <span className="font-semibold" style={{ color: spk.color }}>
                        {Math.round(spk.talk_percentage ?? 0)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${Math.round(spk.talk_percentage ?? 0)}%`,
                          backgroundColor: spk.color,
                        }}
                      />
                    </div>
                    <p className="text-[10px] text-gray-400 mt-1">
                      {spk.segment_count} turn{spk.segment_count !== 1 ? 's' : ''}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
