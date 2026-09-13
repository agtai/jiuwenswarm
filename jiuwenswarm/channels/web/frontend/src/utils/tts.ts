/**
 * TTS 相关工具函数
 */

import { webRequest } from '../services/webClient';
import { TtsPlaybackQueue } from './ttsPlaybackQueue';

export {
  makeLiveVoiceTextSpeakable,
  sanitizeLiveVoiceTtsText,
  sanitizeTtsText,
  splitLiveVoiceTtsText,
} from './ttsText';

interface TtsResponse {
  success: boolean;
  audio_base64?: string;
  audio_mime?: string;
  error?: string;
}

const TTS_STOP_EVENT = 'jiuwen-tts-stop';
// 全局音频实例，用于打断控制
let globalAudio: HTMLAudioElement | null = null;
let settleAudio: (() => void) | null = null;
const playbackQueue = new TtsPlaybackQueue();

export function stopGlobalAudio(): void {
  playbackQueue.stop();
  clearCurrentAudio();
}

function clearCurrentAudio(): void {
  settleAudio?.();
  settleAudio = null;
  if (globalAudio) {
    globalAudio.pause();
    globalAudio.currentTime = 0;
    globalAudio = null;
  }
}

export function stopAllTts(): void {
  stopGlobalAudio();

  if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
    window.speechSynthesis.cancel();
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(TTS_STOP_EVENT));
  }
}

export function onTtsStop(handler: () => void): () => void {
  if (typeof window === 'undefined') {
    return () => {};
  }

  window.addEventListener(TTS_STOP_EVENT, handler);
  return () => window.removeEventListener(TTS_STOP_EVENT, handler);
}

export async function fetchTtsAudio(
  text: string,
  sessionId?: string,
  signal?: AbortSignal
): Promise<TtsResponse | null> {
  const trimmed = text.trim();
  if (!trimmed) {
    return null;
  }

  try {
    const params: Record<string, unknown> = { text };
    if (sessionId) {
      params.session_id = sessionId;
    }
    const response = await webRequest<TtsResponse>('tts.synthesize', params, {
      signal,
    });
    return response;
  } catch (error) {
    console.warn('TTS 请求失败:', error);
    return null;
  }
}

/** Synthesize only the next chunk after the current audio ends. */
export async function playTtsText(
  text: string, sessionId?: string, isCurrent: () => boolean = () => true
): Promise<boolean> {
  stopAllTts();
  return playbackQueue.play(text, async (chunk, signal) => {
    if (!chunk.trim()) return true;
    const response = await fetchTtsAudio(chunk, sessionId, signal);
    if (signal.aborted || !isCurrent() || !response?.success || !response.audio_base64) return false;
    return new Promise<boolean>((resolve) => {
      const audio = new Audio(`data:${response.audio_mime || 'audio/mpeg'};base64,${response.audio_base64}`);
      let settled = false;
      const finish = (completed: boolean) => {
        if (settled) return;
        settled = true;
        signal.removeEventListener('abort', abort);
        audio.onended = null;
        audio.onerror = null;
        audio.pause();
        if (globalAudio === audio) {
          globalAudio = null;
          settleAudio = null;
        }
        resolve(completed);
      };
      const abort = () => finish(false);
      globalAudio = audio;
      settleAudio = abort;
      signal.addEventListener('abort', abort, { once: true });
      audio.onended = () => finish(true);
      audio.onerror = abort;
      void audio.play().catch(abort);
    });
  }, isCurrent);
}

export async function playAudioBase64(
  audioBase64: string,
  mimeType = 'audio/mpeg'
): Promise<boolean> {
  if (!audioBase64) {
    return false;
  }

  // 先停止正在播放的音频
  stopGlobalAudio();

  try {
    const audio = new Audio(`data:${mimeType};base64,${audioBase64}`);
    globalAudio = audio;
    audio.onended = () => {
      if (globalAudio === audio) {
        globalAudio = null;
      }
    };
    await audio.play();
    return true;
  } catch (error) {
    console.warn('播放音频失败:', error);
    return false;
  }
}
