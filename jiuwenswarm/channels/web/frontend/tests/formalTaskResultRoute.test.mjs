import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FORMAL_TASK_RESULT_METHOD,
  ProductFormalTaskResultOwner,
  parseFormalTaskResultResponse,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/formalTaskResultRoute.js';

function envelope(requestId, availability, taskResult = null, reason = `TASK_RESULT_${availability.toUpperCase()}`) {
  return {
    request_id: requestId,
    ok: true,
    result: {
      task_id: 'task-current-1',
      availability,
      reason,
      task_result: taskResult,
    },
    error: null,
  };
}

function availableResult(changes = {}) {
  return {
    task_id: 'task-current-1',
    attempt_id: 'attempt-current-1',
    source_event_id: 'executor-event-itinerary-1',
    result_text: '第二天最早的固定安排是 08:30 参观博物馆。',
    artifacts: [{ relative_path: 'itinerary.md', sha256: 'a'.repeat(64) }],
    completed_at: '2030-01-01T00:00:00Z',
    ...changes,
  };
}

test('reads available result through the independent closed method', async () => {
  const calls = [];
  const owner = new ProductFormalTaskResultOwner({
    enabled: true,
    request_id: () => 'request-result-1',
    request: async (method, params, requestId) => {
      calls.push({ method, params, requestId });
      return envelope(requestId, 'available', availableResult(), 'TASK_RESULT_AVAILABLE');
    },
  });

  const receipt = await owner.read({
    auth_token: 'opaque-token',
    session_id: 'session-product',
    task_id: 'task-current-1',
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, FORMAL_TASK_RESULT_METHOD);
  assert.deepEqual(calls[0].params, {
    auth_token: 'opaque-token',
    session_id: 'session-product',
    task_id: 'task-current-1',
  });
  assert.equal(receipt.availability, 'available');
  assert.equal(receipt.retryable, false);
  assert.equal(receipt.task_result.artifacts[0].relative_path, 'itinerary.md');
  assert.match(receipt.task_result.result_text, /08:30/);
});

test('not_ready is retryable while unavailable is stable and exposes no result', () => {
  const notReady = parseFormalTaskResultResponse(
    envelope('request-not-ready', 'not_ready', null, 'TASK_RESULT_NOT_READY'),
    'request-not-ready',
    'task-current-1',
  );
  const unavailable = parseFormalTaskResultResponse(
    envelope('request-unavailable', 'unavailable', null, 'TASK_CANCELLED'),
    'request-unavailable',
    'task-current-1',
  );

  assert.equal(notReady.retryable, true);
  assert.equal(notReady.task_result, null);
  assert.equal(unavailable.retryable, false);
  assert.equal(unavailable.task_result, null);
});

test('closed parser rejects unsafe paths, oversized text, target mismatch and unavailable content', () => {
  for (const invalid of [
    availableResult({ artifacts: [] }),
    availableResult({ artifacts: [{ relative_path: '../secret.txt', sha256: 'a'.repeat(64) }] }),
    availableResult({ artifacts: [{ relative_path: 'C:/secret.txt', sha256: 'a'.repeat(64) }] }),
    availableResult({ artifacts: [{ relative_path: '\\\\server\\share.txt', sha256: 'a'.repeat(64) }] }),
    availableResult({ artifacts: [{ relative_path: 'folder/../secret.txt', sha256: 'a'.repeat(64) }] }),
    availableResult({ result_text: 'unsafe\0result' }),
    availableResult({ result_text: 'x'.repeat(32_769) }),
    availableResult({ task_id: 'task-other' }),
  ]) {
    assert.throws(
      () => parseFormalTaskResultResponse(
        envelope('request-invalid', 'available', invalid, 'TASK_RESULT_AVAILABLE'),
        'request-invalid',
        'task-current-1',
      ),
      /invalid|mismatch|oversized/,
    );
  }
  assert.throws(
    () => parseFormalTaskResultResponse(
      envelope('request-leak', 'unavailable', availableResult(), 'TASK_FAILED'),
      'request-leak',
      'task-current-1',
    ),
    /must not expose/,
  );
});

test('result parser counts Unicode scalars like Python and rejects lone surrogates', () => {
  const astral = availableResult({
    task_id: '😀'.repeat(256),
    result_text: '😀'.repeat(20_000),
    artifacts: [{ relative_path: `${'😀'.repeat(300)}.md`, sha256: 'b'.repeat(64) }],
  });
  const accepted = parseFormalTaskResultResponse(
    {
      ...envelope('request-astral', 'available', astral, 'TASK_RESULT_AVAILABLE'),
      result: {
        ...envelope('request-astral', 'available', astral, 'TASK_RESULT_AVAILABLE').result,
        task_id: astral.task_id,
      },
    },
    'request-astral',
    astral.task_id,
  );
  assert.equal([...accepted.task_result.result_text].length, 20_000);
  assert.equal([...accepted.task_result.artifacts[0].relative_path].length, 303);

  for (const invalid of [
    availableResult({ result_text: 'bad\ud800text' }),
    availableResult({ artifacts: [{ relative_path: 'bad\udc00.md', sha256: 'a'.repeat(64) }] }),
    availableResult({ attempt_id: 'bad\ud800' }),
  ]) {
    assert.throws(
      () => parseFormalTaskResultResponse(
        envelope('request-invalid-scalar', 'available', invalid, 'TASK_RESULT_AVAILABLE'),
        'request-invalid-scalar',
        'task-current-1',
      ),
      /invalid/,
    );
  }
  assert.throws(
    () => parseFormalTaskResultResponse(
      envelope('request-invalid-reason', 'not_ready', null, 'bad\ud800'),
      'request-invalid-reason',
      'task-current-1',
    ),
    /invalid/,
  );
});

test('result parser rejects normalized-but-invalid UTC calendar timestamps', () => {
  for (const completed_at of [
    '0000-01-01T00:00:00Z',
    '2030-02-29T00:00:00Z',
    '2030-02-31T00:00:00Z',
    '2030-04-31T00:00:00Z',
    '2030-01-01T24:00:00Z',
    '2030-01-01T00:60:00Z',
    '2030-01-01T00:00:60Z',
  ]) {
    assert.throws(
      () => parseFormalTaskResultResponse(
        envelope(
          'request-invalid-calendar',
          'available',
          availableResult({ completed_at }),
          'TASK_RESULT_AVAILABLE',
        ),
        'request-invalid-calendar',
        'task-current-1',
      ),
      /completed_at is invalid/,
    );
  }
  const leap = parseFormalTaskResultResponse(
    envelope(
      'request-leap-calendar',
      'available',
      availableResult({ completed_at: '2032-02-29T23:59:59.123456Z' }),
      'TASK_RESULT_AVAILABLE',
    ),
    'request-leap-calendar',
    'task-current-1',
  );
  assert.equal(leap.task_result.completed_at, '2032-02-29T23:59:59.123456Z');
});

test('request binding and single in-flight owner fail closed', async () => {
  let resolveRequest;
  const owner = new ProductFormalTaskResultOwner({
    enabled: true,
    request_id: () => 'request-pending',
    request: () => new Promise(resolve => { resolveRequest = resolve; }),
  });
  const pending = owner.read({ auth_token: 'token', session_id: 'session-product', task_id: 'task-current-1' });
  await assert.rejects(
    owner.read({ auth_token: 'token', session_id: 'session-product', task_id: 'task-current-1' }),
    /already in progress/,
  );
  resolveRequest(envelope('request-pending', 'not_ready', null, 'TASK_RESULT_NOT_READY'));
  await pending;

  assert.throws(
    () => parseFormalTaskResultResponse(
      envelope('request-server', 'not_ready', null, 'TASK_RESULT_NOT_READY'),
      'request-client',
      'task-current-1',
    ),
    /mismatched/,
  );
});

test('close fences a late result and the owner remains closed', async () => {
  let resolveRequest;
  const owner = new ProductFormalTaskResultOwner({
    enabled: true,
    request_id: () => 'request-close-race',
    request: () => new Promise(resolve => { resolveRequest = resolve; }),
  });
  const pending = owner.read({
    auth_token: 'token',
    session_id: 'session-product',
    task_id: 'task-current-1',
  });

  assert.equal(owner.snapshot().status, 'reading');
  assert.equal(owner.close().status, 'closed');
  resolveRequest(envelope(
    'request-close-race',
    'available',
    availableResult(),
    'TASK_RESULT_AVAILABLE',
  ));

  await assert.rejects(pending, /closed/);
  assert.deepEqual(owner.snapshot(), {
    status: 'closed',
    task_id: null,
    receipt: null,
    reason: 'OWNER_CLOSED',
  });
  await assert.rejects(
    owner.read({
      auth_token: 'token',
      session_id: 'session-product',
      task_id: 'task-current-1',
    }),
    /closed/,
  );
});
