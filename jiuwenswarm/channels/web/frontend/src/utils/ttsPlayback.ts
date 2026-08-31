/**
 * TTS 播放/停止工具。
 *
 * 与 ./tts 拆分的原因：正式 Live Voice 的浏览器所有权 hook 需要在启动时停掉
 * 一切在播 TTS，而它不能依赖 webClient（网络层）。全局音频实例的所有权保持
 * 单一：playAudioBase64 与 stopGlobalAudio 必须共享同一个 globalAudio。
 */

const TTS_STOP_EVENT = 'jiuwen-tts-stop';
// 全局音频实例，用于打断控制
let globalAudio: HTMLAudioElement | null = null;

export function stopGlobalAudio(): void {
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
