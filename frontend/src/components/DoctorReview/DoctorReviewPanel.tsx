import React, { useState, useEffect, useCallback } from 'react';
import {
  StudentFeedback,
  ClinicalSkill,
  NTSComponent,
  TimestampedObservation,
  ABCDEAssessment,
  ABCDEItem,
  CRMReflection,
  SkillRating,
  FeedbackStatus
} from '@/types';
import {
  Check,
  X,
  Edit2,
  Save,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  Star,
  Clock,
  AlertCircle,
  CheckCircle,
  Play,
  Plus,
  Trash2,
  MessageSquare,
  Send
} from 'lucide-react';

// ============================================================================
// Types
// ============================================================================

interface DoctorAction {
  action_type:
    | 'accept_feedback'
    | 'edit_feedback'
    | 'reject_feedback'
    | 'add_observation'
    | 'validate_evidence'
    | 'reject_evidence'
    | 'change_rating'
    | 'add_reference'
    | 'reorder_priority';
  timestamp: Date;
  section: string;
  field_path?: string;
  original_content: any;
  modified_content: any;
  time_spent_seconds: number;
}

interface ImplicitSignal {
  signal_type:
    | 'hover_duration'
    | 'video_rewatch'
    | 'section_skip'
    | 'immediate_accept'
    | 'deep_edit'
    | 'reference_lookup';
  section: string;
  duration_ms: number;
  context: any;
}

interface Props {
  feedback: StudentFeedback;
  sessionId: string;
  evaluatorId: string;
  onSave: (updatedFeedback: StudentFeedback, actions: DoctorAction[]) => Promise<void>;
  onJumpToVideo?: (startTime: number, endTime: number) => void;
}

// ============================================================================
// Rating Component
// ============================================================================

const EditableRating: React.FC<{
  rating: SkillRating;
  onChange: (rating: SkillRating) => void;
  disabled?: boolean;
}> = ({ rating, onChange, disabled }) => {
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((star) => (
        <button
          key={star}
          onClick={() => !disabled && onChange(star as SkillRating)}
          disabled={disabled}
          className={`p-0.5 transition-colors ${disabled ? 'cursor-default' : 'cursor-pointer hover:scale-110'}`}
        >
          <Star
            size={18}
            className={star <= rating ? 'text-amber-400 fill-amber-400' : 'text-gray-300'}
          />
        </button>
      ))}
    </div>
  );
};

// ============================================================================
// Section Components
// ============================================================================

interface SectionHeaderProps {
  title: string;
  isExpanded: boolean;
  onToggle: () => void;
  status: 'pending' | 'accepted' | 'edited' | 'rejected';
  onAccept?: () => void;
  onReject?: () => void;
}

const SectionHeader: React.FC<SectionHeaderProps> = ({
  title,
  isExpanded,
  onToggle,
  status,
  onAccept,
  onReject
}) => {
  const statusColors = {
    pending: 'bg-gray-100 text-gray-600',
    accepted: 'bg-green-100 text-green-700',
    edited: 'bg-blue-100 text-blue-700',
    rejected: 'bg-red-100 text-red-700'
  };

  const statusLabels = {
    pending: 'Pending Review',
    accepted: 'Accepted',
    edited: 'Edited',
    rejected: 'Rejected'
  };

  return (
    <div className="flex items-center justify-between p-4 bg-gray-50 border-b border-gray-200">
      <button
        onClick={onToggle}
        className="flex items-center gap-2 text-left flex-1"
      >
        {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
        <span className="font-semibold text-gray-900">{title}</span>
        <span className={`ml-2 px-2 py-0.5 text-xs rounded-full ${statusColors[status]}`}>
          {statusLabels[status]}
        </span>
      </button>

      <div className="flex items-center gap-2">
        {status === 'pending' && (
          <>
            <button
              onClick={onAccept}
              className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg transition-colors"
              title="Accept as-is"
            >
              <Check size={18} />
            </button>
            <button
              onClick={onReject}
              className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
              title="Reject section"
            >
              <X size={18} />
            </button>
          </>
        )}
      </div>
    </div>
  );
};

// ============================================================================
// Editable Text Component
// ============================================================================

interface EditableTextProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  multiline?: boolean;
  label?: string;
}

