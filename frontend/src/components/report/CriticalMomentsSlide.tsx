import { MomentContext, OverlayKeyframe, OverlayPersonMeta } from '@/types';
import { SlideShell } from './SlideShell';
import { EvidenceScene } from './EvidenceScene';
import { GazeBar } from './GazeBar';
import { ImageZoom } from './ImageZoom';

interface Props {
  moments: MomentContext[];
  momentKeyframes: Map<number, OverlayKeyframe>;
  personMeta: Record<string, OverlayPersonMeta>;
  momentFrameUrls?: Map<number, string>;
}

function formatTime(s: number): string {
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`;
}

function formatCat(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

export function CriticalMomentsSlide({ moments, momentKeyframes, personMeta, momentFrameUrls }: Props) {
  const criticals = moments.filter(m => m.importance === 'critical');

  // Top tags among criticals
  const tagCounts: Record<string, number> = {};
  for (const m of criticals) {
    for (const tag of m.tags ?? []) {
      tagCounts[tag] = (tagCounts[tag] ?? 0) + 1;
    }
  }
  const topTag = Object.entries(tagCounts).sort((a, b) => b[1] - a[1])[0];
  const topCategories = Object.entries(
    criticals.reduce<Record<string, number>>((acc, m) => {
      acc[m.category] = (acc[m.category] ?? 0) + 1;
      return acc;
    }, {})
  ).sort((a, b) => b[1] - a[1]).slice(0, 2).map(([c]) => formatCat(c));

  // Short overview — 1-2 sentences max
  let overview = `${criticals.length} critical moments, mainly ${topCategories.join(' and ') || 'various'}.`;
  if (topTag) {
    overview += ` Most common gap: ${topTag[0].replace(/_/g, ' ')} (${topTag[1]}x).`;
  }

  const displayCriticals = criticals.slice(0, 3);
  const remaining = criticals.length - 3;

  // Pick the strongest quote from each moment's chronological utterances
  function getKeyQuote(m: MomentContext): string | null {
    const utts = m.speech.chronological_utterances;
    if (!utts || utts.length === 0) return null;
    // Pick longest utterance as the most substantive
    const best = [...utts].sort((a, b) => b.text.length - a.text.length)[0];
    const text = best.text.length > 100 ? best.text.slice(0, 97) + '...' : best.text;
    return `"${text}"`;
  }

  return (
    <SlideShell
      title="Critical Moments"
      subtitle={`${criticals.length} flagged critical`}
      accent="border-red-500"
    >
      {criticals.length === 0 ? (
        <div className="flex items-center justify-center h-40">
          <p className="text-gray-400 text-sm">No critical moments in this session.</p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-gray-600">{overview}</p>

          {displayCriticals.map((m) => {
            const kf = momentKeyframes.get(m.moment_id);
            const frameUrl = momentFrameUrls?.get(m.moment_id);
            const hasGaze = m.gaze.team_gaze && Object.keys(m.gaze.team_gaze).length > 0;
            const quote = getKeyQuote(m);

            return (
              <div key={m.moment_id} className="bg-white border border-red-100 rounded-xl p-4">
                <div className="flex gap-4">
                  {/* Left: annotated video frame or SVG fallback */}
                  <div className="flex-shrink-0 space-y-1.5">
                    {frameUrl ? (
                      <ImageZoom src={frameUrl} alt={`Moment ${m.moment_id}`} className="w-[240px] h-[135px] rounded-lg overflow-hidden">
                        <img
                          src={frameUrl}
                          alt={`Moment ${m.moment_id}`}
                          className="w-full h-full object-cover shadow-sm"
                        />
                      </ImageZoom>
                    ) : kf ? (
                      <EvidenceScene keyframe={kf} personMeta={personMeta} width={240} height={135} />
                    ) : (
                      <div className="w-[240px] h-[135px] rounded-lg bg-gray-100 flex items-center justify-center">
                        <span className="text-[10px] text-gray-400">No frame data</span>
                      </div>
                    )}
                    {hasGaze && m.gaze.team_gaze && (
                      <GazeBar gazeDistribution={m.gaze.team_gaze} width={240} />
                    )}
                  </div>

                  {/* Right: narrative + evidence */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-[10px] font-bold text-white bg-red-500 uppercase tracking-wide px-2 py-0.5 rounded-full">
                        {formatCat(m.category)}
                      </span>
                      <span className="text-xs text-gray-400 font-mono">{formatTime(m.timestamp)}</span>
                    </div>

                    {/* Narrative — first 2 sentences */}
                    <p className="text-sm text-gray-700 leading-relaxed mb-2">
                      {truncateToSentences(m.narrative ?? m.original_text, 2)}
                    </p>

                    {/* Key quote from transcript */}
                    {quote && (
                      <p className="text-xs text-gray-500 italic border-l-2 border-gray-200 pl-2 mb-2">
                        {quote}
                      </p>
                    )}

                    {/* Discussion prompt */}
                    {m.discussion_prompt && (
                      <div className="bg-amber-50 border-l-3 border-amber-400 rounded-r-lg px-3 py-1.5">
                        <p className="text-xs text-amber-900">{m.discussion_prompt}</p>
                      </div>
                    )}

                    {/* Tags */}
                    {m.tags && m.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-2">
                        {m.tags.slice(0, 4).map(tag => (
                          <span key={tag} className="text-[9px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-500">
                            {tag.replace(/_/g, ' ')}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}

          {remaining > 0 && (
            <p className="text-xs text-gray-400 text-center">
              + {remaining} more critical moment{remaining !== 1 ? 's' : ''} (see deep-dives)
            </p>
          )}
        </div>
      )}
    </SlideShell>
  );
}

/** Truncate text to N sentences */
function truncateToSentences(text: string, n: number): string {
  const sentences = text.match(/[^.!?]+[.!?]+/g);
  if (!sentences || sentences.length <= n) return text;
  return sentences.slice(0, n).join('').trim();
}
