import { useState } from 'react';
import {
  StudentFeedback,
  ClinicalSkill,
  NTSComponent,
  TimestampedObservation,
  SkillRating
} from '@/types';
import {
  User,
  ClipboardList,
  Activity,
  Users,
  Brain,
  Target,
  Link2,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Star,
  Clock,
  CheckCircle,
  AlertCircle
} from 'lucide-react';

interface Props {
  feedback: StudentFeedback;
  onObservationClick?: (observation: TimestampedObservation) => void;
  isEditable?: boolean;
}

const RatingStars = ({ rating }: { rating: SkillRating }) => {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((star) => (
        <Star
          key={star}
          size={14}
          className={star <= rating ? 'text-amber-400 fill-amber-400' : 'text-gray-300'}
        />
      ))}
    </div>
  );
};

const ObservationItem = ({
  observation,
  onClick
}: {
  observation: TimestampedObservation;
  onClick?: () => void;
}) => {
  const sourceColor = {
    video: 'bg-blue-100 text-blue-700',
    audio: 'bg-green-100 text-green-700',
    vitals: 'bg-red-100 text-red-700'
  };

  return (
    <div
      className={`flex items-start gap-2 p-2 rounded-lg bg-gray-50 ${
        onClick ? 'cursor-pointer hover:bg-gray-100' : ''
      }`}
      onClick={onClick}
    >
      <Clock size={14} className="text-gray-400 mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-700">{observation.description}</p>
        <div className="flex items-center gap-2 mt-1">
          <span className="text-xs text-gray-500">{observation.timestamp}</span>
          <span className={`text-xs px-1.5 py-0.5 rounded ${sourceColor[observation.evidence_source]}`}>
            {observation.evidence_source}
          </span>
          {observation.moment_id && (
            <Link2 size={10} className="text-gray-400" />
          )}
        </div>
      </div>
    </div>
  );
};

