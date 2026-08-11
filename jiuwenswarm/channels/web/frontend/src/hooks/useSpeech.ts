/**
 * 语音输入输出 Hook
 *
 * 使用 Web Speech API 实现语音识别（STT）和语音合成（TTS）
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import i18n from '../i18n';
import {
  isSuccessfulSpeechTailNoSpeech,
  shouldContinueSpeechCaptureAfterNaturalEnd,
  shouldRetrySpeechCaptureDuringInitialSilence,
} from './speechRecognitionLifecycle';

// ============================================================================
// 语音识别 (STT)
// ============================================================================

interface UseSpeechRecognitionOptions {
  language?: string;
  continuous?: boolean;
  interimResults?: boolean;
  /** 无声音后多少毫秒结束识别，默认 5000。需配合 continuous: true 使用。 */
  silenceTimeoutMs?: number;
  /** 首次识别结果到达前允许等待的毫秒数；默认与 silenceTimeoutMs 相同。 */
  initialSilenceTimeoutMs?: number;
  /** 返回 true 时，onend 后会自动重启识别。 */
  restartWhen?: () => boolean;
  onResult?: (transcript: string, isFinal: boolean) => void;
  onError?: (error: string) => void;
  onEnd?: () => void;
}

interface UseSpeechRecognitionReturn {
  isListening: boolean;
  transcript: string;
  interimTranscript: string;
  startListening: () => void;
  stopListening: () => void;
  isSupported: boolean;
}

// Web Speech API 类型（部分浏览器/TS 未内置）
interface SpeechRecognitionEventMap {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}
interface SpeechRecognitionInstance extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start(): void;
  stop(): void;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onresult: ((event: SpeechRecognitionEventMap) => void) | null;
}
interface SpeechRecognitionConstructor {
  new (): SpeechRecognitionInstance;
}

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

// 供本文件内 ref 等使用
type SpeechRecognition = SpeechRecognitionInstance;

