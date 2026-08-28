import { MomentContext } from '@/types';
import { SlideShell } from './SlideShell';
import { Star, MessageSquare } from 'lucide-react';

interface Props {
  moment: MomentContext;
  index: number;
  total: number;
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

const TAG_COLORS: Record<string, string> = {
  closed_loop_present: 'bg-green-100 text-green-700',
  closed_loop_absent: 'bg-red-100 text-red-700',
  directive_given: 'bg-blue-100 text-blue-700',
  question_unanswered: 'bg-amber-100 text-amber-700',
  team_discussion: 'bg-green-100 text-green-700',
  monologue: 'bg-gray-100 text-gray-600',
  escalation_trigger: 'bg-red-100 text-red-700',
  role_confusion: 'bg-orange-100 text-orange-700',
};

export function MomentDeepDiveSlide({ moment, index, total, speakerRoles }: Props) {
  const allUtterances = moment.speech.chronological_utterances ?? [];
  const topQuotes = [...allUtterances]
    .sort((a, b) => b.text.length - a.text.length)
    .slice(0, 2);

  return (
    <SlideShell
      title={`Moment ${index + 1} / ${total}: ${formatCat(moment.category)}`}
      subtitle={`${formatTime(moment.timestamp)} — ${formatTime(moment.end_timestamp)} · ${moment.importance}`}
      accent={moment.importance === 'critical' ? 'border-red-500' : 'border-amber-500'}
    >
      <div className="grid grid-cols-2 gap-8 h-full">
        <div className="space-y-4">
          <div>
            <div className="flex items-center gap-1.5 mb-2">
              <Star size={13} className="text-amber-500 fill-amber-500" />
              <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">AI Observation</span>
            </div>
            <p className="text-sm text-gray-800 leading-relaxed">
              {moment.narrative ?? moment.original_text}
            </p>
          </div>

          {moment.tags && moment.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {moment.tags.map(tag => (
                <span
                  key={tag}
                  className={`text-xs px-2.5 py-1 rounded-full font-medium ${TAG_COLORS[tag] ?? 'bg-gray-100 text-gray-600'}`}
                >
                  {tag.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                </span>
              ))}
            </div>
          )}

          {moment.discussion_prompt && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl p-3">
              <p className="text-xs font-semibold text-amber-700 mb-1">Discussion Prompt</p>
              <p className="text-sm text-amber-900 italic">{moment.discussion_prompt}</p>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {topQuotes.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <MessageSquare size={13} className="text-blue-500" />
                <span className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Key Speech</span>
              </div>
              <div className="space-y-2">
                {topQuotes.map((utt, i) => {
                  const spkInfo = speakerRoles[utt.speaker];
                  return (
                    <div key={i} className="bg-gray-50 rounded-lg p-3">
                      <p className="text-[10px] font-semibold text-gray-500 mb-1">
                        {spkInfo?.label ?? utt.speaker} · {formatTime(utt.start)}
                      </p>
                      <p className="text-sm text-gray-800 italic">"{utt.text}"</p>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div>
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Team Dynamics</p>
            <div className="space-y-1.5 text-sm text-gray-700">
              <div className="flex items-center gap-2">
                <span className={`w-2 h-2 rounded-full ${moment.dynamics.closed_loop_detected ? 'bg-green-500' : 'bg-red-400'}`} />
                Closed-loop: {moment.dynamics.closed_loop_detected ? 'present' : 'absent'}
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-blue-400" />
                {moment.speech.active_speakers.length} active speaker{moment.speech.active_speakers.length !== 1 ? 's' : ''}
              </div>
              {moment.dynamics.silence_gaps.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-gray-400" />
                  {moment.dynamics.silence_gaps.length} silence gap{moment.dynamics.silence_gaps.length !== 1 ? 's' : ''}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </SlideShell>
  );
}
