import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSpeechRecognition } from '../../hooks/useSpeech';
import {
  combinedSpeechRecognitionTranscript,
  mergeSpeechRecognitionTranscript,
} from '../../hooks/speechRecognitionLifecycle';
import type { AgentMode, Message } from '../../types';
import {
  onTtsStop,
  sanitizeLiveVoiceTtsText,
  splitLiveVoiceTtsText,
  stopAllTts,
} from '../../utils/tts';
import { acquireLiveVoiceTtsOutputOwnership } from '../../utils/ttsOutputOwnership';
import type { LiveVoiceDemoBarProps } from '../../components/ChatPanel/LiveVoiceDemoBar';
import { createLiveVoiceCore, type LiveVoiceCore, type LiveVoiceSnapshot, type LiveVoiceSpeechPlayer } from './liveVoiceCore';
import { selectLiveVoiceResponseMessages } from './liveVoiceMessageGate';
import {
  resolveLiveVoiceSessionTransition,
  shouldResumeAfterSilentResponse,
} from './liveVoiceTurnLifecycle';

const DEMO_LANGUAGE = 'zh-CN';
const DEMO_END_OF_SPEECH_TIMEOUT_MS = 2200;
const DEMO_INITIAL_SILENCE_TIMEOUT_MS = 8000;

interface VoiceTurn {
  transcript: string;
  responseEpoch: number;
  userBoundaryId: string | null;
  responseObserved: boolean;
}

export interface UseLiveVoiceDemoOptions {
  activeSessionId: string | null;
  messages: readonly Message[];
  isProcessing: boolean;
  isThinking: boolean;
  mode: AgentMode;
  interactionBlocked: boolean;
  newSessionPromotion: {
    targetSessionId: string;
    sequence: number;
  } | null;
  onSendMessage: (content: string) => void;
  onInterrupt: (newInput?: string) => void;
}

function browserSpeechSynthesisAvailable(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance !== 'undefined';
}

function createBrowserSpeechPlayer(): LiveVoiceSpeechPlayer {
  let activeUtterance: SpeechSynthesisUtterance | null = null;

  return {
    play(text, callbacks): void {
      if (!browserSpeechSynthesisAvailable()) {
        throw new Error('Speech synthesis is not supported by this browser');
      }

      const utterance = new SpeechSynthesisUtterance(text);
      activeUtterance = utterance;
      utterance.lang = DEMO_LANGUAGE;
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.volume = 1;

      const chineseVoice = window.speechSynthesis.getVoices().find(voice => /^zh(?:-|_)/i.test(voice.lang));
      if (chineseVoice) {
        utterance.voice = chineseVoice;
      }

      utterance.onstart = () => callbacks.onStart();
      utterance.onend = () => {
        if (activeUtterance === utterance) {
          activeUtterance = null;
        }
        callbacks.onEnd();
      };
      utterance.onerror = event => {
        if (activeUtterance === utterance) {
          activeUtterance = null;
        }
        callbacks.onError(new Error(`Speech playback failed: ${event.error}`));
      };

      window.speechSynthesis.speak(utterance);
    },

    stop(): void {
      if (activeUtterance) {
        activeUtterance.onstart = null;
        activeUtterance.onend = null;
        activeUtterance.onerror = null;
        activeUtterance = null;
      }
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    },
  };
}

function createCore(): LiveVoiceCore {
  return createLiveVoiceCore({ player: createBrowserSpeechPlayer() });
}

function findErrorMessageAfterBoundary(messages: readonly Message[], userBoundaryId: string): Message | null {
  const boundaryIndex = messages.findIndex(message => message.id === userBoundaryId && message.role === 'user');
  if (boundaryIndex < 0) return null;

  let latestErrorMessage: Message | null = null;
  for (let index = boundaryIndex + 1; index < messages.length; index += 1) {
    const message = messages[index];
    if (message.role === 'user') break;
    const isExplicitError =
      message.role === 'system' && ((message as Message & { isError?: boolean }).isError === true || /(?:^|-)error(?:-|$)/i.test(message.id));
    if (isExplicitError && message.content.trim()) {
      latestErrorMessage = message;
    }
  }
  return latestErrorMessage;
}

function hasUserMessageAfterBoundary(messages: readonly Message[], userBoundaryId: string): boolean {
  const boundaryIndex = messages.findIndex(message => message.id === userBoundaryId && message.role === 'user');
  if (boundaryIndex < 0) return false;
  return messages.slice(boundaryIndex + 1).some(message => message.role === 'user');
}

