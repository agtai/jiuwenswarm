import assert from 'node:assert/strict';
import test from 'node:test';

import {
  BrowserSpeechRecognitionAdapter,
  BrowserSpeechRecognitionAdapterViolation,
  BrowserSpeechSynthesisAdapter,
  BrowserSpeechSynthesisAdapterViolation,
  createIntegratedP1Route,
} from '../node_modules/.cache/live-voice-browser-adapters/integratedP1Route.mjs';

function synthesisEnvironment(available = true) {
  const utterances = [];
  let cancelCount = 0;
  return {
    environment: {
      available,
      createUtterance(text) {
        const utterance = {
          text,
          lang: '',
          rate: 0,
          pitch: 0,
          volume: 0,
          voice: null,
          onstart: null,
          onend: null,
          onerror: null,
        };
        utterances.push(utterance);
        return utterance;
      },
      getVoices: () => [],
      speak: () => {},
      cancel: () => {
        cancelCount += 1;
      },
    },
    utterances,
    cancelCount: () => cancelCount,
  };
}

const first = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 0 });
const second = Object.freeze({ interaction_id: 'interaction-1', response_id: 'response-2', response_generation: 1 });

test('recognition observations preserve fallback provenance and never commit a turn', () => {
  const adapter = new BrowserSpeechRecognitionAdapter();
  const capture = adapter.begin('capture-1');
  const partial = adapter.observe(capture, 'hello', false);
  const final = adapter.observe(capture, 'hello world', true);
  assert.equal(partial.kind, 'partial');
  assert.equal(final.kind, 'final');
  assert.equal(final.confidence, null);
  assert.equal(final.commits_turn, false);
  assert.equal(final.provider.implementation_class, 'fallback');
  assert.equal(final.provider.fallback_from, 'formal-speech-recognition-port');
  assert.deepEqual([partial.seq, final.seq], [0, 1]);
});

test('replacement capture fences stale recognition callbacks', () => {
  const adapter = new BrowserSpeechRecognitionAdapter();
  const stale = adapter.begin('capture-1');
  const current = adapter.begin('capture-1');
  assert.equal(adapter.observe(stale, 'stale', true), null);
  assert.equal(adapter.finish(stale), false);
  assert.equal(adapter.observe(current, 'current', true).display_text, 'current');
  assert.equal(adapter.finish(current), true);
  assert.equal(adapter.observe(current, 'late', true), null);
});

test('empty Browser observations are no-ops and do not consume sequence', () => {
  const adapter = new BrowserSpeechRecognitionAdapter();
  const capture = adapter.begin('capture-1');
  assert.equal(adapter.observe(capture, '', false), null);
  assert.equal(adapter.observe(capture, '   ', true), null);
  assert.equal(adapter.observe(capture, 'current', false).seq, 0);
  assert.equal(adapter.finish(capture), true);
});

test('recognition capability makes unsupported streaming and cursor explicit', () => {
  const adapter = new BrowserSpeechRecognitionAdapter();
  assert.equal(adapter.capability.batch, true);
  assert.equal(adapter.capability.streaming, false);
  assert.equal(adapter.capability.hypothesis_cursor, false);
  assert.equal(adapter.capability.provider_final_is_turn_commit, false);
  assert.throws(
    () => new BrowserSpeechRecognitionAdapter({ available: false }).begin('capture-1'),
    error => error instanceof BrowserSpeechRecognitionAdapterViolation && error.reason === 'BROWSER_RECOGNITION_UNAVAILABLE'
  );
});

test('synthesis replacement drops stale callbacks and keeps only the current response', () => {
  const fake = synthesisEnvironment();
  const adapter = new BrowserSpeechSynthesisAdapter(fake.environment);
  const calls = [];
  adapter.play(
    { response: first, spoken_text: 'first' },
    {
      onStart: () => calls.push('first-start'),
      onEnd: () => calls.push('first-end'),
      onError: () => calls.push('first-error'),
    }
  );
  const staleStart = fake.utterances[0].onstart;
  const staleEnd = fake.utterances[0].onend;
  adapter.play(
    { response: second, spoken_text: 'second' },
    {
      onStart: () => calls.push('second-start'),
      onEnd: () => calls.push('second-end'),
      onError: () => calls.push('second-error'),
    }
  );
  staleStart();
  staleEnd();
  fake.utterances[1].onstart();
  fake.utterances[1].onend();
  assert.deepEqual(calls, ['second-start', 'second-end']);
  assert.equal(fake.cancelCount(), 1);
});

