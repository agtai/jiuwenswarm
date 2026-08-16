import assert from 'node:assert/strict';
import test from 'node:test';

import {
  PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD,
  ProductUnifiedCommittedInputOwner,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/unifiedCommittedInputOwner.js';

const binding = Object.freeze({
  session_id: 'session-1',
  correlation_id: 'correlation-1',
  interaction_id: 'interaction-1',
  activation_id: 'activation-1',
  activation_generation: 3,
});
function finalInput(overrides = {}) {
  return {
    request_id: 'request-final-1',
    commit_id: 'commit-final-1',
    turn_id: 'turn-final-1',
    committed_at: '2030-01-01T00:00:00Z',
    text: '帮我根据这些要求制定三天的行程。',
    voice_commit_receipt: 'opaque-gateway-speech-receipt',
    ...overrides,
  };
}
function accepted(requestId, overrides = {}) {
  return {
    request_id: requestId,
    ok: true,
    result: {
      status: 'authoritative_presentation_accepted',
      response: {
        interaction_id: binding.interaction_id,
        response_id: `response-${requestId}`,
        response_generation: 1,
      },
    },
    error: null,
    ...overrides,
  };
}
function roundAccepted(requestId, input = finalInput()) {
  return {
    request_id: requestId,
    ok: true,
    result: {
      status: 'round_accepted',
      ...binding,
      turn_id: input.turn_id,
      commit_id: input.commit_id,
      request_id: `agent-${requestId}`,
      round_id: `round-${requestId}`,
      response: {
        interaction_id: binding.interaction_id,
        response_id: `response-${requestId}`,
        response_generation: 1,
      },
    },
    error: null,
  };
}

test('submits only the closed authoritative-final shape', async () => {
  const calls = [];
  const owner = new ProductUnifiedCommittedInputOwner(async (method, params, requestId) => {
    calls.push({ method, params, requestId });
    return accepted(requestId);
  });

  await owner.submit(binding, finalInput());

  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, PRODUCT_UNIFIED_COMMITTED_INPUT_METHOD);
  assert.equal(calls[0].requestId, 'request-final-1');
  assert.deepEqual(calls[0].params, {
    ...binding,
    commit_id: 'commit-final-1',
    turn_id: 'turn-final-1',
    committed_at: '2030-01-01T00:00:00Z',
    text: '帮我根据这些要求制定三天的行程。',
    input_state: 'final',
    voice_commit_receipt: 'opaque-gateway-speech-receipt',
  });
  assert.equal('dispatch_target' in calls[0].params, false);
  assert.equal('critical_confirmation' in calls[0].params, false);
});

test('duplicate rendering shares one request and one completed replay', async () => {
  let resolve;
  const transport = new Promise(done => {
    resolve = done;
  });
  let calls = 0;
  const owner = new ProductUnifiedCommittedInputOwner(async (_method, _params, requestId) => {
    calls += 1;
    await transport;
    return accepted(requestId);
  });
  const input = finalInput();
  const first = owner.submit(binding, input);
  const duplicate = owner.submit(binding, input);
  assert.equal(owner.hasPending(), true);
  assert.equal(calls, 1);
  resolve();
  assert.deepEqual(await duplicate, await first);
  await owner.submit(binding, input);
  assert.equal(calls, 1);
  assert.equal(owner.hasPending(), false);
});

test('accepts the closed round_accepted union for dialogue and result-backed query', async () => {
  const input = finalInput({ request_id: 'request-round' });
  const owner = new ProductUnifiedCommittedInputOwner(async (_method, _params, requestId) => (
    roundAccepted(requestId, input)
  ));

  const result = await owner.submit(binding, input);

  assert.equal(result.result.status, 'round_accepted');
  assert.equal(result.result.session_id, binding.session_id);
  assert.equal(result.result.turn_id, input.turn_id);
  assert.equal(result.result.commit_id, input.commit_id);
});

