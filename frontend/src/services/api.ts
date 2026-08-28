import { CriticalMoment, TranscriptSegment, FeedbackItem, RubricScores, Interaction, InteractionAnalytics, MomentContextsResponse, DebriefPlan, VideoOverlayData, StudentSummary, ReportManifest } from '@/types';

const API_BASE = '/api';

export const api = {
  // Sessions & Moments
  async listSessions(): Promise<{ id: string; total_moments: number }[]> {
    const res = await fetch(`${API_BASE}/sessions/`);
    return res.json();
  },

  async getMoments(sessionId: string): Promise<{ moments: CriticalMoment[] }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/moments`);
    return res.json();
  },

  async getTranscript(sessionId: string): Promise<{ segments: TranscriptSegment[] }> {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/transcript`);
    return res.json();
  },

  // Feedback
  async saveFeedback(data: {
    session_id: string;
    moment_id: number;
    feedback_items: FeedbackItem[];
    rubric_scores: RubricScores;
    comments?: string;
    evaluator_id: string;
  }) {
    const res = await fetch(`${API_BASE}/feedback/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  // Interactions
  async logInteraction(interaction: Interaction) {
    const res = await fetch(`${API_BASE}/interactions/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(interaction),
    });
    return res.json();
  },

  // Video
  getVideoUrl(camera: string, sessionId: string): string {
    return `${API_BASE}/videos/${encodeURIComponent(sessionId)}/${encodeURIComponent(camera)}`;
  },

  // Reports & Slides
  async generateSlides(data: {
    session_id: string;
    moments: any[];
    evaluations: any[];
    student_name?: string;
    evaluator_name?: string;
  }) {
    const res = await fetch(`${API_BASE}/reports/slides`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return res.json();
  },

  async exportToPowerPoint(data: {
    session_id: string;
    slides: any[];
  }): Promise<Blob> {
    const res = await fetch(`${API_BASE}/reports/export-pptx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to export to PowerPoint');
    return res.blob();
  },

  async generateStudentSlides(data: {
    session_id: string;
    student_id: string;
  }): Promise<{ session_id: string; student_id: string; total_slides: number; slides: any[] }> {
    const res = await fetch(`${API_BASE}/reports/student-slides`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to generate student slides');
    return res.json();
  },

  async exportStudentToPowerPoint(data: {
    session_id: string;
    student_id: string;
  }): Promise<Blob> {
    const res = await fetch(`${API_BASE}/reports/student-pptx`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to export student presentation');
    return res.blob();
  },

  // Interaction Analytics
  async getInteractionAnalytics(sessionId: string): Promise<InteractionAnalytics> {
    const res = await fetch(`${API_BASE}/interactions-analytics/${sessionId}/analytics`);
    return res.json();
  },

  async getMomentContexts(sessionId: string): Promise<MomentContextsResponse> {
    const res = await fetch(`${API_BASE}/interactions-analytics/${sessionId}/moment-contexts`);
    if (!res.ok) throw new Error('Failed to load moment contexts');
    return res.json();
  },

  async getVideoOverlay(sessionId: string): Promise<VideoOverlayData> {
    const res = await fetch(`${API_BASE}/interactions-analytics/${sessionId}/video-overlay`);
    if (!res.ok) throw new Error('Failed to load video overlay data');
    return res.json();
  },

  async regenerateNarrative(sessionId: string, momentId: number): Promise<{ narrative: string; tags: string[]; discussion_prompt: string }> {
    const res = await fetch(`${API_BASE}/interactions-analytics/${sessionId}/regenerate-narrative`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ moment_id: momentId }),
    });
    if (!res.ok) throw new Error('Failed to regenerate narrative');
    return res.json();
  },

  // Report Assets
  async getReportManifest(sessionId: string): Promise<ReportManifest> {
    const res = await fetch(`${API_BASE}/report-assets/${sessionId}/manifest.json`);
    if (!res.ok) return { session_id: sessionId, speakers: {}, moments: {} };
    return res.json();
  },

  getReportAssetUrl(sessionId: string, assetType: 'speakers' | 'moments', filename: string): string {
    return `${API_BASE}/report-assets/${sessionId}/${assetType}/${filename}`;
  },

  // Debrief Plans
  async getDebriefPlan(sessionId: string): Promise<DebriefPlan> {
    const res = await fetch(`${API_BASE}/debrief-plans/${sessionId}`);
    return res.json();
  },

  async saveDebriefPlan(sessionId: string, plan: DebriefPlan): Promise<DebriefPlan> {
    const res = await fetch(`${API_BASE}/debrief-plans/${sessionId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(plan),
    });
    return res.json();
  },

  // Students
  async getStudents(sessionId: string): Promise<StudentSummary[]> {
    const res = await fetch(`${API_BASE}/students/session/${sessionId}`);
    if (!res.ok) throw new Error('Failed to load students');
    return res.json();
  },

  async generateFeedback(studentId: string, sessionId: string): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE}/students/${encodeURIComponent(studentId)}/generate?session_id=${sessionId}`, {
      method: 'POST',
    });
    if (!res.ok) throw new Error('Failed to generate feedback');
    return res.json();
  },

};