const EditableText: React.FC<EditableTextProps> = ({
  value,
  onChange,
  placeholder,
  multiline = false,
  label
}) => {
  const [isEditing, setIsEditing] = useState(false);
  const [localValue, setLocalValue] = useState(value);

  useEffect(() => {
    setLocalValue(value);
  }, [value]);

  const handleSave = () => {
    onChange(localValue);
    setIsEditing(false);
  };

  const handleCancel = () => {
    setLocalValue(value);
    setIsEditing(false);
  };

  if (isEditing) {
    return (
      <div className="space-y-2">
        {label && <label className="text-xs font-medium text-gray-500">{label}</label>}
        {multiline ? (
          <textarea
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            className="w-full p-2 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
            rows={3}
            autoFocus
          />
        ) : (
          <input
            type="text"
            value={localValue}
            onChange={(e) => setLocalValue(e.target.value)}
            className="w-full p-2 border border-blue-300 rounded-lg focus:ring-2 focus:ring-blue-500 text-sm"
            autoFocus
          />
        )}
        <div className="flex gap-2">
          <button
            onClick={handleSave}
            className="px-3 py-1 text-xs bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Save
          </button>
          <button
            onClick={handleCancel}
            className="px-3 py-1 text-xs bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="group">
      {label && <label className="text-xs font-medium text-gray-500">{label}</label>}
      <div
        onClick={() => setIsEditing(true)}
        className="p-2 rounded-lg cursor-pointer hover:bg-gray-50 border border-transparent hover:border-gray-200 transition-all"
      >
        <p className="text-sm text-gray-700">
          {value || <span className="text-gray-400 italic">{placeholder}</span>}
        </p>
        <Edit2 size={14} className="text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity mt-1" />
      </div>
    </div>
  );
};

// ============================================================================
// Inline Add Input Component
// ============================================================================

interface InlineAddInputProps {
  onAdd: (value: string) => void;
  onCancel: () => void;
  placeholder?: string;
  colorScheme?: 'green' | 'amber';
}

const InlineAddInput: React.FC<InlineAddInputProps> = ({
  onAdd,
  onCancel,
  placeholder = 'Type and press Enter...',
  colorScheme = 'green'
}) => {
  const [value, setValue] = useState('');

  const borderColor = colorScheme === 'green' ? 'border-green-300 focus:ring-green-500' : 'border-amber-300 focus:ring-amber-500';
  const confirmColor = colorScheme === 'green' ? 'bg-green-600 hover:bg-green-700' : 'bg-amber-600 hover:bg-amber-700';

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (trimmed) {
      onAdd(trimmed);
      setValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    } else if (e.key === 'Escape') {
      onCancel();
    }
  };

  return (
    <div className="flex items-center gap-2 mt-2">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        className={`flex-1 p-2 border ${borderColor} rounded-lg focus:ring-2 text-sm`}
        placeholder={placeholder}
        autoFocus
      />
      <button
        onClick={handleSubmit}
        disabled={!value.trim()}
        className={`p-2 ${confirmColor} text-white rounded-lg disabled:opacity-50 disabled:cursor-not-allowed`}
        title="Add"
      >
        <Check size={14} />
      </button>
      <button
        onClick={onCancel}
        className="p-2 bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300"
        title="Cancel"
      >
        <X size={14} />
      </button>
    </div>
  );
};

// ============================================================================
// Clinical Skill Editor
// ============================================================================

interface ClinicalSkillEditorProps {
  skill: ClinicalSkill;
  index: number;
  onChange: (index: number, skill: ClinicalSkill) => void;
  onJumpToVideo?: (obs: TimestampedObservation) => void;
}

