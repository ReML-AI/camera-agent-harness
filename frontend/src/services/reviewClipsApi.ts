// frontend/src/services/reviewClipsApi.ts

export type ReviewClipPreset = "source" | "tracking" | "attention" | "comms" | "yolo";

export interface ReviewClipEntry {
  id: string;
  label: string;
  moment_id?: number;
  start_sec: number;
  duration_sec: number;
  cams: string[];
  presets: ReviewClipPreset[];
}

export interface ReviewClipsIndex {
  session_id: string;
  generated_at: string;
  clips: ReviewClipEntry[];
}

const API_BASE = "";

export async function fetchReviewClipsIndex(
  sessionId: string,
): Promise<ReviewClipsIndex> {
  const res = await fetch(
    `${API_BASE}/api/review-clips/${encodeURIComponent(sessionId)}`,
  );
  if (res.status === 404) {
    return { session_id: sessionId, generated_at: "", clips: [] };
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch review clips index: ${res.status}`);
  }
  return (await res.json()) as ReviewClipsIndex;
}

export function buildClipUrl(
  sessionId: string,
  clipId: string,
  cam: string,
  preset: ReviewClipPreset,
): string {
  return (
    `${API_BASE}/api/review-clips/` +
    `${encodeURIComponent(sessionId)}/` +
    `${encodeURIComponent(clipId)}/` +
    `${encodeURIComponent(cam)}/${encodeURIComponent(preset)}`
  );
}
