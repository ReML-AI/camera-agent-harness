// frontend/src/components/ReviewPlayer.tsx
import { useEffect, useMemo, useState } from "react";
import {
  buildClipUrl,
  fetchReviewClipsIndex,
  ReviewClipEntry,
  ReviewClipPreset,
} from "../services/reviewClipsApi";

interface Props {
  sessionId: string;
}

const PRESET_ORDER: ReviewClipPreset[] = [
  "source",
  "yolo",
  "tracking",
  "attention",
  "comms",
];

const PRESET_LABEL: Record<ReviewClipPreset, string> = {
  source: "Source",
  yolo: "YOLO",
  tracking: "Tracking",
  attention: "Attention",
  comms: "Comms",
};

export default function ReviewPlayer({ sessionId }: Props) {
  const [clips, setClips] = useState<ReviewClipEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [clipId, setClipId] = useState<string>("");
  const [cam, setCam] = useState<string>("cam1");
  const [preset, setPreset] = useState<ReviewClipPreset>("tracking");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchReviewClipsIndex(sessionId)
      .then((idx) => {
        if (cancelled) return;
        setClips(idx.clips);
        if (idx.clips.length > 0) {
          setClipId(idx.clips[0].id);
          setCam(idx.clips[0].cams[0] ?? "cam1");
        }
        setLoading(false);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(String(e));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const currentClip = useMemo(
    () => clips.find((c) => c.id === clipId),
    [clips, clipId],
  );

  if (loading)
    return (
      <div className="p-4 text-sm text-gray-500">Loading review clips…</div>
    );
  if (error)
    return <div className="p-4 text-sm text-red-600">Error: {error}</div>;
  if (clips.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-500">
        No canonical evidence clips are available for this session.
      </div>
    );
  }

  const videoUrl = currentClip
    ? buildClipUrl(sessionId, currentClip.id, cam, preset)
    : "";

  return (
    <div className="flex flex-col gap-3 p-4 border rounded bg-white">
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium">Clip:</label>
        <select
          className="border rounded px-2 py-1 text-sm flex-1"
          value={clipId}
          onChange={(e) => setClipId(e.target.value)}
        >
          {clips.map((c) => (
            <option key={c.id} value={c.id}>
              {c.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Cam:</span>
        {(currentClip?.cams ?? []).map((c) => (
          <button
            key={c}
            onClick={() => setCam(c)}
            className={
              "px-3 py-1 rounded text-sm border " +
              (c === cam
                ? "bg-blue-600 text-white border-blue-600"
                : "bg-white hover:bg-gray-50")
            }
          >
            {c}
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">View:</span>
        {PRESET_ORDER.filter((p) =>
          (currentClip?.presets ?? []).includes(p),
        ).map((p) => (
          <button
            key={p}
            onClick={() => setPreset(p)}
            className={
              "px-3 py-1 rounded text-sm border " +
              (p === preset
                ? "bg-green-600 text-white border-green-600"
                : "bg-white hover:bg-gray-50")
            }
          >
            {PRESET_LABEL[p]}
          </button>
        ))}
      </div>

      <div className="bg-black rounded overflow-hidden min-h-[300px] flex items-center justify-center">
        {videoUrl ? (
          <video
            key={videoUrl}
            src={videoUrl}
            controls
            preload="metadata"
            className="w-full h-auto max-h-[60vh]"
          />
        ) : (
          <span className="text-gray-500 text-sm">Select a clip</span>
        )}
      </div>
    </div>
  );
}
