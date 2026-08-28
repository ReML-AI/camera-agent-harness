import { MomentContext, OverlayKeyframe, OverlayPersonMeta } from '@/types';
import { SlideShell } from './SlideShell';
import { EvidenceScene } from './EvidenceScene';
import { GazeBar } from './GazeBar';
import { CheckCircle, AlertCircle } from 'lucide-react';
import { ImageZoom } from './ImageZoom';

interface Props {
  moments: MomentContext[];
  momentKeyframes: Map<number, OverlayKeyframe>;
  personMeta: Record<string, OverlayPersonMeta>;
  momentFrameUrls?: Map<number, string>;
}

function formatCat(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

const TAG_LABELS: Record<string, string> = {
  closed_loop_absent: 'incomplete closed-loop communication',
  monitor_focused: 'over-reliance on monitor',
  monologue: 'single-speaker monologues',
  directive_given: 'unconfirmed directives',
  question_unanswered: 'unanswered clinical questions',
  attention_away_from_patient: 'insufficient patient attention',
  information_gap: 'information sharing gaps',
  role_confusion: 'role confusion',
};

export function LearningOutcomesSlide({ moments, momentKeyframes, personMeta, momentFrameUrls }: Props) {
  // Positive moments
  const positiveMoments = moments.filter(
    m => m.dynamics.closed_loop_detected || (m.tags ?? []).includes('closed_loop_present')
  );
  const patientFocused = moments.filter(m => (m.tags ?? []).includes('attention_on_patient'));
  const escalations = moments.filter(m => (m.tags ?? []).includes('escalation_trigger'));

  // Strengths paragraph — concise
  const strengthParts: string[] = [];
  if (positiveMoments.length > 0) {
    const cats = [...new Set(positiveMoments.map(m => formatCat(m.category)))].slice(0, 2).join(' and ');
    strengthParts.push(`Effective closed-loop communication in ${positiveMoments.length} instance${positiveMoments.length !== 1 ? 's' : ''} (${cats}).`);
  }
  if (patientFocused.length > 0) strengthParts.push(`Patient-focused attention noted ${patientFocused.length}x.`);
  if (escalations.length > 0) strengthParts.push(`Appropriate escalation initiated ${escalations.length}x.`);
  if (!strengthParts.length) strengthParts.push('No explicit positive markers detected.');

  const strengthExamples = positiveMoments.filter(m => m.narrative).slice(0, 2);

  // Development: top 3 tag themes among criticals
  const criticals = moments.filter(m => m.importance === 'critical');
  const tagCounts: Record<string, number> = {};
  for (const m of criticals) for (const tag of m.tags ?? []) tagCounts[tag] = (tagCounts[tag] ?? 0) + 1;
  const topThemes = Object.entries(tagCounts).sort((a, b) => b[1] - a[1]).slice(0, 3);

  const devText = topThemes.length > 0
    ? `Key gaps: ${topThemes.map(([tag]) => TAG_LABELS[tag] ?? tag.replace(/_/g, ' ')).join(', ')}.`
    : 'No specific patterns identified.';

  // Diverse improvement moments
  const improvementMoments: MomentContext[] = [];
  const targetTags = ['monologue', 'directive_given', 'question_unanswered', 'closed_loop_absent'];
  const usedTags = new Set<string>();
  for (const tag of targetTags) {
    if (improvementMoments.length >= 2) break;
    const found = criticals.find(m => (m.tags ?? []).includes(tag) && !usedTags.has(tag) && m.narrative);
    if (found) { improvementMoments.push(found); usedTags.add(tag); }
  }
  for (const m of criticals) {
    if (improvementMoments.length >= 2) break;
    if (!improvementMoments.includes(m) && m.narrative) improvementMoments.push(m);
  }

  return (
    <SlideShell title="Learning Outcomes" accent="border-green-500">
      <div className="grid grid-cols-2 gap-6">
        {/* Strengths */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <CheckCircle size={16} className="text-green-600" />
            <h3 className="text-sm font-semibold text-gray-900">Strengths Observed</h3>
          </div>
          <p className="text-xs text-gray-600 leading-relaxed mb-3">{strengthParts.join(' ')}</p>

          {strengthExamples.map(m => {
            const kf = momentKeyframes.get(m.moment_id);
            const frameUrl = momentFrameUrls?.get(m.moment_id);
            return (
              <div key={m.moment_id} className="border-l-3 border-green-400 pl-3 py-2 mb-2">
                <div className="flex gap-3">
                  {frameUrl ? (
                    <ImageZoom src={frameUrl} alt={`Moment ${m.moment_id}`} className="w-[160px] h-[90px] rounded-lg overflow-hidden flex-shrink-0">
                      <img src={frameUrl} alt={`Moment ${m.moment_id}`} className="w-full h-full object-cover" />
                    </ImageZoom>
                  ) : kf ? (
                    <EvidenceScene keyframe={kf} personMeta={personMeta} width={160} height={90} />
                  ) : null}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-700 leading-relaxed">
                      {truncateToSentences(m.narrative!, 2)}
                    </p>
                    {m.gaze.team_gaze && Object.keys(m.gaze.team_gaze).length > 0 && (
                      <div className="mt-1.5">
                        <GazeBar gazeDistribution={m.gaze.team_gaze} width={140} />
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Areas for Development */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <AlertCircle size={16} className="text-amber-600" />
            <h3 className="text-sm font-semibold text-gray-900">Areas for Development</h3>
          </div>
          <p className="text-xs text-gray-600 leading-relaxed mb-3">{devText}</p>

          {improvementMoments.map(m => {
            const kf = momentKeyframes.get(m.moment_id);
            const frameUrl = momentFrameUrls?.get(m.moment_id);
            return (
              <div key={m.moment_id} className="mb-3">
                <div className="flex gap-3">
                  {frameUrl ? (
                    <ImageZoom src={frameUrl} alt={`Moment ${m.moment_id}`} className="w-[160px] h-[90px] rounded-lg overflow-hidden flex-shrink-0">
                      <img src={frameUrl} alt={`Moment ${m.moment_id}`} className="w-full h-full object-cover" />
                    </ImageZoom>
                  ) : kf ? (
                    <EvidenceScene keyframe={kf} personMeta={personMeta} width={160} height={90} />
                  ) : null}
                  <div className="flex-1 min-w-0">
                    <p className="text-xs text-gray-700 leading-relaxed">
                      {truncateToSentences(m.narrative!, 2)}
                    </p>
                    {m.gaze.team_gaze && Object.keys(m.gaze.team_gaze).length > 0 && (
                      <div className="mt-1.5">
                        <GazeBar gazeDistribution={m.gaze.team_gaze} width={140} />
                      </div>
                    )}
                  </div>
                </div>
                {m.discussion_prompt && (
                  <div className="bg-amber-50 border-l-3 border-amber-400 rounded-r-lg px-3 py-1 mt-1.5">
                    <p className="text-[11px] text-amber-900">{m.discussion_prompt}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </SlideShell>
  );
}

function truncateToSentences(text: string, n: number): string {
  const sentences = text.match(/[^.!?]+[.!?]+/g);
  if (!sentences || sentences.length <= n) return text;
  return sentences.slice(0, n).join('').trim();
}