const ClinicalSkillCard = ({
  skill,
  onObservationClick
}: {
  skill: ClinicalSkill;
  onObservationClick?: (obs: TimestampedObservation) => void;
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <div className="flex-1">
          <div className="font-medium text-gray-900">{skill.skill_name}</div>
          {skill.protocol_reference && (
            <div className="text-xs text-gray-500">{skill.protocol_reference}</div>
          )}
        </div>
        <RatingStars rating={skill.performance_rating} />
      </div>

      {isExpanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-100">
          {skill.summary && (
            <p className="text-sm text-gray-600 mt-3">{skill.summary}</p>
          )}

          {skill.observations.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-gray-500 uppercase">Observations</div>
              {skill.observations.map((obs, idx) => (
                <ObservationItem
                  key={idx}
                  observation={obs}
                  onClick={onObservationClick ? () => onObservationClick(obs) : undefined}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const NTSComponentCard = ({
  component,
  onObservationClick
}: {
  component: NTSComponent;
  onObservationClick?: (obs: TimestampedObservation) => void;
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <div className="flex-1 font-medium text-gray-900">{component.skill_name}</div>
        <RatingStars rating={component.rating} />
      </div>

      {isExpanded && (
        <div className="px-4 pb-4 space-y-3 border-t border-gray-100">
          {component.strengths.length > 0 && (
            <div className="mt-3">
              <div className="text-xs font-medium text-green-700 mb-1">Strengths</div>
              <ul className="space-y-1">
                {component.strengths.map((s, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                    <CheckCircle size={14} className="text-green-500 mt-0.5 flex-shrink-0" />
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {component.areas_for_improvement.length > 0 && (
            <div>
              <div className="text-xs font-medium text-amber-700 mb-1">Areas for Improvement</div>
              <ul className="space-y-1">
                {component.areas_for_improvement.map((a, idx) => (
                  <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                    <AlertCircle size={14} className="text-amber-500 mt-0.5 flex-shrink-0" />
                    {a}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {component.observations.length > 0 && (
            <div>
              <div className="text-xs font-medium text-gray-500 uppercase mb-2">Observations</div>
              <div className="space-y-2">
                {component.observations.map((obs, idx) => (
                  <ObservationItem
                    key={idx}
                    observation={obs}
                    onClick={onObservationClick ? () => onObservationClick(obs) : undefined}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export const RichFeedbackPanel = ({ feedback, onObservationClick, isEditable = false }: Props) => {
  const [activeSection, setActiveSection] = useState<string>('scenario');

  const sections = [
    { id: 'scenario', label: 'Scenario', icon: ClipboardList },
    { id: 'clinical', label: 'Clinical Skills', icon: Activity },
    { id: 'abcde', label: 'ABCDE', icon: Activity },
    { id: 'nts', label: 'Non-Technical', icon: Users },
    { id: 'crm', label: 'CRM', icon: Brain },
    { id: 'outcomes', label: 'Outcomes', icon: Target },
    { id: 'evidence', label: 'Evidence', icon: Link2 },
    { id: 'references', label: 'References', icon: BookOpen },
  ];

  const getStatusBadge = (status: string) => {
    const styles = {
      draft: 'bg-gray-100 text-gray-700',
      ai_generated: 'bg-blue-100 text-blue-700',
      doctor_reviewed: 'bg-amber-100 text-amber-700',
      final: 'bg-green-100 text-green-700'
    };
    return styles[status as keyof typeof styles] || styles.draft;
  };

  return (
    <div className="h-full flex flex-col bg-white rounded-lg shadow-sm border border-gray-200">
      {/* Header */}
      <div className="p-4 border-b border-gray-200">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center">
            <User size={20} className="text-gray-600" />
          </div>
          <div className="flex-1">
            <h2 className="font-semibold text-gray-900">
              {feedback.student_name || feedback.student_id}
            </h2>
            <p className="text-sm text-gray-500">{feedback.student_role}</p>
          </div>
          <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${getStatusBadge(feedback.status)}`}>
            {feedback.status.replace('_', ' ')}
          </span>
        </div>
      </div>

      {/* Section tabs */}
      <div className="flex border-b border-gray-200 overflow-x-auto">
        {sections.map(section => {
          const Icon = section.icon;
          const isActive = activeSection === section.id;

          // Hide ABCDE if not present
          if (section.id === 'abcde' && !feedback.abcde_assessment) return null;

          return (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id)}
              className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium whitespace-nowrap border-b-2 transition-colors ${
                isActive
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              <Icon size={14} />
              {section.label}
            </button>
          );
        })}
      </div>

      {/* Section content */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* Section 1: Scenario Details */}
        {activeSection === 'scenario' && (
          <div className="space-y-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Patient Presentation</h3>
              <p className="text-sm text-gray-600">{feedback.scenario_details.patient_presentation}</p>
            </div>

            <div>
              <h3 className="text-sm font-semibold text-gray-900 mb-2">Clinical Context</h3>
              <p className="text-sm text-gray-600">{feedback.scenario_details.clinical_context}</p>
            </div>

            {feedback.scenario_details.scenario_type && (
              <div className="inline-block px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm">
                {feedback.scenario_details.scenario_type}
              </div>
            )}

            {feedback.scenario_details.learning_objectives.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-900 mb-2">Learning Objectives</h3>
                <ul className="space-y-1">
                  {feedback.scenario_details.learning_objectives.map((obj, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <span className="text-blue-600">•</span>
                      {obj}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Section 2: Clinical Skills */}
        {activeSection === 'clinical' && (
          <div className="space-y-3">
            {feedback.clinical_skills.map((skill, idx) => (
              <ClinicalSkillCard
                key={idx}
                skill={skill}
                onObservationClick={onObservationClick}
              />
            ))}
            {feedback.clinical_skills.length === 0 && (
              <p className="text-gray-500 text-center py-8">No clinical skills assessed</p>
            )}
          </div>
        )}

        {/* Section 3: ABCDE Assessment */}
        {activeSection === 'abcde' && feedback.abcde_assessment && (
          <div className="space-y-4">
            <div className={`p-3 rounded-lg ${
              feedback.abcde_assessment.overall_sequence_followed
                ? 'bg-green-50 border border-green-200'
                : 'bg-amber-50 border border-amber-200'
            }`}>
              <div className="flex items-center gap-2">
                {feedback.abcde_assessment.overall_sequence_followed ? (
                  <CheckCircle size={16} className="text-green-600" />
                ) : (
                  <AlertCircle size={16} className="text-amber-600" />
                )}
                <span className="text-sm font-medium">
                  {feedback.abcde_assessment.overall_sequence_followed
                    ? 'ABCDE sequence followed correctly'
                    : 'ABCDE sequence not fully followed'}
                </span>
              </div>
            </div>

            {['airway', 'breathing', 'circulation', 'disability', 'exposure'].map((component) => {
              const item = feedback.abcde_assessment![component as keyof typeof feedback.abcde_assessment];
              if (!item || typeof item !== 'object' || !('status' in item)) return null;

              return (
                <div key={component} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium text-gray-900 capitalize">
                      {component.charAt(0).toUpperCase()} - {component}
                    </h4>
                    {item.rating && <RatingStars rating={item.rating} />}
                  </div>
                  <p className="text-sm text-gray-600">{item.status}</p>
                  {item.actions_taken.length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs text-gray-500 mb-1">Actions taken:</div>
                      <ul className="text-sm text-gray-600 space-y-0.5">
                        {item.actions_taken.map((action, idx) => (
                          <li key={idx}>• {action}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Section 4: Non-Technical Skills */}
        {activeSection === 'nts' && (
          <div className="space-y-3">
            <NTSComponentCard
              component={feedback.non_technical_skills.communication}
              onObservationClick={onObservationClick}
            />
            <NTSComponentCard
              component={feedback.non_technical_skills.teamwork}
              onObservationClick={onObservationClick}
            />
            <NTSComponentCard
              component={feedback.non_technical_skills.leadership}
              onObservationClick={onObservationClick}
            />
            <NTSComponentCard
              component={feedback.non_technical_skills.situational_awareness}
              onObservationClick={onObservationClick}
            />
            <NTSComponentCard
              component={feedback.non_technical_skills.decision_making}
              onObservationClick={onObservationClick}
            />
          </div>
        )}

        {/* Section 5: CRM Reflection */}
        {activeSection === 'crm' && (
          <div className="space-y-4">
            {/* CRM Principle indicators */}
            <div className="grid grid-cols-2 gap-2">
              {[
                { key: 'knew_environment', label: 'Knew Environment' },
                { key: 'mobilized_resources', label: 'Mobilized Resources' },
                { key: 'prevented_fixation', label: 'Prevented Fixation' },
                { key: 'cross_checked', label: 'Cross-Checked' },
                { key: 'used_cognitive_aids', label: 'Used Cognitive Aids' },
                { key: 're_evaluated', label: 'Re-evaluated' },
                { key: 'set_priorities', label: 'Set Priorities' },
              ].map(({ key, label }) => {
                const value = feedback.crm_reflection[key as keyof typeof feedback.crm_reflection];
                if (value === undefined || value === null) return null;

                return (
                  <div
                    key={key}
                    className={`flex items-center gap-2 p-2 rounded-lg ${
                      value ? 'bg-green-50' : 'bg-red-50'
                    }`}
                  >
                    {value ? (
                      <CheckCircle size={14} className="text-green-600" />
                    ) : (
                      <AlertCircle size={14} className="text-red-600" />
                    )}
                    <span className={`text-sm ${value ? 'text-green-700' : 'text-red-700'}`}>
                      {label}
                    </span>
                  </div>
                );
              })}
            </div>

            {feedback.crm_reflection.strengths.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-green-700 mb-2">Strengths</h4>
                <ul className="space-y-1">
                  {feedback.crm_reflection.strengths.map((s, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <CheckCircle size={14} className="text-green-500 mt-0.5" />
                      {s}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.crm_reflection.areas_for_development.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-amber-700 mb-2">Areas for Development</h4>
                <ul className="space-y-1">
                  {feedback.crm_reflection.areas_for_development.map((a, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <AlertCircle size={14} className="text-amber-500 mt-0.5" />
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Section 6: Learning Outcomes */}
        {activeSection === 'outcomes' && (
          <div className="space-y-4">
            {feedback.learning_outcomes.debrief_summary && (
              <div className="bg-blue-50 border border-blue-100 rounded-lg p-4">
                <h4 className="text-sm font-semibold text-blue-900 mb-2">Summary</h4>
                <p className="text-sm text-blue-800">{feedback.learning_outcomes.debrief_summary}</p>
              </div>
            )}

            {feedback.learning_outcomes.key_achievements.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-green-700 mb-2">Key Achievements</h4>
                <ul className="space-y-1">
                  {feedback.learning_outcomes.key_achievements.map((a, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <CheckCircle size={14} className="text-green-500 mt-0.5" />
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.learning_outcomes.areas_for_improvement.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-amber-700 mb-2">Areas for Improvement</h4>
                <ul className="space-y-1">
                  {feedback.learning_outcomes.areas_for_improvement.map((a, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm text-gray-600">
                      <AlertCircle size={14} className="text-amber-500 mt-0.5" />
                      {a}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {feedback.learning_outcomes.action_plan.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-900 mb-2">Action Plan</h4>
                <ul className="space-y-2">
                  {feedback.learning_outcomes.action_plan.map((item, idx) => (
                    <li key={idx} className="flex items-start gap-2 text-sm">
                      <span className="flex-shrink-0 w-5 h-5 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-xs font-medium">
                        {idx + 1}
                      </span>
                      <span className="text-gray-600">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Section 7: Evidence Chain - use EvidenceChainView component */}
        {activeSection === 'evidence' && (
          <div className="text-sm text-gray-500">
            <p>Evidence chain visualization available in dedicated view.</p>
            <p className="mt-2">
              Total evidence links: {feedback.evidence_chain.evidence_links.length}
            </p>
          </div>
        )}

        {/* Section 8: References */}
        {activeSection === 'references' && (
          <div className="space-y-3">
            {feedback.references.map((ref, idx) => (
              <div key={idx} className="border border-gray-200 rounded-lg p-3">
                <p className="text-sm text-gray-700">{ref.citation}</p>
                {ref.url && (
                  <a
                    href={ref.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs text-blue-600 hover:underline mt-1 inline-block"
                  >
                    View source →
                  </a>
                )}
                {ref.protocol_name && (
                  <span className="text-xs text-gray-500 ml-2">({ref.protocol_name})</span>
                )}
              </div>
            ))}
            {feedback.references.length === 0 && (
              <p className="text-gray-500 text-center py-8">No references available</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default RichFeedbackPanel;
