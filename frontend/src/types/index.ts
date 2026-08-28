export interface CriticalMoment {
  id: number;
  start_time: number;
  end_time: number;
  duration: number;
  severity: 'critical' | 'warning';
  confidence: number;
  sources: {
    [key: string]: {
      detected: boolean;
      data: any[];
    };
  };
  num_sources: number;
  start_time_formatted: string;
  end_time_formatted: string;
  summary: string;
  clinical_significance: string;
}

export interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
  speaker?: string;
}

export interface Session {
  id: string;
  date: string;
  status: string;
  total_moments: number;
  videos: string[];
}

export interface FeedbackItem {
  text: string;
  type: 'positive' | 'negative' | 'learning_point';
  action?: 'accept' | 'edit' | 'reject';
  edited_text?: string;
}

export interface RubricScores {
  team_communication?: number;
  technical_skills?: number;
  response_time?: number;
  leadership?: number;
  overall?: number;
}

export interface Interaction {
  session_id: string;
  moment_id?: number;
  interaction_type: string;
  data: any;
}

// ============================================================================
// Rich Feedback Types (8-Section Professional Debrief)
// ============================================================================

export type FeedbackStatus = 'draft' | 'ai_generated' | 'doctor_reviewed' | 'final';
export type EvidenceSource = 'video' | 'audio' | 'vitals';
export type SkillRating = 1 | 2 | 3 | 4 | 5;

export interface TimestampedObservation {
  description: string;
  timestamp: string;
  timestamp_start?: number;
  timestamp_end?: number;
  evidence_source: EvidenceSource;
  moment_id?: string;
  confidence: number;
}

export interface EvidenceLink {
  moment_id: string;
  detection_source: EvidenceSource;
  timestamp_start: number;
  timestamp_end: number;
  raw_data?: any;
  ai_interpretation: string;
  confidence_score: number;
  doctor_validated: boolean;
  validation_notes?: string;
}

export interface EvidenceChain {
  evidence_links: EvidenceLink[];
  total_moments_referenced: number;
  total_video_evidence: number;
  total_audio_evidence: number;
  total_vitals_evidence: number;
}

export interface ScenarioDetails {
  patient_presentation: string;
  clinical_context: string;
  learning_objectives: string[];
  scenario_type?: string;
}

export interface ClinicalSkill {
  skill_name: string;
  performance_rating: SkillRating;
  observations: TimestampedObservation[];
  protocol_reference?: string;
  summary?: string;
}

export interface ABCDEItem {
  component: 'airway' | 'breathing' | 'circulation' | 'disability' | 'exposure';
  status: string;
  actions_taken: string[];
  observations: TimestampedObservation[];
  rating?: SkillRating;
  notes?: string;
}

export interface ABCDEAssessment {
  airway: ABCDEItem;
  breathing: ABCDEItem;
  circulation: ABCDEItem;
  disability: ABCDEItem;
  exposure: ABCDEItem;
  overall_sequence_followed: boolean;
  time_to_complete?: number;
}

export interface NTSComponent {
  skill_name: string;
  rating: SkillRating;
  observations: TimestampedObservation[];
  strengths: string[];
  areas_for_improvement: string[];
}

export interface NonTechnicalSkills {
  communication: NTSComponent;
  teamwork: NTSComponent;
  leadership: NTSComponent;
  situational_awareness: NTSComponent;
  decision_making: NTSComponent;
  overall_nts_rating?: SkillRating;
}

export interface CRMReflection {
  strengths: string[];
  areas_for_development: string[];
  specific_observations: TimestampedObservation[];
  knew_environment?: boolean;
  mobilized_resources?: boolean;
  prevented_fixation?: boolean;
  cross_checked?: boolean;
  used_cognitive_aids?: boolean;
  re_evaluated?: boolean;
  set_priorities?: boolean;
}

export interface LearningOutcomes {
  key_achievements: string[];
  areas_for_improvement: string[];
  recommended_focus: string[];
  action_plan: string[];
  debrief_summary?: string;
}

export interface Reference {
  citation: string;
  url?: string;
  protocol_name?: string;
}

export interface StudentFeedback {
  student_id: string;
  student_name?: string;
  student_role: string;
  session_id: string;
  status: FeedbackStatus;
  scenario_details: ScenarioDetails;
  clinical_skills: ClinicalSkill[];
  abcde_assessment?: ABCDEAssessment;
  non_technical_skills: NonTechnicalSkills;
  crm_reflection: CRMReflection;
  learning_outcomes: LearningOutcomes;
  evidence_chain: EvidenceChain;
  references: Reference[];
  generated_at?: string;
  ai_model_version?: string;
}

// ============================================================================
// Interaction Analytics Types
// ============================================================================

export interface SpeakerInfo {
  color: string;
  label: string;
  visual_track: number | null;
  total_talk_time: number;
  segment_count: number;
  talk_percentage: number;
}

export interface DiarizedSegment {
  start: number;
  end: number;
  speaker: string;
  text: string;
  color: string;
}

export interface InteractionInsight {
  type: 'long_silence' | 'no_attention' | 'dominance_shift' | 'rapid_exchange' | 'overlap';
  timestamp: number;
  duration?: number;
  description: string;
}

export interface InteractionAnalytics {
  speakers: Record<string, SpeakerInfo>;
  timeline_segments: DiarizedSegment[];
  turn_taking: {
    transitions: Record<string, number>;
    avg_gap_seconds: number;
    avg_overlap_seconds: number;
  };
  attention: {
    speaker_attention_received: Record<string, { avg_attention: number; samples: number }>;
    gaze_distribution: Record<string, { left: number; center: number; right: number }>;
  };
  insights: InteractionInsight[];
  gaze_attention?: Record<string, Record<string, number>>;
}