test('wrong-response stop has zero playback effect', () => {
  const fake = synthesisEnvironment();
  const adapter = new BrowserSpeechSynthesisAdapter(fake.environment);
  let ended = 0;
  adapter.play({ response: first, spoken_text: 'first' }, { onStart: () => {}, onEnd: () => (ended += 1), onError: () => {} });
  assert.equal(adapter.stop(second), false);
  assert.equal(fake.cancelCount(), 0);
  fake.utterances[0].onend();
  assert.equal(ended, 1);
});

test('synthesis capability exposes batch-only fallback and unavailable failure', () => {
  const fake = synthesisEnvironment();
  const adapter = new BrowserSpeechSynthesisAdapter(fake.environment);
  assert.equal(adapter.capability.batch, true);
  assert.equal(adapter.capability.streaming, false);
  assert.equal(adapter.capability.audio_chunk_cursor, false);
  assert.equal(adapter.capability.provider.implementation_class, 'fallback');
  const unavailable = new BrowserSpeechSynthesisAdapter(synthesisEnvironment(false).environment);
  assert.throws(
    () => unavailable.play({ response: first, spoken_text: 'text' }, { onStart: () => {}, onEnd: () => {}, onError: () => {} }),
    error => error instanceof BrowserSpeechSynthesisAdapterViolation && error.reason === 'BROWSER_SYNTHESIS_UNAVAILABLE'
  );
});

test('integrated route reports truthful owners, classes, and unsupported cursor features', () => {
  const fake = synthesisEnvironment();
  const route = createIntegratedP1Route({
    correlationId: 'correlation-1',
    observedAt: '2026-08-04T08:00:00Z',
    recognitionAvailable: true,
    synthesisEnvironment: fake.environment,
  });
  assert.equal(route.routeLabel, 'P1 · Browser Speech · fallback');
  assert.deepEqual(route.routeTelemetry(), []);
  route.beginRecognition();
  assert.equal(route.observeRecognition('partial', false).commits_turn, false);
  assert.equal(route.finishRecognition(), true);
  route.speechPlayer.play('answer', { onStart: () => {}, onEnd: () => {}, onError: () => {} });
  assert.deepEqual(
    route.routeTelemetry().map(item => [item.segment_id, item.implementation_class, item.owner_module]),
    [
      ['p1.browser_recognition', 'fallback', 'formal.adapters.browserSpeechRecognitionAdapter'],
      ['p1.browser_synthesis', 'fallback', 'formal.adapters.browserSpeechSynthesisAdapter'],
    ]
  );
  assert.deepEqual(route.capabilities(), {
    recognition_streaming: false,
    recognition_hypothesis_cursor: false,
    synthesis_streaming: false,
    synthesis_audio_chunk_cursor: false,
  });
});

test('integrated route labels unavailable Browser paths as unsupported', () => {
  const route = createIntegratedP1Route({
    correlationId: 'correlation-2',
    observedAt: '2026-08-04T08:00:00Z',
    recognitionAvailable: false,
    synthesisEnvironment: synthesisEnvironment(false).environment,
  });
  assert.equal(route.routeLabel, 'P1 · Browser Speech · unsupported');
  assert.deepEqual(route.routeTelemetry(), []);
  assert.throws(
    () => route.beginRecognition(),
    error => error instanceof BrowserSpeechRecognitionAdapterViolation && error.reason === 'BROWSER_RECOGNITION_UNAVAILABLE'
  );
  assert.throws(
    () => route.speechPlayer.play('text', { onStart: () => {}, onEnd: () => {}, onError: () => {} }),
    error => error instanceof BrowserSpeechSynthesisAdapterViolation && error.reason === 'BROWSER_SYNTHESIS_UNAVAILABLE'
  );
  assert.deepEqual(
    route.routeTelemetry().map(item => [item.implementation_class, item.safe_reason]),
    [
      ['unsupported', 'BROWSER_RECOGNITION_UNAVAILABLE'],
      ['unsupported', 'BROWSER_SYNTHESIS_UNAVAILABLE'],
    ]
  );
});
