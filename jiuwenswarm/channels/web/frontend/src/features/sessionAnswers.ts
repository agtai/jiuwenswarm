import type { UserAnswer } from '../types';

// Answers a pending question of any session, not only the open one. App registers its
// sendUserAnswer here, so plugin pages (Blackboard's chat box) answer the way the chat page does.
type AnswerHandler = (sessionId: string, requestId: string, answers: UserAnswer[], source?: string) => Promise<boolean>;

let handler: AnswerHandler | null = null;

export function registerSessionAnswerHandler(next: AnswerHandler): () => void {
  handler = next;
  return () => {
    if (handler === next) handler = null;
  };
}

export function answerSessionQuestion(
  sessionId: string,
  requestId: string,
  answers: UserAnswer[],
  source?: string,
): Promise<boolean> {
  return handler ? handler(sessionId, requestId, answers, source) : Promise.resolve(false);
}
