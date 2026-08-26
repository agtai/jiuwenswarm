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

test('synthesis bounds 128 exact response IDs behind a conservative owner-lifetime fence', () => {
  const fake = synthesisEnvironment();
  const adapter = new BrowserSpeechSynthesisAdapter(fake.environment);
  const callbacks = { onStart: () => {}, onEnd: () => {}, onError: () => {} };

  for (let generation = 0; generation < 2_000; generation += 1) {
    adapter.play(
      {
        response: {
          interaction_id: 'bounded-browser-owner',
          response_id: `bounded-response-${generation}`,
          response_generation: generation,
        },
        spoken_text: `answer-${generation}`,
      },
      callbacks
    );
  }

  const activeResponse = Object.freeze({
    interaction_id: 'bounded-browser-owner',
    response_id: 'bounded-response-1999',
    response_generation: 1_999,
  });
  const beforeReject = Object.freeze({ utterances: fake.utterances.length, cancels: fake.cancelCount() });
  assert.equal(adapter.isCurrent(activeResponse), true);
  assert.throws(
    () =>
      adapter.play(
        {
          response: {
            interaction_id: 'bounded-browser-owner',
            response_id: 'bounded-response-0',
            response_generation: 2_000,
          },
          spoken_text: 'retired replay',
        },
        callbacks
      ),
    error => error instanceof BrowserSpeechSynthesisAdapterViolation && error.reason === 'RESPONSE_ID_REUSED'
  );
  assert.deepEqual({ utterances: fake.utterances.length, cancels: fake.cancelCount() }, beforeReject);
  assert.equal(adapter.isCurrent(activeResponse), true);

  // This unused identity is a deterministic four-hash false positive only after
  // bounded-response-1871 retires at the exact 128-entry boundary. A 129-entry
  // exact ledger, or the old unbounded Set, admits it and causes playback effects.
  assert.throws(
    () =>
      adapter.play(
        {
          response: {
            interaction_id: 'bounded-browser-owner',
            response_id: 'unused-boundary-candidate-1420439',
            response_generation: 2_000,
          },
          spoken_text: 'conservative rejection',
        },
        callbacks
      ),
    error => error instanceof BrowserSpeechSynthesisAdapterViolation && error.reason === 'RESPONSE_ID_REUSED'
  );
  assert.deepEqual({ utterances: fake.utterances.length, cancels: fake.cancelCount() }, beforeReject);
  assert.equal(adapter.isCurrent(activeResponse), true);

  adapter.play(
    {
      response: {
        interaction_id: 'bounded-browser-owner',
        response_id: 'fresh-recovery-response',
        response_generation: 2_000,
      },
      spoken_text: 'retry with a fresh identity',
    },
    callbacks
  );
  assert.equal(fake.utterances.length, beforeReject.utterances + 1);

  const replacementFake = synthesisEnvironment();
  const replacementOwner = new BrowserSpeechSynthesisAdapter(replacementFake.environment);
  replacementOwner.play(
    {
      response: {
        interaction_id: 'replacement-browser-owner',
        response_id: 'unused-boundary-candidate-1420439',
        response_generation: 0,
      },
      spoken_text: 'new owner lifetime',
    },
    callbacks
  );
  assert.equal(replacementFake.utterances.length, 1);
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

test('integrated route retains only the latest recognition and synthesis telemetry slots', () => {
  const route = createIntegratedP1Route({
    correlationId: 'correlation-bounded-slots',
    observedAt: '2026-08-26T08:00:00Z',
    recognitionAvailable: true,
    synthesisEnvironment: synthesisEnvironment().environment,
  });

  route.beginRecognition();
  route.finishRecognition();
  route.speechPlayer.play('answer-0', { onStart: () => {}, onEnd: () => {}, onError: () => {} });
  const [firstRecognition, firstSynthesis] = route.routeTelemetry();

  for (let index = 1; index <= 256; index += 1) {
    route.beginRecognition();
    route.finishRecognition();
    route.speechPlayer.play(`answer-${index}`, { onStart: () => {}, onEnd: () => {}, onError: () => {} });
  }

  const telemetry = route.routeTelemetry();
  assert.equal(telemetry.length, 2);
  assert.deepEqual(
    telemetry.map(item => item.segment_id),
    ['p1.browser_recognition', 'p1.browser_synthesis']
  );
  assert.notStrictEqual(telemetry[0], firstRecognition);
  assert.notStrictEqual(telemetry[1], firstSynthesis);
});

test('integrated route telemetry uses fixed slot order and omits unobserved segments', () => {
  const synthesisOnly = createIntegratedP1Route({
    correlationId: 'correlation-synthesis-only',
    recognitionAvailable: true,
    synthesisEnvironment: synthesisEnvironment().environment,
  });
  synthesisOnly.speechPlayer.play('answer', { onStart: () => {}, onEnd: () => {}, onError: () => {} });
  assert.deepEqual(
    synthesisOnly.routeTelemetry().map(item => item.segment_id),
    ['p1.browser_synthesis']
  );

  const synthesisFirst = createIntegratedP1Route({
    correlationId: 'correlation-synthesis-first',
    recognitionAvailable: true,
    synthesisEnvironment: synthesisEnvironment().environment,
  });
  synthesisFirst.speechPlayer.play('answer', { onStart: () => {}, onEnd: () => {}, onError: () => {} });
  synthesisFirst.beginRecognition();
  assert.deepEqual(
    synthesisFirst.routeTelemetry().map(item => item.segment_id),
    ['p1.browser_recognition', 'p1.browser_synthesis']
  );

  const recognitionOnly = createIntegratedP1Route({
    correlationId: 'correlation-recognition-only',
    recognitionAvailable: true,
    synthesisEnvironment: synthesisEnvironment().environment,
  });
  recognitionOnly.beginRecognition();
  assert.deepEqual(
    recognitionOnly.routeTelemetry().map(item => item.segment_id),
    ['p1.browser_recognition']
  );
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
