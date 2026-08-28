import { create } from 'zustand';
import { FeedbackItem, RubricScores } from '@/types';

interface FeedbackState {
  feedbackItems: Map<number, FeedbackItem[]>;
  rubricScores: Map<number, RubricScores>;
  comments: Map<number, string>;

  setFeedbackItems: (momentId: number, items: FeedbackItem[]) => void;
  updateFeedbackItem: (momentId: number, index: number, item: FeedbackItem) => void;
  setRubricScores: (momentId: number, scores: RubricScores) => void;
  setComments: (momentId: number, comment: string) => void;
}

export const useFeedbackStore = create<FeedbackState>((set) => ({
  feedbackItems: new Map(),
  rubricScores: new Map(),
  comments: new Map(),

  setFeedbackItems: (momentId, items) =>
    set((state) => {
      const newMap = new Map(state.feedbackItems);
      newMap.set(momentId, items);
      return { feedbackItems: newMap };
    }),

  updateFeedbackItem: (momentId, index, item) =>
    set((state) => {
      const items = state.feedbackItems.get(momentId) || [];
      const newItems = [...items];
      newItems[index] = item;
      const newMap = new Map(state.feedbackItems);
      newMap.set(momentId, newItems);
      return { feedbackItems: newMap };
    }),

  setRubricScores: (momentId, scores) =>
    set((state) => {
      const newMap = new Map(state.rubricScores);
      newMap.set(momentId, scores);
      return { rubricScores: newMap };
    }),

  setComments: (momentId, comment) =>
    set((state) => {
      const newMap = new Map(state.comments);
      newMap.set(momentId, comment);
      return { comments: newMap };
    }),
}));
