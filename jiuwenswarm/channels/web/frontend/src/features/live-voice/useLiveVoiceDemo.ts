import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useSpeechRecognition } from '../../hooks/useSpeech';
import { combinedSpeechRecognitionTranscript, mergeSpeechRecognitionTranscript } from '../../hooks/speechRecognitionLifecycle';
import type { AgentMode, Message } from '../../types';
import { onTtsStop, sanitizeLiveVoiceTtsText, splitLiveVoiceTtsText, stopAllTts } from '../../utils/tts';
import { acquireLiveVoiceTtsOutputOwnership } from '../../utils/ttsOutputOwnership';
import type { LiveVoiceDemoBarProps } from '../../components/ChatPanel/LiveVoiceDemoBar';
import { FEATURE_LIVE_VOICE_INTEGRATED_P1, FEATURE_LIVE_VOICE_STREAMING_SPEECH } from '../../featureFlags';
import { createLiveVoiceCore, type LiveVoiceCore, type LiveVoiceSnapshot, type LiveVoiceSpeechPlayer } from './liveVoiceCore';
import { selectLiveVoiceResponseMessages } from './liveVoiceMessageGate';
import { advanceLiveVoiceStreamingSpeech, createLiveVoiceStreamingSpeechState } from './liveVoiceStreamingSpeech';
import {
  LIVE_VOICE_STREAMING_FINAL_TIMEOUT_MS,
  resolveLiveVoiceSessionTransition,
  resolveLiveVoiceTurnOriginatingSessionId,
  selectLiveVoicePostSpeechAction,
  selectLiveVoiceStreamingFinalTimeoutAction,
  shouldResumeAfterSilentResponse,
} from './liveVoiceTurnLifecycle';
import { createIntegratedP1Route, type IntegratedP1Route } from './formal/integratedP1Route';

const DEMO_LANGUAGE = 'zh-CN';
const DEMO_END_OF_SPEECH_TIMEOUT_MS = 2200;
const DEMO_INITIAL_SILENCE_TIMEOUT_MS = 8000;

interface VoiceTurn {
  transcript: string;
  responseEpoch: number;
  originatingSessionId: string | null;
  userBoundaryId: string | null;
  responseObserved: boolean;
}

interface StreamingFinalTimeoutRegistration {
  responseEpoch: number;
  originatingSessionId: string;
  timeoutId: ReturnType<typeof setTimeout>;
}

export interface UseLiveVoiceDemoOptions {
  activeSessionId: string | null;
  messages: readonly Message[];
  isProcessing: boolean;
  isThinking: boolean;
  isConnected: boolean;
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

function createCore(player: LiveVoiceSpeechPlayer = createBrowserSpeechPlayer()): LiveVoiceCore {
  return createLiveVoiceCore({ player });
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
 * chat.send/supplement callbacks. TTS consumes only message snapshots already
 * accepted into chatStore, never raw WebSocket output. The optional Post-V0
 * sentence preview remains behind a separate feature flag.
 */
export function useLiveVoiceDemo({
  activeSessionId,
  messages,
  isProcessing,
  isThinking,
  isConnected,
  mode,
  interactionBlocked,
  newSessionPromotion,
  onSendMessage,
  onInterrupt,
}: UseLiveVoiceDemoOptions): LiveVoiceDemoBarProps {
  const { t } = useTranslation();
  const integratedP1RouteRef = useRef<IntegratedP1Route | null>(null);
  if (FEATURE_LIVE_VOICE_INTEGRATED_P1 && integratedP1RouteRef.current === null) {
    integratedP1RouteRef.current = createIntegratedP1Route({ correlationId: 'live-voice-browser-p1' });
  }
  const integratedP1Route = integratedP1RouteRef.current;
  const coreRef = useRef<LiveVoiceCore | null>(null);
  if (coreRef.current === null) {
    coreRef.current = createCore(integratedP1Route?.speechPlayer);
  }
  const core = coreRef.current;

  const [active, setActive] = useState(false);
  const [snapshot, setSnapshot] = useState<LiveVoiceSnapshot>(() => core.getSnapshot());
  const activeRef = useRef(active);
  const connectedRef = useRef(isConnected);
  const processingRef = useRef(isProcessing);
  const responseInProgressRef = useRef(isProcessing || isThinking);
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
  const streamingSpeechStateRef = useRef(createLiveVoiceStreamingSpeechState());
  const streamingFinalTimeoutRef = useRef<StreamingFinalTimeoutRegistration | null>(null);
  const resumeListeningAfterSpeechRef = useRef(false);
  const ignoreNextGlobalTtsStopRef = useRef(false);
  const coreSubscriptionRef = useRef<(() => void) | null>(null);
  const releaseTtsOutputOwnershipRef = useRef<(() => void) | null>(null);

  activeRef.current = active;
  connectedRef.current = isConnected;
  processingRef.current = isProcessing;
  responseInProgressRef.current = isProcessing || isThinking;
  interactionBlockedRef.current = interactionBlocked;
  sessionIdRef.current = activeSessionId;

  const clearStreamingFinalTimeout = useCallback(() => {
    const registration = streamingFinalTimeoutRef.current;
    streamingFinalTimeoutRef.current = null;
    if (registration) {
      clearTimeout(registration.timeoutId);
    }
  }, []);

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
      const observation = integratedP1Route?.observeRecognition(transcript, isFinal);
      if (integratedP1Route && observation === null) return;
      const nextTranscript = mergeSpeechRecognitionTranscript(
        {
          finalTranscript: finalChunksRef.current,
          interimTranscript: interimChunkRef.current,
        },
        observation?.display_text ?? transcript,
        observation?.kind === 'final' || (!observation && isFinal)
      );
      finalChunksRef.current = nextTranscript.finalTranscript;
      interimChunkRef.current = nextTranscript.interimTranscript;
      core.setInterimTranscript(combinedSpeechRecognitionTranscript(nextTranscript));
    },
    [core, integratedP1Route]
  );