test('a rebuilt owner accepts durable same-voice replay rebound to its outer request', async () => {
  let businessEffects = 0;
  let completed = false;
  const durableServer = async (_method, params, requestId) => {
    if (!completed) {
      businessEffects += 1;
      completed = true;
    }
    return accepted(requestId, {
      result: {
        status: 'authoritative_presentation_accepted',
        response: {
          interaction_id: binding.interaction_id,
          response_id: `response-durable-${params.commit_id}`,
          response_generation: 1,
        },
      },
    });
  };
  const firstOwner = new ProductUnifiedCommittedInputOwner(durableServer);
  const rebuiltOwner = new ProductUnifiedCommittedInputOwner(durableServer);

  const first = await firstOwner.submit(
    binding,
    finalInput({ request_id: 'request-before-rebuild' }),
  );
  const replay = await rebuiltOwner.submit(
    binding,
    finalInput({ request_id: 'request-after-rebuild' }),
  );

  assert.equal(first.request_id, 'request-before-rebuild');
  assert.equal(replay.request_id, 'request-after-rebuild');
  assert.deepEqual(replay.result, first.result);
  assert.equal(businessEffects, 1);
});

test('same owner rebinds a completed same-voice replay to the new outer request', async () => {
  let calls = 0;
  const owner = new ProductUnifiedCommittedInputOwner(async (_method, _params, requestId) => {
    calls += 1;
    return accepted(requestId);
  });

  const first = await owner.submit(
    binding,
    finalInput({ request_id: 'request-same-owner-first' }),
  );
  const replay = await owner.submit(
    binding,
    finalInput({ request_id: 'request-same-owner-alias' }),
  );

  assert.equal(first.request_id, 'request-same-owner-first');
  assert.equal(replay.request_id, 'request-same-owner-alias');
  assert.deepEqual(replay.result, first.result);
  assert.equal(calls, 1);
});

test('a different final cannot replace the unresolved voice identity', async () => {
  let resolve;
  const transport = new Promise(done => {
    resolve = done;
  });
  let calls = 0;
  const owner = new ProductUnifiedCommittedInputOwner(async (_method, _params, requestId) => {
    calls += 1;
    await transport;
    return accepted(requestId);
  });
  const first = owner.submit(binding, finalInput());
  await assert.rejects(
    owner.submit(
      binding,
      finalInput({
        request_id: 'request-final-2',
        commit_id: 'commit-final-2',
        turn_id: 'turn-final-2',
        text: '不同内容',
        voice_commit_receipt: 'different-receipt',
      }),
    ),
    /different authoritative final/,
  );
  assert.equal(calls, 1);
  resolve();
  await first;
});

test('enforces the backend Unicode scalar, character, and UTF-8 bounds', async () => {
  let calls = 0;
  const owner = new ProductUnifiedCommittedInputOwner(async (_method, _params, requestId) => {
    calls += 1;
    return accepted(requestId);
  });

  await owner.submit(binding, finalInput({ text: '😀'.repeat(8_192) }));
  assert.equal(calls, 1);
  assert.throws(
    () => owner.submit(binding, finalInput({ request_id: 'too-long', text: 'a'.repeat(8_193) })),
    /text is invalid/,
  );
  assert.throws(
    () => owner.submit(binding, finalInput({ request_id: 'bad-scalar', text: '\ud800' })),
    /text is invalid/,
  );
  assert.equal(calls, 1);
});

test('rejects malformed or open unified success envelopes before caching', async () => {
  const malformed = [
    accepted('request-final-1', { extra: true }),
    accepted('request-final-1', { error: { code: 'X', reason: 'X', message: 'X' } }),
    { request_id: 'request-final-1', ok: true, result: null, error: null },
    {
      request_id: 'request-final-1',
      ok: true,
      result: { status: 'accepted', response: accepted('x').result.response },
      error: null,
    },
    {
      request_id: 'request-final-1',
      ok: true,
      result: { ...accepted('x').result, extra: true },
      error: null,
    },
    {
      request_id: 'request-final-1',
      ok: true,
      result: {
        status: 'authoritative_presentation_accepted',
        response: { ...accepted('x').result.response, interaction_id: 'foreign-interaction' },
      },
      error: null,
    },
    {
      ...roundAccepted('request-final-1'),
      result: { ...roundAccepted('request-final-1').result, turn_id: 'foreign-turn' },
    },
  ];
  for (const response of malformed) {
    let calls = 0;
    const owner = new ProductUnifiedCommittedInputOwner(async () => {
      calls += 1;
      return response;
    });
    await assert.rejects(owner.submit(binding, finalInput()), /unified committed-input/);
    assert.equal(calls, 1);
    assert.equal(owner.hasPending(), false);
  }
});
