/**
 * TTS 相关工具函数
 */

import { webRequest } from '../services/webClient';

export {
  makeLiveVoiceTextSpeakable,
  sanitizeLiveVoiceTtsText,
  sanitizeTtsText,
  splitLiveVoiceTtsText,
} from './ttsText';

export {
  onTtsStop,
  playAudioBase64,
  stopAllTts,
  stopGlobalAudio,
} from './ttsPlayback';

interface TtsResponse {
  success: boolean;
  audio_base64?: string;
  audio_mime?: string;
  error?: string;
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
    const params: Record<string, unknown> = { text: trimmed };
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
