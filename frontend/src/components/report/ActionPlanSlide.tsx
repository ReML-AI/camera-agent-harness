import { InteractionAnalytics, MomentContext } from '@/types';
import { SlideShell } from './SlideShell';

interface Props {
  moments: MomentContext[];
  analytics: InteractionAnalytics;
  speakerRoles: Record<string, { label: string; role: string }>;
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function formatCat(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

const TAG_LABELS: Record<string, string> = {
  closed_loop_absent: 'Incomplete closed-loop communication',
  monitor_focused: 'Over-reliance on monitor vs patient assessment',
  monologue: 'Single-speaker communication without team engagement',
  directive_given: 'Directives issued without confirmation',
  question_unanswered: 'Clinical questions left unaddressed',
  attention_away_from_patient: 'Insufficient patient-focused attention',
  information_gap: 'Gaps in information sharing',
  medication_verification: 'Medication verification concerns',
  escalation_trigger: 'Escalation response patterns',
  role_confusion: 'Role confusion within the team',
  task_delegation: 'Task delegation patterns',
  patient_assessment: 'Patient assessment approach',
  closed_loop_present: 'Effective closed-loop communication',
  attention_on_patient: 'Patient-focused attention',
};

export function ActionPlanSlide({ moments, analytics, speakerRoles: _speakerRoles }: Props) {
  const criticals = moments.filter(m => m.importance === 'critical');
  const sortedByTime = [...moments].sort((a, b) => a.timestamp - b.timestamp);
  const midpoint = sortedByTime.length > 0
    ? sortedByTime[Math.floor(sortedByTime.length / 2)].timestamp
    : 0;

  // --- Section 1: Key Discussion Questions ---
  // Pick 3 diverse discussion prompts
  const discussionQuestions: { moment: MomentContext; context: string }[] = [];

  // 1. First critical moment chronologically
  const firstCritical = sortedByTime.find(m => m.importance === 'critical' && m.discussion_prompt);
  if (firstCritical) {
    discussionQuestions.push({
      moment: firstCritical,
      context: `${formatCat(firstCritical.category)} at ${formatTime(firstCritical.timestamp)}`,
    });
  }

  // 2. Moment with question_unanswered or role_confusion
  const gapMoment = sortedByTime.find(
    m => m.discussion_prompt
      && m !== firstCritical
      && ((m.tags ?? []).includes('question_unanswered') || (m.tags ?? []).includes('role_confusion'))
  );
  if (gapMoment) {
    discussionQuestions.push({
      moment: gapMoment,
      context: `${formatCat(gapMoment.category)} at ${formatTime(gapMoment.timestamp)}`,
    });
  }

  // 3. Moment from second half
  const secondHalf = sortedByTime.find(
    m => m.discussion_prompt
      && m.timestamp >= midpoint
      && m !== firstCritical
      && m !== gapMoment
  );
  if (secondHalf) {
    discussionQuestions.push({
      moment: secondHalf,
      context: `${formatCat(secondHalf.category)} at ${formatTime(secondHalf.timestamp)}`,
    });
  }

  // Fill remaining slots if needed
  for (const m of sortedByTime) {
    if (discussionQuestions.length >= 3) break;
    if (m.discussion_prompt && !discussionQuestions.some(q => q.moment === m)) {
      discussionQuestions.push({
        moment: m,
        context: `${formatCat(m.category)} at ${formatTime(m.timestamp)}`,
      });
    }
  }

  // --- Section 2: Session Themes ---
  const tagCounts: Record<string, number> = {};
  for (const m of moments) {
    for (const tag of m.tags ?? []) {
      tagCounts[tag] = (tagCounts[tag] ?? 0) + 1;
    }
  }
  const topTags = Object.entries(tagCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);

  let themesText = '';
  if (topTags.length >= 3) {
    themesText = `(1) ${TAG_LABELS[topTags[0][0]] ?? topTags[0][0].replace(/_/g, ' ')} (${topTags[0][1]}x), (2) ${TAG_LABELS[topTags[1][0]] ?? topTags[1][0].replace(/_/g, ' ')} (${topTags[1][1]}x), (3) ${TAG_LABELS[topTags[2][0]] ?? topTags[2][0].replace(/_/g, ' ')} (${topTags[2][1]}x).`;
  } else if (topTags.length > 0) {
    themesText = topTags.map(([tag, count]) => `${TAG_LABELS[tag] ?? tag.replace(/_/g, ' ')} (${count}x)`).join(', ') + '.';
  }

  // --- Section 3: Suggested Debrief Flow ---
  const earliestCritical = sortedByTime.find(m => m.importance === 'critical');
  const richestMoment = [...moments]
    .filter(m => m !== earliestCritical)
    .sort((a, b) => (b.tags?.length ?? 0) - (a.tags?.length ?? 0))[0];
  const positiveMoment = moments.find(
    m => (m.tags ?? []).includes('closed_loop_present') || m.dynamics.closed_loop_detected
  );
  const latestCritical = [...criticals].sort((a, b) => b.timestamp - a.timestamp)[0];

  return (
    <SlideShell title="Discussion Guide" accent="border-gray-400">
      <div className="space-y-6">
        {/* Section 1: Key Discussion Questions */}
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Key Discussion Questions</p>
          <div className="space-y-3">
            {discussionQuestions.map((q, i) => (
              <div key={q.moment.moment_id} className="bg-white border border-gray-100 rounded-xl p-4">
                <div className="flex items-start gap-3">
                  <span className="w-6 h-6 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">
                    {i + 1}
                  </span>
                  <div className="flex-1">
                    <p className="text-sm text-gray-800 leading-relaxed">{q.moment.discussion_prompt}</p>
                    <p className="text-xs text-gray-400 mt-1">{q.context}</p>
                  </div>
                </div>
              </div>
            ))}
            {discussionQuestions.length === 0 && (
              <p className="text-sm text-gray-400 italic">No discussion prompts available for this session.</p>
            )}
          </div>
        </div>

        {/* Section 2: Session Themes */}
        {themesText && (
          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Session Themes</p>
            <p className="text-sm text-gray-700 leading-relaxed">{themesText}</p>
          </div>
        )}

        {/* Section 3: Suggested Debrief Flow */}
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Suggested Debrief Flow</p>
          <div className="grid grid-cols-3 gap-3">
            {/* Open with */}
            <div className="bg-blue-50 rounded-xl p-3">
              <p className="text-xs font-bold text-blue-700 uppercase mb-1">Open with</p>
              {earliestCritical ? (
                <p className="text-xs text-gray-700 leading-relaxed">
                  Begin by reviewing the initial {formatCat(earliestCritical.category).toLowerCase()} at {formatTime(earliestCritical.timestamp)}
                  {earliestCritical.narrative ? ` \u2014 ${earliestCritical.narrative.split('.')[0]}.` : '.'}
                </p>
              ) : (
                <p className="text-xs text-gray-400 italic">No critical moment to open with.</p>
              )}
            </div>

            {/* Explore */}
            <div className="bg-amber-50 rounded-xl p-3">
              <p className="text-xs font-bold text-amber-700 uppercase mb-1">Explore</p>
              {richestMoment ? (
                <p className="text-xs text-gray-700 leading-relaxed">
                  Dig into the {formatCat(richestMoment.category).toLowerCase()} at {formatTime(richestMoment.timestamp)}
                  {' '}\u2014 this moment had {richestMoment.tags?.length ?? 0} overlapping issues.
                </p>
              ) : (
                <p className="text-xs text-gray-400 italic">No multi-faceted moment identified.</p>
              )}
            </div>

            {/* Close with */}
            <div className="bg-green-50 rounded-xl p-3">
              <p className="text-xs font-bold text-green-700 uppercase mb-1">Close with</p>
              {positiveMoment ? (
                <p className="text-xs text-gray-700 leading-relaxed">
                  End on a positive: {positiveMoment.narrative
                    ? positiveMoment.narrative.split('.')[0] + '.'
                    : `effective communication at ${formatTime(positiveMoment.timestamp)}.`}
                </p>
              ) : latestCritical ? (
                <p className="text-xs text-gray-700 leading-relaxed">
                  Close by discussing the team's final actions at {formatTime(latestCritical.timestamp)}.
                </p>
              ) : (
                <p className="text-xs text-gray-400 italic">No closing moment identified.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </SlideShell>
  );
}