export function useSpeechRecognition(
  options: UseSpeechRecognitionOptions = {}
): UseSpeechRecognitionReturn {
  const {
    language = 'cmn-Hans-CN', // 普通话简体中文（比 zh-CN 更准确）
    continuous = false, // 默认检测到停止说话后自动结束
    interimResults = true,
    silenceTimeoutMs = 5000, // 无声音后 5s 结束（需配合 continuous: true）
    initialSilenceTimeoutMs = silenceTimeoutMs,
    restartWhen,
    onResult,
    onError,
    onEnd,
  } = options;

  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [interimTranscript, setInterimTranscript] = useState('');
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const recognitionGenerationRef = useRef(0);
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const manualStopRef = useRef(false);
  const autoStopRef = useRef(false);
  const useContinuousRef = useRef(false);

  // 检查浏览器支持
  const isSupported =
    typeof window !== 'undefined' &&
    (typeof window.SpeechRecognition === 'function' || typeof window.webkitSpeechRecognition === 'function');

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current);
      silenceTimerRef.current = null;
    }
  }, []);

  const scheduleSilenceStop = useCallback((recognition: SpeechRecognition, generation: number, timeoutMs: number) => {
    if (timeoutMs <= 0) {
      return;
    }
    clearSilenceTimer();
    silenceTimerRef.current = setTimeout(() => {
      silenceTimerRef.current = null;
      if (recognitionGenerationRef.current !== generation || recognitionRef.current !== recognition) {
        return;
      }
      autoStopRef.current = true;
      try {
        recognition.stop();
      } catch (error) {
        console.warn('Speech recognition auto-stop failed:', error);
        recognitionRef.current = null;
        setIsListening(false);
        onEnd?.();
      }
    }, timeoutMs);
  }, [clearSilenceTimer, onEnd]);

  const startListening = useCallback(() => {
    if (!isSupported) {
      onError?.(i18n.t('speech.recognitionUnsupported'));
      return;
    }

    clearSilenceTimer();
    const previousRecognition = recognitionRef.current;
    recognitionGenerationRef.current += 1;
    recognitionRef.current = null;
    if (previousRecognition) {
      try {
        previousRecognition.stop();
      } catch {
        // The previous instance may already be ending. Its callbacks are
        // fenced by generation and cannot mutate the replacement capture.
      }
    }
    manualStopRef.current = false;
    autoStopRef.current = false;

    // 创建识别实例
    const SpeechRecognitionCtor =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      onError?.(i18n.t('speech.recognitionUnsupported'));
      onEnd?.();
      return;
    }
    let recognition: SpeechRecognition;
    try {
      recognition = new SpeechRecognitionCtor();
    } catch (error) {
      console.error('Speech recognition initialization failed:', error);
      setIsListening(false);
      onError?.(i18n.t('speech.errors.recognitionGeneric', { error: 'initialization' }));
      onEnd?.();
      return;
    }
    const generation = recognitionGenerationRef.current;
    const isCurrentRecognition = () =>
      recognitionGenerationRef.current === generation && recognitionRef.current === recognition;
    const initialSilenceDeadline = Date.now() + initialSilenceTimeoutMs;
    let currentSilenceDeadline = initialSilenceDeadline;
    let receivedAnyResult = false;
    let retryAfterInitialNoSpeech = false;
    let successfulTailNoSpeech = false;
    let terminalRecognitionError = false;

    const scheduleCurrentSilenceDeadline = () => {
      const configuredTimeoutMs = receivedAnyResult
        ? silenceTimeoutMs
        : initialSilenceTimeoutMs;
      if (configuredTimeoutMs <= 0) return;
      scheduleSilenceStop(
        recognition,
        generation,
        Math.max(1, currentSilenceDeadline - Date.now()),
      );
    };

    // 使用自定义静默超时时，用 continuous=true 避免浏览器约 2s 就结束
    const useContinuous = continuous || silenceTimeoutMs > 0;
    useContinuousRef.current = useContinuous;
    recognition.lang = language;
    recognition.continuous = useContinuous;
    recognition.interimResults = interimResults;

    recognition.onstart = () => {
      if (!isCurrentRecognition()) return;
      setIsListening(true);
      setTranscript('');
      setInterimTranscript('');
      // Starting the short end-of-speech timer here can cut a real user off
      // before Chrome emits its first interim result. Give device pickup and
      // the user's first word a separate, longer window.
      // A browser-level natural restart after a result keeps the existing
      // trailing deadline instead of granting a new full initial-silence span.
      scheduleCurrentSilenceDeadline();
    };

    recognition.onresult = (event) => {
      if (!isCurrentRecognition()) return;
      let finalTranscript = '';
      let interim = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        if (result.isFinal) {
          finalTranscript += result[0].transcript;
        } else {
          interim += result[0].transcript;
        }
      }

      if (finalTranscript || interim) {
        receivedAnyResult = true;
        currentSilenceDeadline = Date.now() + silenceTimeoutMs;
      }

      if (finalTranscript) {
        setTranscript((prev) => prev + finalTranscript);
        onResult?.(finalTranscript, true);
        scheduleCurrentSilenceDeadline();
      }

      setInterimTranscript(interim);
      if (interim) {
        onResult?.(interim, false);
        scheduleCurrentSilenceDeadline();
      }
    };

    recognition.onerror = (event) => {
      if (!isCurrentRecognition()) return;
      if (isSuccessfulSpeechTailNoSpeech(event.error, receivedAnyResult)) {
        // A restarted recognition instance often reports no-speech once the
        // user has finished. Earlier final chunks remain valid and are
        // committed by the following onend exactly once.
        successfulTailNoSpeech = true;
        clearSilenceTimer();
        return;
      }
      if (
        event.error === 'no-speech' &&
        !receivedAnyResult &&
        Date.now() < initialSilenceDeadline
      ) {
        // Chromium may end an otherwise healthy capture after only a few
        // seconds of initial silence. Keep the same logical capture alive
        // until the Demo's explicit initial-silence deadline instead of
        // forcing the user to race a browser-specific timeout.
        retryAfterInitialNoSpeech = true;
        clearSilenceTimer();
        return;
      }
      terminalRecognitionError = true;
      console.error('Speech recognition error:', event.error);
      clearSilenceTimer();
      setIsListening(false);
      
      const errorMessages: Record<string, string> = {
        'no-speech': i18n.t('speech.errors.noSpeech'),
        'audio-capture': i18n.t('speech.errors.noMic'),
        'not-allowed': i18n.t('speech.errors.notAllowed'),
        'network': i18n.t('speech.errors.network'),
      };
      
      onError?.(errorMessages[event.error] || i18n.t('speech.errors.recognitionGeneric', { error: event.error }));
    };

    recognition.onend = () => {
      if (!isCurrentRecognition()) return;
      clearSilenceTimer();
      if (shouldRetrySpeechCaptureDuringInitialSilence({
        retryRequested: retryAfterInitialNoSpeech,
        receivedAnyResult,
        beforeInitialDeadline: Date.now() < initialSilenceDeadline,
        terminalRecognitionError,
        manualStop: manualStopRef.current,
        autoStop: autoStopRef.current,
      })) {
        retryAfterInitialNoSpeech = false;
        try {
          recognition.start();
          return;
        } catch (error) {
          console.warn('Speech recognition initial-silence retry failed:', error);
        }
      }
      if (manualStopRef.current) {
        manualStopRef.current = false;
        recognitionRef.current = null;
        setIsListening(false);
        onEnd?.();
        return;
      }
      if (autoStopRef.current) {
        autoStopRef.current = false;
        recognitionRef.current = null;
        setIsListening(false);
        onEnd?.();
        return;
      }
      if (successfulTailNoSpeech) {
        successfulTailNoSpeech = false;
        recognitionRef.current = null;
        setIsListening(false);
        onEnd?.();
        return;
      }
      let restartRequested = false;
      if (!terminalRecognitionError && receivedAnyResult) {
        try {
          restartRequested = restartWhen?.() ?? false;
        } catch (error) {
          console.warn('Speech recognition restart condition failed:', error);
        }
      }
      if (shouldContinueSpeechCaptureAfterNaturalEnd({
        useContinuous: useContinuousRef.current,
        restartRequested,
        receivedAnyResult,
        terminalRecognitionError,
        manualStop: manualStopRef.current,
        autoStop: autoStopRef.current,
      })) {
        try {
          recognition.start();
          return;
        } catch (error) {
          console.warn('Speech recognition restart failed:', error);
        }
      }
      recognitionRef.current = null;
      setIsListening(false);
      onEnd?.();
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch (error) {
      if (isCurrentRecognition()) {
        recognitionRef.current = null;
      }
      console.error('Speech recognition start failed:', error);
      setIsListening(false);
      onError?.(i18n.t('speech.errors.recognitionGeneric', { error: 'start' }));
      onEnd?.();
    }
  }, [isSupported, language, continuous, interimResults, silenceTimeoutMs, initialSilenceTimeoutMs, restartWhen, onResult, onError, onEnd, clearSilenceTimer]);

  const stopListening = useCallback(() => {
    clearSilenceTimer();
    const recognition = recognitionRef.current;
    if (recognition) {
      manualStopRef.current = true;
      try {
        recognition.stop();
      } catch (error) {
        console.warn('Speech recognition stop failed:', error);
        if (recognitionRef.current === recognition) {
          recognitionRef.current = null;
          recognitionGenerationRef.current += 1;
          manualStopRef.current = false;
          onEnd?.();
        }
      }
    }
    setIsListening(false);
  }, [clearSilenceTimer, onEnd]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      clearSilenceTimer();
      recognitionGenerationRef.current += 1;
      const recognition = recognitionRef.current;
      recognitionRef.current = null;
      if (recognition) {
        try {
          recognition.stop();
        } catch {
          // Unmount cleanup is best-effort and all callbacks are stale now.
        }
      }
    };
  }, [clearSilenceTimer]);

  return {
    isListening,
    transcript,
    interimTranscript,
    startListening,
    stopListening,
    isSupported,
  };
}