export interface GazePose {
  frame: number;
  timestamp: number;
  yaw: number;
  pitch: number;
  roll: number;
  bbox: [number, number, number, number];
  gaze_target: string;
  gaze_target_track: string | null;
  confidence: number;
}

export interface GazeTrackData {
  speaker: string | null;
  speaker_label: string | null;
  color: string | null;
  poses: GazePose[];
  summary: Record<string, number>;
}

export interface GazeTracks {
  metadata: {
    video: string;
    fps: number;
    resolution: [number, number];
    threshold_degrees: number;
    total_tracks: number;
  };
  layout: {
    patient_zone: { bbox: number[]; center: number[]; source: string };
    monitor_zone: { bbox: number[]; center: number[]; source: string; residual_samples?: number };
  };
  tracks: Record<string, GazeTrackData>;
}

export interface StudentSummary {
  student_id: string;
  student_name?: string;
  role: string;
  thumbnail_url?: string;
  feedback_status: FeedbackStatus;
  total_observations: number;
  evidence_count: number;
  last_updated?: string;
}

// Moment Context Types (cross-modal analysis)

export interface MomentSpeechData {
  talk_time_seconds: number;
  talk_time_pct: number;
  utterances: string[];
  spoke_first: boolean;
}

export interface ChronologicalUtterance {
  speaker: string;
  text: string;
  start: number;
}

export interface MomentSpeech {
  active_speakers: string[];
  per_speaker: Record<string, MomentSpeechData>;
  chronological_utterances?: ChronologicalUtterance[];
  silence_seconds: number;
  total_utterances: number;
  speaker_transitions: number;
}

export interface MomentGaze {
  per_speaker: Record<string, Record<string, number>>;
  team_gaze?: Record<string, number>;
  team_gaze_samples?: number;
  team_patient_attention_pct: number;
  data_quality: 'sufficient' | 'insufficient' | 'no_data';
}

export interface MomentVitals {
  spo2: { start: number; end: number; trend: string } | null;
  heart_rate: { start: number; end: number; trend: string } | null;
  blood_pressure: { start: number; end: number; trend: string } | null;
  readings_in_window: number;
}

export interface MomentDynamics {
  first_response_latency_seconds: number | null;
  closed_loop_detected: boolean;
  silence_gaps: { duration: number }[];
  overlapping_insights: { type: string; timestamp: number; description: string }[];
}

export interface MomentEvidenceSource {
  detected: boolean;
  data: Array<{
    // Transcript source
    text?: string;
    speaker?: string;
    categories?: string[];
    // Video source (CLIP)
    camera?: string;
    description?: string;
    urgency_score?: number;
    avg_score?: number;
    // Monitor OCR source
    vitals?: Record<string, number | null>;
    anomalies?: Array<{ vital: string; value: number; severity: string; reason: string }>;
  }>;
}

export interface MomentContext {
  moment_id: number;
  timestamp: number;
  end_timestamp: number;
  duration: number;
  category: string;
  importance: 'critical' | 'high';
  original_text: string;
  action_type: string;
  confidence?: number;
  num_sources?: number;
  evidence?: Record<string, MomentEvidenceSource>;
  categories?: Array<{category: string, action_type: string, importance: string}>;
  speech: MomentSpeech;
  gaze: MomentGaze;
  vitals: MomentVitals;
  dynamics: MomentDynamics;
  narrative?: string;
  tags?: string[];
  discussion_prompt?: string;
}

export interface MomentContextsResponse {
  metadata: {
    total_moments: number;
    pipeline?: string;
    filter?: string;
    generated_at: string;
  };
  speaker_roles: Record<string, { label: string; role: string }>;
  moments: MomentContext[];
}

// ============================================================================
// Report Assets Types
// ============================================================================

export interface ReportSpeakerAsset {
  file: string;
  person_id: string;
  frame: number;
  label: string;
  role: string;
  color: string;
}

export interface ReportMomentAsset {
  file: string;
  moment_id: number;
  frame: number;
  timestamp: number;
  category: string;
  importance: string;
}

export interface ReportManifest {
  session_id: string;
  speakers: Record<string, ReportSpeakerAsset>;
  moments: Record<string, ReportMomentAsset>;
}

// ============================================================================
// Debrief Plan Types
// ============================================================================

export interface DebriefPlan {
  session_id: string;
  starred_moment_ids: number[];
  moment_order: number[];
  notes: Record<string, string>;
  updated_at: string;
}

// ============================================================================
// Video Overlay Types
// ============================================================================

export interface OverlayBBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface OverlayHeadPose {
  yaw: number;
  pitch: number;
  roll: number;
}

export interface OverlayPerson {
  personId: string;
  trackId?: string;
  bbox: OverlayBBox;
  headPose: OverlayHeadPose | null;
  isSpeaking: boolean;
}

export interface OverlayKeyframe {
  frame: number;
  timestamp: number;
  persons: OverlayPerson[];
  isCriticalMoment: boolean;
  criticalMomentId: number | null;
}

export interface OverlayPersonMeta {
  role: string;
  label: string;
  color: string;
}

export interface OverlayMomentMeta {
  moment_id: number;
  start_frame: number;
  end_frame: number;
  start_time: number;
  end_time: number;
  category: string;
  importance: string;
}

export interface VideoOverlayData {
  videoId: string;
  fps: number;
  totalFrames: number;
  videoWidth: number;
  videoHeight: number;
  keyframeInterval: number;
  bboxFormat: string;
  persons: Record<string, OverlayPersonMeta>;
  moments: OverlayMomentMeta[];
  keyframes: OverlayKeyframe[];
}