const ClinicalSkillEditor: React.FC<ClinicalSkillEditorProps> = ({
  skill,
  index,
  onChange,
  onJumpToVideo
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  const handleRatingChange = (rating: SkillRating) => {
    onChange(index, { ...skill, performance_rating: rating });
  };

  const handleSummaryChange = (summary: string) => {
    onChange(index, { ...skill, summary });
  };

  const handleObservationEdit = (obsIndex: number, description: string) => {
    const newObservations = [...skill.observations];
    newObservations[obsIndex] = { ...newObservations[obsIndex], description };
    onChange(index, { ...skill, observations: newObservations });
  };

  const handleDeleteObservation = (obsIndex: number) => {
    const newObservations = skill.observations.filter((_, i) => i !== obsIndex);
    onChange(index, { ...skill, observations: newObservations });
  };

  const handleAddObservation = () => {
    const newObservation: TimestampedObservation = {
      description: '',
      timestamp: new Date().toISOString(),
      evidence_source: 'video',
      confidence: 1.0
    };
    onChange(index, { ...skill, observations: [...skill.observations, newObservation] });
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <div className="flex-1">
          <span className="font-medium text-gray-900">{skill.skill_name}</span>
          {skill.protocol_reference && (
            <span className="ml-2 text-xs text-gray-500">({skill.protocol_reference})</span>
          )}
        </div>
        <div onClick={(e) => e.stopPropagation()}>
          <EditableRating rating={skill.performance_rating} onChange={handleRatingChange} />
        </div>
      </div>

      {isExpanded && (
        <div className="p-4 border-t border-gray-100 space-y-4">
          <EditableText
            value={skill.summary || ''}
            onChange={handleSummaryChange}
            placeholder="Add summary..."
            multiline
            label="Summary"
          />

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-gray-500">Observations</label>
              <button
                onClick={handleAddObservation}
                className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                <Plus size={12} />
                Add Observation
              </button>
            </div>

            <div className="space-y-2">
              {skill.observations.map((obs, obsIdx) => (
                <div key={obsIdx} className="flex items-start gap-2 p-2 bg-gray-50 rounded-lg group">
                  <div className="flex-1">
                    <EditableText
                      value={obs.description}
                      onChange={(desc) => handleObservationEdit(obsIdx, desc)}
                      placeholder="Describe the observation..."
                    />
                    <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                      <Clock size={12} />
                      <span>{obs.timestamp}</span>
                      {obs.timestamp_start && onJumpToVideo && (
                        <button
                          onClick={() => onJumpToVideo(obs)}
                          className="text-blue-600 hover:underline flex items-center gap-1"
                        >
                          <Play size={10} />
                          View
                        </button>
                      )}
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteObservation(obsIdx)}
                    className="p-1 text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-600 transition-opacity"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// ABCDE Item Editor
// ============================================================================

interface ABCDEItemEditorProps {
  item: ABCDEItem;
  label: string;
  onChange: (item: ABCDEItem) => void;
}

const ABCDEItemEditor: React.FC<ABCDEItemEditorProps> = ({
  item,
  label,
  onChange
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [addingAction, setAddingAction] = useState(false);

  const statusColor = item.status.toLowerCase().includes('not assessed')
    ? 'text-red-600 bg-red-50'
    : 'text-green-600 bg-green-50';

  const handleRatingChange = (rating: SkillRating) => {
    onChange({ ...item, rating });
  };

  const handleActionEdit = (actionIndex: number, value: string) => {
    const newActions = [...item.actions_taken];
    newActions[actionIndex] = value;
    onChange({ ...item, actions_taken: newActions });
  };

  const handleDeleteAction = (actionIndex: number) => {
    onChange({ ...item, actions_taken: item.actions_taken.filter((_, i) => i !== actionIndex) });
  };

  const handleAddAction = (value: string) => {
    onChange({ ...item, actions_taken: [...item.actions_taken, value] });
    setAddingAction(false);
  };

  const handleAddObservation = () => {
    const newObservation: TimestampedObservation = {
      description: '',
      timestamp: new Date().toISOString(),
      evidence_source: 'video',
      confidence: 1.0
    };
    onChange({ ...item, observations: [...item.observations, newObservation] });
  };

  const handleObservationEdit = (obsIndex: number, description: string) => {
    const newObservations = [...item.observations];
    newObservations[obsIndex] = { ...newObservations[obsIndex], description };
    onChange({ ...item, observations: newObservations });
  };

  const handleDeleteObservation = (obsIndex: number) => {
    onChange({ ...item, observations: item.observations.filter((_, i) => i !== obsIndex) });
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <div className="flex-1">
          <span className="font-medium text-gray-900">{label}</span>
          <span className={`ml-2 px-2 py-0.5 text-xs rounded-full ${statusColor}`}>
            {item.status || 'Not Assessed'}
          </span>
        </div>
        <div onClick={(e) => e.stopPropagation()}>
          <EditableRating rating={item.rating || (1 as SkillRating)} onChange={handleRatingChange} />
        </div>
      </div>

      {isExpanded && (
        <div className="p-4 border-t border-gray-100 space-y-4">
          {/* Status */}
          <EditableText
            value={item.status}
            onChange={(value) => onChange({ ...item, status: value })}
            label="Status"
            placeholder="e.g., Assessed, Compromised..."
          />

          {/* Actions Taken */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-gray-500">Actions Taken</label>
              <button
                onClick={() => setAddingAction(true)}
                className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                <Plus size={12} />
                Add Action
              </button>
            </div>
            <div className="space-y-1">
              {item.actions_taken.map((action, idx) => (
                <div key={idx} className="flex items-center gap-2 p-2 bg-blue-50 rounded-lg group">
                  <div className="flex-1">
                    <EditableText
                      value={action}
                      onChange={(val) => handleActionEdit(idx, val)}
                    />
                  </div>
                  <button
                    onClick={() => handleDeleteAction(idx)}
                    className="p-1 text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-600 transition-opacity"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>
            {addingAction && (
              <InlineAddInput
                onAdd={handleAddAction}
                onCancel={() => setAddingAction(false)}
                placeholder="Describe the action taken..."
                colorScheme="green"
              />
            )}
          </div>

          {/* Observations */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-gray-500">Observations</label>
              <button
                onClick={handleAddObservation}
                className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                <Plus size={12} />
                Add Observation
              </button>
            </div>
            <div className="space-y-2">
              {item.observations.map((obs, obsIdx) => (
                <div key={obsIdx} className="flex items-start gap-2 p-2 bg-gray-50 rounded-lg group">
                  <div className="flex-1">
                    <EditableText
                      value={obs.description}
                      onChange={(desc) => handleObservationEdit(obsIdx, desc)}
                      placeholder="Describe the observation..."
                    />
                    <div className="flex items-center gap-2 mt-1 text-xs text-gray-500">
                      <Clock size={12} />
                      <span>{obs.timestamp}</span>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteObservation(obsIdx)}
                    className="p-1 text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-600 transition-opacity"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
              {item.observations.length === 0 && (
                <p className="text-xs text-gray-400 italic p-2">No observations recorded</p>
              )}
            </div>
          </div>

          {/* Notes */}
          <EditableText
            value={item.notes || ''}
            onChange={(value) => onChange({ ...item, notes: value })}
            label="Notes"
            placeholder="Additional notes..."
            multiline
          />
        </div>
      )}
    </div>
  );
};

// ============================================================================
// NTS Component Editor
// ============================================================================

interface NTSComponentEditorProps {
  name: string;
  component: NTSComponent;
  onChange: (component: NTSComponent) => void;
}

const NTSComponentEditor: React.FC<NTSComponentEditorProps> = ({
  name,
  component,
  onChange
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [addingStrength, setAddingStrength] = useState(false);
  const [addingImprovement, setAddingImprovement] = useState(false);

  const handleRatingChange = (rating: SkillRating) => {
    onChange({ ...component, rating });
  };

  const handleAddStrength = (value: string) => {
    onChange({ ...component, strengths: [...component.strengths, value] });
    setAddingStrength(false);
  };

  const handleAddImprovement = (value: string) => {
    onChange({
      ...component,
      areas_for_improvement: [...component.areas_for_improvement, value]
    });
    setAddingImprovement(false);
  };

  const handleRemoveStrength = (index: number) => {
    onChange({
      ...component,
      strengths: component.strengths.filter((_, i) => i !== index)
    });
  };

  const handleRemoveImprovement = (index: number) => {
    onChange({
      ...component,
      areas_for_improvement: component.areas_for_improvement.filter((_, i) => i !== index)
    });
  };

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden">
      <div
        className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span className="flex-1 font-medium text-gray-900">{name}</span>
        <div onClick={(e) => e.stopPropagation()}>
          <EditableRating rating={component.rating} onChange={handleRatingChange} />
        </div>
      </div>

      {isExpanded && (
        <div className="p-4 border-t border-gray-100 space-y-4">
          {/* Strengths */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-green-700">Strengths</label>
              <button
                onClick={() => setAddingStrength(true)}
                className="text-xs text-green-600 hover:text-green-700 flex items-center gap-1"
              >
                <Plus size={12} />
                Add
              </button>
            </div>
            <div className="space-y-1">
              {component.strengths.map((s, idx) => (
                <div key={idx} className="flex items-center gap-2 p-2 bg-green-50 rounded-lg group">
                  <CheckCircle size={14} className="text-green-600 flex-shrink-0" />
                  <span className="flex-1 text-sm text-green-800">{s}</span>
                  <button
                    onClick={() => handleRemoveStrength(idx)}
                    className="p-1 text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-600"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
            {addingStrength && (
              <InlineAddInput
                onAdd={handleAddStrength}
                onCancel={() => setAddingStrength(false)}
                placeholder="Enter new strength..."
                colorScheme="green"
              />
            )}
          </div>

          {/* Areas for Improvement */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-medium text-amber-700">Areas for Improvement</label>
              <button
                onClick={() => setAddingImprovement(true)}
                className="text-xs text-amber-600 hover:text-amber-700 flex items-center gap-1"
              >
                <Plus size={12} />
                Add
              </button>
            </div>
            <div className="space-y-1">
              {component.areas_for_improvement.map((a, idx) => (
                <div key={idx} className="flex items-center gap-2 p-2 bg-amber-50 rounded-lg group">
                  <AlertCircle size={14} className="text-amber-600 flex-shrink-0" />
                  <span className="flex-1 text-sm text-amber-800">{a}</span>
                  <button
                    onClick={() => handleRemoveImprovement(idx)}
                    className="p-1 text-red-400 opacity-0 group-hover:opacity-100 hover:text-red-600"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
            {addingImprovement && (
              <InlineAddInput
                onAdd={handleAddImprovement}
                onCancel={() => setAddingImprovement(false)}
                placeholder="Enter area for improvement..."
                colorScheme="amber"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
};

// ============================================================================
// CRM Principle Flags
// ============================================================================

const CRM_PRINCIPLE_LABELS: Record<string, string> = {
  knew_environment: 'Knew the Environment',
  mobilized_resources: 'Mobilized Resources',
  prevented_fixation: 'Prevented Fixation Errors',
  cross_checked: 'Cross-Checked / Double-Checked',
  used_cognitive_aids: 'Used Cognitive Aids',
  re_evaluated: 'Re-evaluated Regularly',
  set_priorities: 'Set Priorities Dynamically'
};

// ============================================================================
// Main Component
// ============================================================================

export const DoctorReviewPanel: React.FC<Props> = ({
  feedback,
  sessionId,
  evaluatorId,
  onSave,
  onJumpToVideo
}) => {
  const [editedFeedback, setEditedFeedback] = useState<StudentFeedback>(feedback);
  const [sectionStatuses, setSectionStatuses] = useState<Record<string, 'pending' | 'accepted' | 'edited' | 'rejected'>>({
    scenario: 'pending',
    clinical_skills: 'pending',
    abcde: 'pending',
    nts: 'pending',
    crm: 'pending',
    learning_outcomes: 'pending'
  });
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['scenario']));
  const [actions, setActions] = useState<DoctorAction[]>([]);
  const [sectionStartTimes, setSectionStartTimes] = useState<Record<string, number>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [doctorComment, setDoctorComment] = useState('');

  // Track section view time
  useEffect(() => {
    const newStartTimes: Record<string, number> = {};
    expandedSections.forEach(section => {
      if (!sectionStartTimes[section]) {
        newStartTimes[section] = Date.now();
      }
    });
    if (Object.keys(newStartTimes).length > 0) {
      setSectionStartTimes(prev => ({ ...prev, ...newStartTimes }));
    }
  }, [expandedSections]);

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections);
    if (newExpanded.has(section)) {
      newExpanded.delete(section);
      // Log time spent on section
      if (sectionStartTimes[section]) {
        const duration = Date.now() - sectionStartTimes[section];
        console.log(`Section ${section} viewed for ${duration}ms`);
      }
    } else {
      newExpanded.add(section);
    }
    setExpandedSections(newExpanded);
  };

  const logAction = useCallback((action: Omit<DoctorAction, 'timestamp'>) => {
    const fullAction: DoctorAction = {
      ...action,
      timestamp: new Date()
    };
    setActions(prev => [...prev, fullAction]);
  }, []);

  const acceptSection = (section: string) => {
    setSectionStatuses(prev => ({ ...prev, [section]: 'accepted' }));
    logAction({
      action_type: 'accept_feedback',
      section,
      original_content: null,
      modified_content: null,
      time_spent_seconds: sectionStartTimes[section]
        ? (Date.now() - sectionStartTimes[section]) / 1000
        : 0
    });
  };

  const rejectSection = (section: string) => {
    setSectionStatuses(prev => ({ ...prev, [section]: 'rejected' }));
    logAction({
      action_type: 'reject_feedback',
      section,
      original_content: null,
      modified_content: null,
      time_spent_seconds: sectionStartTimes[section]
        ? (Date.now() - sectionStartTimes[section]) / 1000
        : 0
    });
  };

  const handleClinicalSkillChange = (index: number, skill: ClinicalSkill) => {
    const newSkills = [...editedFeedback.clinical_skills];
    const original = newSkills[index];
    newSkills[index] = skill;

    setEditedFeedback(prev => ({ ...prev, clinical_skills: newSkills }));
    setSectionStatuses(prev => ({ ...prev, clinical_skills: 'edited' }));

    if (original.performance_rating !== skill.performance_rating) {
      logAction({
        action_type: 'change_rating',
        section: 'clinical_skills',
        field_path: `${index}.performance_rating`,
        original_content: original.performance_rating,
        modified_content: skill.performance_rating,
        time_spent_seconds: 0
      });
    } else {
      logAction({
        action_type: 'edit_feedback',
        section: 'clinical_skills',
        field_path: `${index}`,
        original_content: original,
        modified_content: skill,
        time_spent_seconds: 0
      });
    }
  };

  const handleABCDEItemChange = (key: string, item: ABCDEItem) => {
    if (!editedFeedback.abcde_assessment) return;
    const original = editedFeedback.abcde_assessment[key as keyof ABCDEAssessment];
    setEditedFeedback(prev => ({
      ...prev,
      abcde_assessment: {
        ...prev.abcde_assessment!,
        [key]: item
      }
    }));
    setSectionStatuses(prev => ({ ...prev, abcde: 'edited' }));

    logAction({
      action_type: 'edit_feedback',
      section: 'abcde',
      field_path: key,
      original_content: original,
      modified_content: item,
      time_spent_seconds: 0
    });
  };

  const handleABCDESequenceToggle = () => {
    if (!editedFeedback.abcde_assessment) return;
    const original = editedFeedback.abcde_assessment.overall_sequence_followed;
    setEditedFeedback(prev => ({
      ...prev,
      abcde_assessment: {
        ...prev.abcde_assessment!,
        overall_sequence_followed: !prev.abcde_assessment!.overall_sequence_followed
      }
    }));
    setSectionStatuses(prev => ({ ...prev, abcde: 'edited' }));

    logAction({
      action_type: 'edit_feedback',
      section: 'abcde',
      field_path: 'overall_sequence_followed',
      original_content: original,
      modified_content: !original,
      time_spent_seconds: 0
    });
  };

  const handleNTSChange = (key: string, component: NTSComponent) => {
    setEditedFeedback(prev => ({
      ...prev,
      non_technical_skills: {
        ...prev.non_technical_skills,
        [key]: component
      }
    }));
    setSectionStatuses(prev => ({ ...prev, nts: 'edited' }));

    logAction({
      action_type: 'edit_feedback',
      section: 'nts',
      field_path: key,
      original_content: feedback.non_technical_skills[key as keyof typeof feedback.non_technical_skills],
      modified_content: component,
      time_spent_seconds: 0
    });
  };

  const handleCRMFlagToggle = (flagKey: string) => {
    const crm = editedFeedback.crm_reflection;
    const original = crm[flagKey as keyof CRMReflection];
    setEditedFeedback(prev => ({
      ...prev,
      crm_reflection: {
        ...prev.crm_reflection,
        [flagKey]: !prev.crm_reflection[flagKey as keyof CRMReflection]
      }
    }));
    setSectionStatuses(prev => ({ ...prev, crm: 'edited' }));

    logAction({
      action_type: 'edit_feedback',
      section: 'crm',
      field_path: flagKey,
      original_content: original,
      modified_content: !original,
      time_spent_seconds: 0
    });
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const updatedFeedback: StudentFeedback = {
        ...editedFeedback,
        status: 'doctor_reviewed' as FeedbackStatus
      };
      await onSave(updatedFeedback, actions);
    } catch (error) {
      console.error('Failed to save:', error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleObservationClick = (obs: TimestampedObservation) => {
    if (onJumpToVideo && obs.timestamp_start) {
      onJumpToVideo(obs.timestamp_start, obs.timestamp_end || obs.timestamp_start + 5);
    }
  };

  const pendingCount = Object.values(sectionStatuses).filter(s => s === 'pending').length;
  const totalSections = Object.keys(sectionStatuses).length;
  const reviewedCount = totalSections - pendingCount;
  const acceptedCount = Object.values(sectionStatuses).filter(s => s === 'accepted').length;
  const editedCount = Object.values(sectionStatuses).filter(s => s === 'edited').length;

  return (
    <div className="h-full flex flex-col bg-white rounded-lg shadow-sm border border-gray-200">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-white">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Doctor Review</h2>
            <p className="text-sm text-gray-500">
              {editedFeedback.student_name || editedFeedback.student_id} - {editedFeedback.student_role}
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-sm">
              <span className="px-2 py-1 bg-gray-100 rounded text-gray-600">{pendingCount} pending</span>
              <span className="px-2 py-1 bg-green-100 rounded text-green-700">{acceptedCount} accepted</span>
              <span className="px-2 py-1 bg-blue-100 rounded text-blue-700">{editedCount} edited</span>
            </div>
          </div>
        </div>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Scenario Section */}
        <div className="border-b border-gray-200">
          <SectionHeader
            title="1. Scenario Details"
            isExpanded={expandedSections.has('scenario')}
            onToggle={() => toggleSection('scenario')}
            status={sectionStatuses.scenario}
            onAccept={() => acceptSection('scenario')}
            onReject={() => rejectSection('scenario')}
          />
          {expandedSections.has('scenario') && (
            <div className="p-4 space-y-4">
              <EditableText
                value={editedFeedback.scenario_details.patient_presentation}
                onChange={(value) => {
                  setEditedFeedback(prev => ({
                    ...prev,
                    scenario_details: { ...prev.scenario_details, patient_presentation: value }
                  }));
                  setSectionStatuses(prev => ({ ...prev, scenario: 'edited' }));
                }}
                label="Patient Presentation"
                multiline
              />
              <EditableText
                value={editedFeedback.scenario_details.clinical_context}
                onChange={(value) => {
                  setEditedFeedback(prev => ({
                    ...prev,
                    scenario_details: { ...prev.scenario_details, clinical_context: value }
                  }));
                  setSectionStatuses(prev => ({ ...prev, scenario: 'edited' }));
                }}
                label="Clinical Context"
                multiline
              />
            </div>
          )}
        </div>

        {/* Clinical Skills Section */}
        <div className="border-b border-gray-200">
          <SectionHeader
            title="2. Clinical Skills"
            isExpanded={expandedSections.has('clinical_skills')}
            onToggle={() => toggleSection('clinical_skills')}
            status={sectionStatuses.clinical_skills}
            onAccept={() => acceptSection('clinical_skills')}
            onReject={() => rejectSection('clinical_skills')}
          />
          {expandedSections.has('clinical_skills') && (
            <div className="p-4 space-y-3">
              {editedFeedback.clinical_skills.map((skill, idx) => (
                <ClinicalSkillEditor
                  key={idx}
                  skill={skill}
                  index={idx}
                  onChange={handleClinicalSkillChange}
                  onJumpToVideo={handleObservationClick}
                />
              ))}
            </div>
          )}
        </div>

        {/* ABCDE Assessment Section */}
        <div className="border-b border-gray-200">
          <SectionHeader
            title="3. ABCDE Assessment"
            isExpanded={expandedSections.has('abcde')}
            onToggle={() => toggleSection('abcde')}
            status={sectionStatuses.abcde}
            onAccept={() => acceptSection('abcde')}
            onReject={() => rejectSection('abcde')}
          />
          {expandedSections.has('abcde') && (
            <div className="p-4 space-y-3">
              {editedFeedback.abcde_assessment ? (
                <>
                  <ABCDEItemEditor
                    label="Airway"
                    item={editedFeedback.abcde_assessment.airway}
                    onChange={(item) => handleABCDEItemChange('airway', item)}
                  />
                  <ABCDEItemEditor
                    label="Breathing"
                    item={editedFeedback.abcde_assessment.breathing}
                    onChange={(item) => handleABCDEItemChange('breathing', item)}
                  />
                  <ABCDEItemEditor
                    label="Circulation"
                    item={editedFeedback.abcde_assessment.circulation}
                    onChange={(item) => handleABCDEItemChange('circulation', item)}
                  />
                  <ABCDEItemEditor
                    label="Disability"
                    item={editedFeedback.abcde_assessment.disability}
                    onChange={(item) => handleABCDEItemChange('disability', item)}
                  />
                  <ABCDEItemEditor
                    label="Exposure"
                    item={editedFeedback.abcde_assessment.exposure}
                    onChange={(item) => handleABCDEItemChange('exposure', item)}
                  />

                  {/* Overall Sequence */}
                  <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-700">Overall ABCDE Sequence Followed</span>
                    </div>
                    <button
                      onClick={handleABCDESequenceToggle}
                      className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                        editedFeedback.abcde_assessment.overall_sequence_followed
                          ? 'bg-green-100 text-green-700 hover:bg-green-200'
                          : 'bg-red-100 text-red-700 hover:bg-red-200'
                      }`}
                    >
                      {editedFeedback.abcde_assessment.overall_sequence_followed ? 'Yes' : 'No'}
                    </button>
                  </div>

                  {editedFeedback.abcde_assessment.time_to_complete && (
                    <div className="flex items-center gap-2 p-3 bg-gray-50 rounded-lg border border-gray-200">
                      <Clock size={14} className="text-gray-500" />
                      <span className="text-sm text-gray-700">
                        Time to complete: {editedFeedback.abcde_assessment.time_to_complete}s
                      </span>
                    </div>
                  )}
                </>
              ) : (
                <div className="text-center py-6">
                  <AlertCircle size={24} className="mx-auto text-gray-300 mb-2" />
                  <p className="text-sm text-gray-500">No ABCDE assessment data available for this student</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* NTS Section */}
        <div className="border-b border-gray-200">
          <SectionHeader
            title="4. Non-Technical Skills"
            isExpanded={expandedSections.has('nts')}
            onToggle={() => toggleSection('nts')}
            status={sectionStatuses.nts}
            onAccept={() => acceptSection('nts')}
            onReject={() => rejectSection('nts')}
          />
          {expandedSections.has('nts') && (
            <div className="p-4 space-y-3">
              <NTSComponentEditor
                name="Communication"
                component={editedFeedback.non_technical_skills.communication}
                onChange={(c) => handleNTSChange('communication', c)}
              />
              <NTSComponentEditor
                name="Teamwork"
                component={editedFeedback.non_technical_skills.teamwork}
                onChange={(c) => handleNTSChange('teamwork', c)}
              />
              <NTSComponentEditor
                name="Leadership"
                component={editedFeedback.non_technical_skills.leadership}
                onChange={(c) => handleNTSChange('leadership', c)}
              />
              <NTSComponentEditor
                name="Situational Awareness"
                component={editedFeedback.non_technical_skills.situational_awareness}
                onChange={(c) => handleNTSChange('situational_awareness', c)}
              />
              <NTSComponentEditor
                name="Decision Making"
                component={editedFeedback.non_technical_skills.decision_making}
                onChange={(c) => handleNTSChange('decision_making', c)}
              />
            </div>
          )}
        </div>

        {/* CRM Section */}
        <div className="border-b border-gray-200">
          <SectionHeader
            title="5. Crisis Resource Management"
            isExpanded={expandedSections.has('crm')}
            onToggle={() => toggleSection('crm')}
            status={sectionStatuses.crm}
            onAccept={() => acceptSection('crm')}
            onReject={() => rejectSection('crm')}
          />
          {expandedSections.has('crm') && (
            <div className="p-4 space-y-4">
              {/* CRM Principle Flags */}
              <div>
                <label className="text-xs font-medium text-gray-700 mb-2 block">CRM Principles</label>
                <div className="space-y-1">
                  {Object.entries(CRM_PRINCIPLE_LABELS).map(([key, label]) => {
                    const flagValue = editedFeedback.crm_reflection[key as keyof CRMReflection];
                    if (typeof flagValue !== 'boolean' && flagValue !== undefined) return null;
                    const isChecked = flagValue === true;
                    return (
                      <button
                        key={key}
                        onClick={() => handleCRMFlagToggle(key)}
                        className="flex items-center gap-3 w-full p-2 rounded-lg hover:bg-gray-50 transition-colors text-left"
                      >
                        <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 transition-colors ${
                          isChecked
                            ? 'bg-green-600 border-green-600'
                            : 'bg-white border-gray-300'
                        }`}>
                          {isChecked && <Check size={12} className="text-white" />}
                        </div>
                        <span className={`text-sm ${isChecked ? 'text-gray-900' : 'text-gray-500'}`}>
                          {label}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="text-xs font-medium text-green-700 mb-2 block">Strengths</label>
                {editedFeedback.crm_reflection.strengths.map((s, idx) => (
                  <div key={idx} className="flex items-center gap-2 p-2 bg-green-50 rounded mb-1">
                    <CheckCircle size={14} className="text-green-600" />
                    <span className="text-sm text-green-800">{s}</span>
                  </div>
                ))}
              </div>
              <div>
                <label className="text-xs font-medium text-amber-700 mb-2 block">Areas for Development</label>
                {editedFeedback.crm_reflection.areas_for_development.map((a, idx) => (
                  <div key={idx} className="flex items-center gap-2 p-2 bg-amber-50 rounded mb-1">
                    <AlertCircle size={14} className="text-amber-600" />
                    <span className="text-sm text-amber-800">{a}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Learning Outcomes Section */}
        <div className="border-b border-gray-200">
          <SectionHeader
            title="6. Learning Outcomes"
            isExpanded={expandedSections.has('learning_outcomes')}
            onToggle={() => toggleSection('learning_outcomes')}
            status={sectionStatuses.learning_outcomes}
            onAccept={() => acceptSection('learning_outcomes')}
            onReject={() => rejectSection('learning_outcomes')}
          />
          {expandedSections.has('learning_outcomes') && (
            <div className="p-4 space-y-4">
              <EditableText
                value={editedFeedback.learning_outcomes.debrief_summary || ''}
                onChange={(value) => {
                  setEditedFeedback(prev => ({
                    ...prev,
                    learning_outcomes: { ...prev.learning_outcomes, debrief_summary: value }
                  }));
                  setSectionStatuses(prev => ({ ...prev, learning_outcomes: 'edited' }));
                }}
                label="Debrief Summary"
                multiline
                placeholder="Brief summary of key debrief points..."
              />

              <div>
                <label className="text-xs font-medium text-gray-700 mb-2 block">Action Plan</label>
                {editedFeedback.learning_outcomes.action_plan.map((item, idx) => (
                  <div key={idx} className="flex items-center gap-2 p-2 bg-blue-50 rounded mb-1">
                    <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-xs flex items-center justify-center">
                      {idx + 1}
                    </span>
                    <span className="text-sm text-blue-800">{item}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Doctor Comment */}
      <div className="p-4 border-t border-gray-200 bg-gray-50">
        <label className="text-xs font-medium text-gray-700 mb-2 block flex items-center gap-1">
          <MessageSquare size={12} />
          Additional Comments
        </label>
        <textarea
          value={doctorComment}
          onChange={(e) => setDoctorComment(e.target.value)}
          className="w-full p-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"
          rows={2}
          placeholder="Add any additional notes or comments..."
        />
      </div>

      {/* Footer Actions */}
      <div className="p-4 border-t border-gray-200 bg-white flex items-center justify-between">
        <div className="text-sm text-gray-500">
          {actions.length} action(s) recorded
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setEditedFeedback(feedback);
              setSectionStatuses({
                scenario: 'pending',
                clinical_skills: 'pending',
                abcde: 'pending',
                nts: 'pending',
                crm: 'pending',
                learning_outcomes: 'pending'
              });
              setActions([]);
            }}
            className="px-4 py-2 text-gray-600 hover:text-gray-800 flex items-center gap-2"
          >
            <RotateCcw size={16} />
            Reset
          </button>

          <button
            onClick={handleSave}
            disabled={isSaving || reviewedCount === 0}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            {isSaving ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save size={16} />
                Save Review
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DoctorReviewPanel;
