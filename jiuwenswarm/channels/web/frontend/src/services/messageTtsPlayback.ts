import { useChatStore } from '../stores/chatStore';
import { playTtsText } from '../utils/tts';

/** Claim an exact message/content once, before asynchronous synthesis begins. */
export async function playMessageTts(
  sessionId: string, messageId: string, content: string, isCurrent: () => boolean
): Promise<boolean> {
  const store = useChatStore.getState();
  const message = store.getRuntime(sessionId)?.messages.find(item => item.id === messageId);
  if (!message || !content.trim() || !isCurrent() || message.audioBase64 || message.ttsRequestedText === content) return false;
  store.updateMessage(sessionId, messageId, { ttsRequestedText: content });
  return playTtsText(content, sessionId !== 'new' ? sessionId : undefined, isCurrent);
}
