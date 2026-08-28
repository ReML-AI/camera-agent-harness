import { create } from 'zustand';
import { CriticalMoment, TranscriptSegment } from '@/types';

interface SessionState {
  sessionId: string;
  moments: CriticalMoment[];
  transcript: TranscriptSegment[];
  currentMoment: CriticalMoment | null;
  currentTime: number;
  isPlaying: boolean;
  focusedCamera: string | null;
  starredMomentIds: number[];
  selectedStudentId: string | null;

  setSessionId: (id: string) => void;
  setMoments: (moments: CriticalMoment[]) => void;
  setTranscript: (transcript: TranscriptSegment[]) => void;
  setCurrentMoment: (moment: CriticalMoment | null) => void;
  setCurrentTime: (time: number) => void;
  setIsPlaying: (playing: boolean) => void;
  setFocusedCamera: (camera: string | null) => void;
  jumpToTime: (time: number) => void;
  setStarredMomentIds: (ids: number[]) => void;
  setSelectedStudentId: (id: string | null) => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessionId: new URLSearchParams(window.location.search).get('session') ?? '',
  moments: [],
  transcript: [],
  currentMoment: null,
  currentTime: 0,
  isPlaying: false,
  focusedCamera: null,
  starredMomentIds: [],
  selectedStudentId: null,

  setSessionId: (id) => set({ sessionId: id }),
  setMoments: (moments) => set({ moments }),
  setTranscript: (transcript) => set({ transcript }),
  setCurrentMoment: (moment) => set({ currentMoment: moment }),
  setCurrentTime: (time) => set({ currentTime: time }),
  setIsPlaying: (playing) => set({ isPlaying: playing }),
  setFocusedCamera: (camera) => set({ focusedCamera: camera }),
  jumpToTime: (time) => set({ currentTime: time, isPlaying: true }),
  setStarredMomentIds: (ids) => set({ starredMomentIds: ids }),
  setSelectedStudentId: (id) => set({ selectedStudentId: id }),
}));