/**
 * Demo adapter from browser speech to the existing Chat/Agent path.
 *
 * Speech recognition only updates local subtitles until one complete capture
 * cycle ends. The accepted final transcript is then sent through the existing
 * chat.send/supplement callbacks. TTS consumes only completed messages already
 * accepted into chatStore, never raw WebSocket output.
 */
export function useLiveVoiceDemo({
  activeSessionId,
  messages,
  isProcessing,
  isThinking,
  mode,
  interactionBlocked,
  newSessionPromotion,
  onSendMessage,
  onInterrupt,
}: UseLiveVoiceDemoOptions): LiveVoiceDemoBarProps {
  const { t } = useTranslation();
  const coreRef = useRef<LiveVoiceCore | null>(null);
  if (coreRef.current === null) {
    coreRef.current = createCore();
  }
  const core = coreRef.current;

  const [active, setActive] = useState(false);
  const [snapshot, setSnapshot] = useState<LiveVoiceSnapshot>(() => core.getSnapshot());
  const activeRef = useRef(active);
  const processingRef = useRef(isProcessing);
  const interactionBlockedRef = useRef(interactionBlocked);
  const sessionIdRef = useRef(activeSessionId);
  const previousSessionIdRef = useRef(activeSessionId);
  const lastHandledPromotionSequenceRef = useRef(newSessionPromotion?.sequence ?? 0);
  const finalChunksRef = useRef('');
  const interimChunkRef = useRef('');
  const recognitionFailedRef = useRef(false);
  const recognitionCaptureOpenRef = useRef(false);
  const retryCaptureAfterRecognitionEndRef = useRef(false);
  const beginCaptureRef = useRef<() => void>(() => {});
  const safelyStopListeningRef = useRef<() => void>(() => {});
  const pendingSupplementAfterPromotionRef = useRef<string | null>(null);
  const voiceTurnRef = useRef<VoiceTurn | null>(null);
  const spokenMessageIdsRef = useRef<Set<string>>(new Set());
  const resumeListeningAfterSpeechRef = useRef(false);
  const ignoreNextGlobalTtsStopRef = useRef(false);
  const coreSubscriptionRef = useRef<(() => void) | null>(null);
  const releaseTtsOutputOwnershipRef = useRef<(() => void) | null>(null);

  activeRef.current = active;
  processingRef.current = isProcessing;
  interactionBlockedRef.current = interactionBlocked;
  sessionIdRef.current = activeSessionId;

  const stopEveryVoiceOutput = useCallback(() => {
    ignoreNextGlobalTtsStopRef.current = true;
    stopAllTts();
  }, []);

  const acquireTtsOutputOwnership = useCallback(() => {
    if (releaseTtsOutputOwnershipRef.current === null) {
      releaseTtsOutputOwnershipRef.current = acquireLiveVoiceTtsOutputOwnership();
    }
  }, []);

  const releaseTtsOutputOwnership = useCallback(() => {
    releaseTtsOutputOwnershipRef.current?.();
    releaseTtsOutputOwnershipRef.current = null;
  }, []);

  const handleRecognitionResult = useCallback(
    (transcript: string, isFinal: boolean) => {
      if (!activeRef.current) return;
      const nextTranscript = mergeSpeechRecognitionTranscript(
        {
          finalTranscript: finalChunksRef.current,
          interimTranscript: interimChunkRef.current,
        },
        transcript,
        isFinal,
      );
      finalChunksRef.current = nextTranscript.finalTranscript;
      interimChunkRef.current = nextTranscript.interimTranscript;
      core.setInterimTranscript(combinedSpeechRecognitionTranscript(nextTranscript));
    },
    [core]
  );

  const handleRecognitionError = useCallback(
    (message: string) => {
      if (!activeRef.current || recognitionFailedRef.current) return;
      recognitionFailedRef.current = true;
      finalChunksRef.current = '';
      interimChunkRef.current = '';
      resumeListeningAfterSpeechRef.current = false;
      core.fail('speech-recognition', message);
    },
    [core]
  );

  const handleRecognitionEnd = useCallback(() => {
    const captureWasOpen = recognitionCaptureOpenRef.current;
    recognitionCaptureOpenRef.current = false;
    if (!activeRef.current) {
      recognitionFailedRef.current = false;
      retryCaptureAfterRecognitionEndRef.current = false;
      finalChunksRef.current = '';
      interimChunkRef.current = '';
      return;
    }
    if (!captureWasOpen) return;
    if (recognitionFailedRef.current) {
      recognitionFailedRef.current = false;
      const shouldRetry = retryCaptureAfterRecognitionEndRef.current;
      retryCaptureAfterRecognitionEndRef.current = false;
      if (shouldRetry) {
        queueMicrotask(() => {
          if (activeRef.current) beginCaptureRef.current();
        });
      }
      return;
    }
    if (interactionBlockedRef.current) {
      finalChunksRef.current = '';
      interimChunkRef.current = '';
      core.fail('interaction-blocked', t('liveVoice.interactionBlocked'));
      return;
    }

    // `stop()` normally promotes the last interim segment to final, but some
    // Chromium builds end without doing so. Preserve that last visible segment
    // as a fallback while still committing this logical capture only once.
    const finalTranscript = combinedSpeechRecognitionTranscript({
      finalTranscript: finalChunksRef.current,
      interimTranscript: interimChunkRef.current,
    });
    finalChunksRef.current = '';
    interimChunkRef.current = '';
    const committed = core.commitFinalTranscript(finalTranscript);
    if (!committed.accepted) {
      if (committed.reason === 'empty') {
        core.fail('no-speech', t('speech.errors.noSpeech'));
      }
      return;
    }

    voiceTurnRef.current = {
      transcript: committed.transcript,
      responseEpoch: committed.responseEpoch,
      userBoundaryId: null,
      responseObserved: false,
    };
    resumeListeningAfterSpeechRef.current = false;

    // Decide at commit time, not capture start: the Agent may start or finish
    // while the user is still speaking.
    if (processingRef.current && sessionIdRef.current === 'new') {
      // The initial voice turn is already creating the real session. App drops
      // another onSendMessage while that create is in flight, so retain only
      // this second capture and supplement once `new` is promoted.
      pendingSupplementAfterPromotionRef.current = committed.transcript;
    } else if (processingRef.current) {
      pendingSupplementAfterPromotionRef.current = null;
      onInterrupt(committed.transcript);
    } else {
      pendingSupplementAfterPromotionRef.current = null;
      onSendMessage(committed.transcript);
    }
  }, [core, onInterrupt, onSendMessage, t]);

  const shouldContinueRecognitionTail = useCallback(
    () =>
      activeRef.current &&
      recognitionCaptureOpenRef.current &&
      !recognitionFailedRef.current,
    []
  );

  const {
    startListening,
    stopListening,
    isSupported: recognitionSupported,
  } = useSpeechRecognition({
    language: DEMO_LANGUAGE,
    continuous: true,
    interimResults: true,
    silenceTimeoutMs: DEMO_END_OF_SPEECH_TIMEOUT_MS,
    initialSilenceTimeoutMs: DEMO_INITIAL_SILENCE_TIMEOUT_MS,
    restartWhen: shouldContinueRecognitionTail,
    onResult: handleRecognitionResult,
    onError: handleRecognitionError,
    onEnd: handleRecognitionEnd,
  });

  const synthesisSupported = browserSpeechSynthesisAvailable();
  const available = mode === 'agent' && !interactionBlocked && recognitionSupported && synthesisSupported;

  const beginCapture = useCallback(() => {
    if (!activeRef.current || !available) return;
    if (recognitionFailedRef.current) {
      retryCaptureAfterRecognitionEndRef.current = true;
      return;
    }
    if (recognitionCaptureOpenRef.current) return;

    // Once a new capture starts, no later message can still belong to the
    // previous voice turn. This also prevents proactive/late assistant output
    // from being spoken over the microphone while the user is talking.
    voiceTurnRef.current = null;
    finalChunksRef.current = '';
    interimChunkRef.current = '';
    resumeListeningAfterSpeechRef.current = false;
    core.beginListening();
    recognitionCaptureOpenRef.current = true;
    try {
      startListening();
    } catch (error) {
      recognitionCaptureOpenRef.current = false;
      const message = error instanceof Error && error.message ? error.message : t('speech.errors.recognitionGeneric', { error: 'start-failed' });
      core.fail('speech-recognition-start', message);
    }
  }, [available, core, startListening, t]);
  beginCaptureRef.current = beginCapture;

  const safelyStopListening = useCallback(() => {
    try {
      stopListening();
    } catch {
      // Some Chromium builds throw when stop() races an already-ended
      // recognition instance. The local capture is invalidated regardless.
      recognitionCaptureOpenRef.current = false;
    }
  }, [stopListening]);
  safelyStopListeningRef.current = safelyStopListening;

  const exitLiveVoice = useCallback(() => {
    activeRef.current = false;
    setActive(false);
    releaseTtsOutputOwnership();
    finalChunksRef.current = '';
    interimChunkRef.current = '';
    recognitionCaptureOpenRef.current = false;
    recognitionFailedRef.current = false;
    retryCaptureAfterRecognitionEndRef.current = false;
    pendingSupplementAfterPromotionRef.current = null;
    voiceTurnRef.current = null;
    resumeListeningAfterSpeechRef.current = false;
    spokenMessageIdsRef.current.clear();
    safelyStopListening();
    core.exit();
    stopEveryVoiceOutput();
  }, [core, releaseTtsOutputOwnership, safelyStopListening, stopEveryVoiceOutput]);

  const enableLiveVoice = useCallback(() => {
    if (!available || activeRef.current) return;
    acquireTtsOutputOwnership();
    activeRef.current = true;
    setActive(true);
    spokenMessageIdsRef.current = new Set(messages.filter(message => message.role === 'assistant').map(message => message.id));
    voiceTurnRef.current = null;
    pendingSupplementAfterPromotionRef.current = null;
    core.exit();
    stopEveryVoiceOutput();
    finalChunksRef.current = '';
    interimChunkRef.current = '';
    recognitionFailedRef.current = false;
    recognitionCaptureOpenRef.current = false;
    retryCaptureAfterRecognitionEndRef.current = false;
    beginCaptureRef.current();
  }, [acquireTtsOutputOwnership, available, core, messages, stopEveryVoiceOutput]);

  const handlePrimaryAction = useCallback(() => {
    switch (core.getSnapshot().status) {
      case 'listening':
        safelyStopListening();
        return;
      case 'thinking':
      case 'speaking':
        core.interrupt();
        stopEveryVoiceOutput();
        beginCapture();
        return;
      case 'error':
        core.clearError();
        beginCapture();
        return;
      case 'idle':
      case 'interrupted':
        beginCapture();
        return;
    }
  }, [beginCapture, core, safelyStopListening, stopEveryVoiceOutput]);

  useEffect(() => {
    const unsubscribe = core.subscribe(nextSnapshot => setSnapshot(nextSnapshot));
    coreSubscriptionRef.current = unsubscribe;
    return () => {
      if (coreSubscriptionRef.current === unsubscribe) {
        coreSubscriptionRef.current = null;
      }
      unsubscribe();
    };
  }, [core]);

  useLayoutEffect(() => {
    return () => {
      const shouldStopAllTts = activeRef.current;
      activeRef.current = false;
      releaseTtsOutputOwnershipRef.current?.();
      releaseTtsOutputOwnershipRef.current = null;
      finalChunksRef.current = '';
      interimChunkRef.current = '';
      recognitionCaptureOpenRef.current = false;
      recognitionFailedRef.current = false;
      retryCaptureAfterRecognitionEndRef.current = false;
      pendingSupplementAfterPromotionRef.current = null;
      voiceTurnRef.current = null;
      resumeListeningAfterSpeechRef.current = false;
      coreSubscriptionRef.current?.();
      coreSubscriptionRef.current = null;
      safelyStopListeningRef.current();
      core.exit();
      // Do not set ignoreNextGlobalTtsStop during unmount: the event listener
      // may already be gone. activeRef=false makes a still-mounted listener a
      // no-op, while stopAllTts also clears generated HTMLAudio playback.
      if (shouldStopAllTts) stopAllTts();
    };
  }, [core]);

  useEffect(() => {
    return onTtsStop(() => {
      if (ignoreNextGlobalTtsStopRef.current) {
        ignoreNextGlobalTtsStopRef.current = false;
        return;
      }
      const currentSnapshot = core.getSnapshot();
      if (activeRef.current && (currentSnapshot.status === 'speaking' || currentSnapshot.activeSpeechKey !== null || currentSnapshot.pendingSpeechCount > 0)) {
        resumeListeningAfterSpeechRef.current = false;
        core.interrupt();
      }
    });
  }, [core]);

  useEffect(() => {
    if (!active || available) return;
    exitLiveVoice();
  }, [active, available, exitLiveVoice]);

  useEffect(() => {
    const previousSessionId = previousSessionIdRef.current;
    previousSessionIdRef.current = activeSessionId;
    const promotionSequence = newSessionPromotion?.sequence ?? 0;
    const transition = resolveLiveVoiceSessionTransition({
      active: activeRef.current,
      previousSessionId,
      activeSessionId,
      promotionSequence,
      promotionTargetSessionId: newSessionPromotion?.targetSessionId ?? null,
      lastHandledPromotionSequence: lastHandledPromotionSequenceRef.current,
    });
    lastHandledPromotionSequenceRef.current = transition.nextHandledPromotionSequence;

    // Creating the first real session promotes the special `new` runtime. It
    // is the same voice turn and must keep listening/thinking across the move.
    if (transition.action === 'preserve') {
      const pendingSupplement = pendingSupplementAfterPromotionRef.current;
      pendingSupplementAfterPromotionRef.current = null;
      if (pendingSupplement) onInterrupt(pendingSupplement);
      return;
    }
    if (transition.action === 'exit') {
      exitLiveVoice();
    }
  }, [activeSessionId, exitLiveVoice, newSessionPromotion, onInterrupt]);

  useEffect(() => {
    if (!active || !voiceTurnRef.current) return;
    const turn = voiceTurnRef.current;
    const responseInProgress = isProcessing || isThinking;
    if (responseInProgress) {
      turn.responseObserved = true;
    }
    const selection = selectLiveVoiceResponseMessages({
      messages,
      voiceTranscript: turn.transcript,
      knownUserBoundaryId: turn.userBoundaryId,
      isProcessing: responseInProgress,
      spokenMessageIds: spokenMessageIdsRef.current,
    });
    turn.userBoundaryId = selection.userBoundaryId;
    if (selection.speakableMessages.length > 0) {
      turn.responseObserved = true;
    }

    if (selection.userBoundaryId && hasUserMessageAfterBoundary(messages, selection.userBoundaryId)) {
      // A later typed message owns the conversation from this point. Stop the
      // voice loop so it cannot speak or supplement the superseded voice turn.
      exitLiveVoice();
      return;
    }

    if (!responseInProgress && selection.userBoundaryId) {
      const errorMessage = findErrorMessageAfterBoundary(messages, selection.userBoundaryId);
      if (errorMessage) {
        core.fail('agent-response', errorMessage.content.trim());
        return;
      }
    }

    for (const message of selection.speakableMessages) {
      // Mark before enqueue so a synchronous store/render update cannot queue
      // the same final twice. Rejections are intentionally not retried unless
      // they belong to a later, newly committed response epoch.
      spokenMessageIdsRef.current.add(message.id);
      const text = sanitizeLiveVoiceTtsText(message.content);
      for (const [chunkIndex, chunk] of splitLiveVoiceTtsText(text).entries()) {
        const queued = core.enqueueSpeech(chunk, turn.responseEpoch, `${message.id}:${chunkIndex}`);
        if (queued.accepted) {
          resumeListeningAfterSpeechRef.current = true;
        }
      }
    }

    const latestSnapshot = core.getSnapshot();
    if (shouldResumeAfterSilentResponse({
      responseObserved: turn.responseObserved,
      responseInProgress,
      hasUserBoundary: Boolean(selection.userBoundaryId),
      isThinking: latestSnapshot.status === 'thinking',
      pendingSpeechCount: latestSnapshot.pendingSpeechCount,
    })) {
      // A real response may contain only tool/media content, or sanitization
      // may intentionally remove everything. With no error and no playable
      // text, continue the voice loop instead of remaining stuck in thinking.
      beginCapture();
    }
  }, [active, beginCapture, core, exitLiveVoice, isProcessing, isThinking, messages]);

  useEffect(() => {
    if (!active || isProcessing || isThinking) return;
    if (snapshot.status !== 'idle' || !resumeListeningAfterSpeechRef.current) return;
    resumeListeningAfterSpeechRef.current = false;
    beginCapture();
  }, [active, beginCapture, isProcessing, isThinking, snapshot.status]);

  let unavailableMessage = '';
  if (mode !== 'agent') {
    unavailableMessage = t('liveVoice.unavailable');
  } else if (interactionBlocked) {
    unavailableMessage = t('liveVoice.interactionBlocked');
  } else if (!recognitionSupported) {
    unavailableMessage = t('speech.recognitionUnsupported');
  } else if (!synthesisSupported) {
    unavailableMessage = t('speech.synthesisUnsupported');
  }

  return {
    active,
    available,
    status: snapshot.status,
    interimTranscript: snapshot.interimTranscript,
    committedTranscript: snapshot.finalTranscript,
    errorMessage: snapshot.error?.message ?? '',
    unavailableMessage,
    onEnable: enableLiveVoice,
    onExit: exitLiveVoice,
    onPrimaryAction: handlePrimaryAction,
  };
}