  const handleRecognitionError = useCallback(
    (message: string) => {
      if (!activeRef.current || recognitionFailedRef.current) return;
      integratedP1Route?.cancelRecognition();
      recognitionFailedRef.current = true;
      finalChunksRef.current = '';
      interimChunkRef.current = '';
      resumeListeningAfterSpeechRef.current = false;
      core.fail('speech-recognition', message);
    },
    [core, integratedP1Route]
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
    integratedP1Route?.finishRecognition();
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
      originatingSessionId: sessionIdRef.current,
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
  }, [core, integratedP1Route, onInterrupt, onSendMessage, t]);

  const shouldContinueRecognitionTail = useCallback(() => activeRef.current && recognitionCaptureOpenRef.current && !recognitionFailedRef.current, []);

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
    clearStreamingFinalTimeout();
    voiceTurnRef.current = null;
    streamingSpeechStateRef.current = createLiveVoiceStreamingSpeechState();
    finalChunksRef.current = '';
    interimChunkRef.current = '';
    resumeListeningAfterSpeechRef.current = false;
    integratedP1Route?.beginRecognition();
    core.beginListening();
    recognitionCaptureOpenRef.current = true;
    try {
      startListening();
    } catch (error) {
      integratedP1Route?.cancelRecognition();
      recognitionCaptureOpenRef.current = false;
      const message = error instanceof Error && error.message ? error.message : t('speech.errors.recognitionGeneric', { error: 'start-failed' });
      core.fail('speech-recognition-start', message);
    }
  }, [available, clearStreamingFinalTimeout, core, integratedP1Route, startListening, t]);
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
    integratedP1Route?.cancelRecognition();
    retryCaptureAfterRecognitionEndRef.current = false;
    pendingSupplementAfterPromotionRef.current = null;
    clearStreamingFinalTimeout();
    voiceTurnRef.current = null;
    streamingSpeechStateRef.current = createLiveVoiceStreamingSpeechState();
    resumeListeningAfterSpeechRef.current = false;
    spokenMessageIdsRef.current.clear();
    safelyStopListening();
    core.exit();
    stopEveryVoiceOutput();
  }, [clearStreamingFinalTimeout, core, integratedP1Route, releaseTtsOutputOwnership, safelyStopListening, stopEveryVoiceOutput]);

  const enableLiveVoice = useCallback(() => {
    if (!available || activeRef.current) return;
    acquireTtsOutputOwnership();
    activeRef.current = true;
    setActive(true);
    spokenMessageIdsRef.current = new Set(messages.filter(message => message.role === 'assistant').map(message => message.id));
    clearStreamingFinalTimeout();
    voiceTurnRef.current = null;
    streamingSpeechStateRef.current = createLiveVoiceStreamingSpeechState();
    pendingSupplementAfterPromotionRef.current = null;
    core.exit();
    stopEveryVoiceOutput();
    finalChunksRef.current = '';
    interimChunkRef.current = '';
    recognitionFailedRef.current = false;
    recognitionCaptureOpenRef.current = false;
    retryCaptureAfterRecognitionEndRef.current = false;
    beginCaptureRef.current();
  }, [acquireTtsOutputOwnership, available, clearStreamingFinalTimeout, core, messages, stopEveryVoiceOutput]);

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
      clearStreamingFinalTimeout();
      voiceTurnRef.current = null;
      streamingSpeechStateRef.current = createLiveVoiceStreamingSpeechState();
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
  }, [clearStreamingFinalTimeout, core]);

  useEffect(() => {
    return onTtsStop(() => {
      if (ignoreNextGlobalTtsStopRef.current) {
        ignoreNextGlobalTtsStopRef.current = false;
        return;
      }
      const currentSnapshot = core.getSnapshot();
      if (activeRef.current && (currentSnapshot.status === 'speaking' || currentSnapshot.activeSpeechKey !== null || currentSnapshot.pendingSpeechCount > 0)) {
        resumeListeningAfterSpeechRef.current = false;
        clearStreamingFinalTimeout();
        streamingSpeechStateRef.current = createLiveVoiceStreamingSpeechState();
        core.interrupt();
      }
    });
  }, [clearStreamingFinalTimeout, core]);

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
      const currentTurn = voiceTurnRef.current;
      if (currentTurn) {
        currentTurn.originatingSessionId = resolveLiveVoiceTurnOriginatingSessionId({
          originatingSessionId: currentTurn.originatingSessionId,
          previousSessionId,
          activeSessionId,
          transitionAction: transition.action,
        });
      }
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
      plannerMessageId:
        FEATURE_LIVE_VOICE_STREAMING_SPEECH && streamingSpeechStateRef.current.responseEpoch === turn.responseEpoch
          ? streamingSpeechStateRef.current.messageId
          : null,
      requireAuthoritativeFinal: FEATURE_LIVE_VOICE_STREAMING_SPEECH,
    });
    turn.userBoundaryId = selection.userBoundaryId;
    if (selection.speakableMessages.length > 0 || selection.streamingCandidate || selection.plannerFinalObservation) {
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

    if (FEATURE_LIVE_VOICE_STREAMING_SPEECH && selection.plannerFinalObservation) {
      const message = selection.plannerFinalObservation;
      const previousStreamingState = streamingSpeechStateRef.current;
      const planned = advanceLiveVoiceStreamingSpeech(previousStreamingState, {
        responseEpoch: turn.responseEpoch,
        messageId: message.id,
        rawContent: message.content,
        phase: 'final',
      });
      streamingSpeechStateRef.current = planned.state;
      spokenMessageIdsRef.current.add(message.id);
      if (planned.outcome === 'mismatch') {
        if (previousStreamingState.mode !== 'mismatch') {
          resumeListeningAfterSpeechRef.current = false;
          core.fail('streaming-speech-revision', t('liveVoice.streamingRevisionFallback'));
        }
        return;
      }
      for (const emission of planned.emissions) {
        const queued = core.enqueueSpeech(emission.text, emission.responseEpoch, emission.key);
        if (queued.accepted) {
          resumeListeningAfterSpeechRef.current = true;
        }
      }
    }

    if (FEATURE_LIVE_VOICE_STREAMING_SPEECH && selection.streamingCandidate) {
      const previousStreamingState = streamingSpeechStateRef.current;
      const planned = advanceLiveVoiceStreamingSpeech(previousStreamingState, {
        responseEpoch: turn.responseEpoch,
        messageId: selection.streamingCandidate.id,
        rawContent: selection.streamingCandidate.content,
        phase: 'streaming',
      });
      streamingSpeechStateRef.current = planned.state;
      if (planned.outcome === 'mismatch') {
        if (previousStreamingState.mode !== 'mismatch') {
          resumeListeningAfterSpeechRef.current = false;
          core.fail('streaming-speech-revision', t('liveVoice.streamingRevisionFallback'));
        }
        return;
      }
      for (const emission of planned.emissions) {
        const queued = core.enqueueSpeech(emission.text, emission.responseEpoch, emission.key);
        if (queued.accepted) {
          resumeListeningAfterSpeechRef.current = true;
        }
      }
    }

    for (const message of selection.speakableMessages) {
      // Mark before enqueue so a synchronous store/render update cannot queue
      // the same final twice. Rejections are intentionally not retried unless
      // they belong to a later, newly committed response epoch.
      spokenMessageIdsRef.current.add(message.id);

      if (FEATURE_LIVE_VOICE_STREAMING_SPEECH) {
        const previousStreamingState = streamingSpeechStateRef.current;
        // A chat.final collapse may replace the streaming message with a new
        // ID inside the same response epoch. Always let the planner reconcile
        // a single final message: before early speech it can safely fall back
        // to final-only; after early speech it must stop on the ID mismatch
        // instead of replaying the whole final through the legacy path.
        if (selection.finalAssistantMessageCount === 1) {
          const planned = advanceLiveVoiceStreamingSpeech(previousStreamingState, {
            responseEpoch: turn.responseEpoch,
            messageId: message.id,
            rawContent: message.content,
            phase: 'final',
          });
          streamingSpeechStateRef.current = planned.state;
          if (planned.outcome === 'mismatch') {
            spokenMessageIdsRef.current.delete(message.id);
            if (previousStreamingState.mode !== 'mismatch') {
              resumeListeningAfterSpeechRef.current = false;
              core.fail('streaming-speech-revision', t('liveVoice.streamingRevisionFallback'));
            }
            return;
          }
          for (const emission of planned.emissions) {
            const queued = core.enqueueSpeech(emission.text, emission.responseEpoch, emission.key);
            if (queued.accepted) {
              resumeListeningAfterSpeechRef.current = true;
            }
          }
          continue;
        }
      }

      const text = sanitizeLiveVoiceTtsText(message.content);
      for (const [chunkIndex, chunk] of splitLiveVoiceTtsText(text).entries()) {
        const queued = core.enqueueSpeech(chunk, turn.responseEpoch, `${message.id}:${chunkIndex}`);
        if (queued.accepted) {
          resumeListeningAfterSpeechRef.current = true;
        }
      }
    }

    const latestSnapshot = core.getSnapshot();
    const latestStreamingPlan = streamingSpeechStateRef.current;
    const currentSessionId = sessionIdRef.current;
    const finalTimeoutAction = selectLiveVoiceStreamingFinalTimeoutAction({
      streamingEnabled: FEATURE_LIVE_VOICE_STREAMING_SPEECH,
      liveVoiceActive: activeRef.current,
      responseInProgress,
      responseObserved: turn.responseObserved,
      originatingSessionId: turn.originatingSessionId,
      activeSessionId: currentSessionId,
      currentTurnResponseEpoch: turn.responseEpoch,
      plannerResponseEpoch: latestStreamingPlan.responseEpoch,
      plannerMessageId: latestStreamingPlan.messageId,
      plannerMode: latestStreamingPlan.mode,
      status: latestSnapshot.status,
      pendingSpeechCount: latestSnapshot.pendingSpeechCount,
      activeSpeechKey: latestSnapshot.activeSpeechKey,
      timeoutExpired: false,
    });
    if (
      turn.originatingSessionId === currentSessionId &&
      finalTimeoutAction !== 'wait' &&
      shouldResumeAfterSilentResponse({
        responseObserved: turn.responseObserved,
        responseInProgress,
        hasUserBoundary: Boolean(selection.userBoundaryId),
        isThinking: latestSnapshot.status === 'thinking',
        pendingSpeechCount: latestSnapshot.pendingSpeechCount,
      })
    ) {
      // A real response may contain only tool/media content, or sanitization
      // may intentionally remove everything. With no error and no playable
      // text, continue the voice loop instead of remaining stuck in thinking.
      beginCapture();
    }
  }, [active, beginCapture, core, exitLiveVoice, isProcessing, isThinking, messages, t]);

  useEffect(() => {
    const currentSnapshot = core.getSnapshot();
    const currentTurn = voiceTurnRef.current;
    const currentPlan = streamingSpeechStateRef.current;
    const currentSessionId = activeSessionId;
    const action = selectLiveVoiceStreamingFinalTimeoutAction({
      streamingEnabled: FEATURE_LIVE_VOICE_STREAMING_SPEECH,
      liveVoiceActive: active,
      responseInProgress: isProcessing || isThinking,
      responseObserved: currentTurn?.responseObserved ?? false,
      originatingSessionId: currentTurn?.originatingSessionId ?? null,
      activeSessionId: currentSessionId,
      currentTurnResponseEpoch: currentTurn?.responseEpoch ?? null,
      plannerResponseEpoch: currentPlan.responseEpoch,
      plannerMessageId: currentPlan.messageId,
      plannerMode: currentPlan.mode,
      status: currentSnapshot.status,
      pendingSpeechCount: currentSnapshot.pendingSpeechCount,
      activeSpeechKey: currentSnapshot.activeSpeechKey,
      timeoutExpired: false,
    });

    if (action !== 'wait' || currentTurn === null) {
      clearStreamingFinalTimeout();
      return;
    }
    if (
      streamingFinalTimeoutRef.current?.responseEpoch === currentTurn.responseEpoch &&
      streamingFinalTimeoutRef.current.originatingSessionId === currentTurn.originatingSessionId
    ) {
      return;
    }
    if (currentTurn.originatingSessionId === null) {
      clearStreamingFinalTimeout();
      return;
    }

    clearStreamingFinalTimeout();
    let registration: StreamingFinalTimeoutRegistration;
    registration = {
      responseEpoch: currentTurn.responseEpoch,
      originatingSessionId: currentTurn.originatingSessionId,
      timeoutId: setTimeout(() => {
        if (streamingFinalTimeoutRef.current !== registration) return;
        streamingFinalTimeoutRef.current = null;

        const latestSnapshot = core.getSnapshot();
        const latestTurn = voiceTurnRef.current;
        const latestPlan = streamingSpeechStateRef.current;
        const expiredAction = selectLiveVoiceStreamingFinalTimeoutAction({
          streamingEnabled: FEATURE_LIVE_VOICE_STREAMING_SPEECH,
          liveVoiceActive: activeRef.current,
          responseInProgress: responseInProgressRef.current,
          responseObserved: latestTurn?.responseObserved ?? false,
          originatingSessionId: latestTurn?.originatingSessionId ?? null,
          activeSessionId: sessionIdRef.current,
          currentTurnResponseEpoch: latestTurn?.responseEpoch ?? null,
          plannerResponseEpoch: latestPlan.responseEpoch,
          plannerMessageId: latestPlan.messageId,
          plannerMode: latestPlan.mode,
          status: latestSnapshot.status,
          pendingSpeechCount: latestSnapshot.pendingSpeechCount,
          activeSpeechKey: latestSnapshot.activeSpeechKey,
          timeoutExpired: true,
        });
        if (latestTurn?.originatingSessionId !== registration.originatingSessionId) return;
        if (expiredAction !== 'recover') return;

        // Missing chat.final is not permission to speak provisional content as
        // final. Invalidate this epoch and expose a retryable error instead.
        voiceTurnRef.current = null;
        streamingSpeechStateRef.current = createLiveVoiceStreamingSpeechState();
        resumeListeningAfterSpeechRef.current = false;
        core.fail('streaming-final-timeout', t('liveVoice.streamingFinalTimeout'));
      }, LIVE_VOICE_STREAMING_FINAL_TIMEOUT_MS),
    };
    streamingFinalTimeoutRef.current = registration;
  }, [
    active,
    activeSessionId,
    clearStreamingFinalTimeout,
    core,
    isProcessing,
    isThinking,
    messages,
    snapshot.activeSpeechKey,
    snapshot.pendingSpeechCount,
    snapshot.status,
    t,
  ]);

  useEffect(() => {
    if (!active) return;
    const currentSnapshot = core.getSnapshot();
    const currentTurn = voiceTurnRef.current;
    const currentStreamingPlan = streamingSpeechStateRef.current;
    const action = selectLiveVoicePostSpeechAction({
      streamingEnabled: FEATURE_LIVE_VOICE_STREAMING_SPEECH,
      responseInProgress: isProcessing || isThinking,
      responseObserved: currentTurn?.responseObserved ?? false,
      currentTurnResponseEpoch: currentTurn?.responseEpoch ?? null,
      plannerResponseEpoch: currentStreamingPlan.responseEpoch,
      plannerMessageId: currentStreamingPlan.messageId,
      plannerMode: currentStreamingPlan.mode,
      status: currentSnapshot.status,
      pendingSpeechCount: currentSnapshot.pendingSpeechCount,
      activeSpeechKey: currentSnapshot.activeSpeechKey,
      resumeRequested: resumeListeningAfterSpeechRef.current,
    });
    if (action === 'mark-thinking' && currentTurn) {
      core.markThinking(currentTurn.responseEpoch);
      return;
    }
    if (action !== 'begin-capture') return;
    resumeListeningAfterSpeechRef.current = false;
    beginCapture();
  }, [active, beginCapture, core, isProcessing, isThinking, snapshot.activeSpeechKey, snapshot.pendingSpeechCount, snapshot.status]);

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
    routeLabel: integratedP1Route?.routeLabel,
    onEnable: enableLiveVoice,
    onExit: exitLiveVoice,
    onPrimaryAction: handlePrimaryAction,
  };
}