// ============================================================================
// 语音合成 (TTS)
// ============================================================================

interface UseSpeechSynthesisOptions {
  language?: string;
  rate?: number;
  pitch?: number;
  volume?: number;
  onStart?: () => void;
  onEnd?: () => void;
  onError?: (error: string) => void;
}

interface UseSpeechSynthesisReturn {
  isSpeaking: boolean;
  speak: (text: string) => void;
  stop: () => void;
  pause: () => void;
  resume: () => void;
  isSupported: boolean;
  voices: SpeechSynthesisVoice[];
}

export function useSpeechSynthesis(
  options: UseSpeechSynthesisOptions = {}
): UseSpeechSynthesisReturn {
  const {
    language = 'zh-CN',
    rate = 1,
    pitch = 1,
    volume = 1,
    onStart,
    onEnd,
    onError,
  } = options;

  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  // 检查浏览器支持
  const isSupported =
    typeof window !== 'undefined' && 'speechSynthesis' in window;

  // 加载可用语音
  useEffect(() => {
    if (!isSupported) return;

    const loadVoices = () => {
      const availableVoices = window.speechSynthesis.getVoices();
      setVoices(availableVoices);
    };

    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    return () => {
      window.speechSynthesis.onvoiceschanged = null;
    };
  }, [isSupported]);

  const speak = useCallback(
    (text: string) => {
      if (!isSupported) {
        onError?.(i18n.t('speech.synthesisUnsupported'));
        return;
      }

      // 停止当前播放
      window.speechSynthesis.cancel();

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = language;
      utterance.rate = rate;
      utterance.pitch = pitch;
      utterance.volume = volume;

      // 选择合适的中文语音
      const chineseVoice = voices.find(
        (v) => v.lang.includes('zh') || v.lang.includes('CN')
      );
      if (chineseVoice) {
        utterance.voice = chineseVoice;
      }

      utterance.onstart = () => {
        setIsSpeaking(true);
        onStart?.();
      };

      utterance.onend = () => {
        setIsSpeaking(false);
        onEnd?.();
      };

      utterance.onerror = (event) => {
        console.error('Speech synthesis error:', event);
        setIsSpeaking(false);
        onError?.(i18n.t('speech.errors.synthesisGeneric', { error: event.error }));
      };

      utteranceRef.current = utterance;
      window.speechSynthesis.speak(utterance);
    },
    [isSupported, language, rate, pitch, volume, voices, onStart, onEnd, onError]
  );

  const stop = useCallback(() => {
    if (isSupported) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    }
  }, [isSupported]);

  const pause = useCallback(() => {
    if (isSupported) {
      window.speechSynthesis.pause();
    }
  }, [isSupported]);

  const resume = useCallback(() => {
    if (isSupported) {
      window.speechSynthesis.resume();
    }
  }, [isSupported]);

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      if (isSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [isSupported]);

  return {
    isSpeaking,
    speak,
    stop,
    pause,
    resume,
    isSupported,
    voices,
  };
}
