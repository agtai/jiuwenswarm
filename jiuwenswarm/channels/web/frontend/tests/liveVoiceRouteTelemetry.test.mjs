import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CONTRACT_VERSION,
  ROUTE_CLASSES,
  RouteTelemetryViolation,
  createRouteTelemetryLedger,
  createRouteTelemetryRecord,
} from '../node_modules/.cache/live-voice-route-telemetry/features/live-voice/formal/liveVoiceRouteTelemetry.js';

function validInput(overrides = {}) {
  return {
    segment_id: 'p1.capture',
    implementation_class: 'formal',
    owner_module: 'speech.sr',
    capability_provider: 'browser-speech',
    contract_version: CONTRACT_VERSION,
    correlation_id: 'corr-1',
    observed_at: '2026-08-04T08:00:00Z',
    safe_reason: null,
    ...overrides,
  };
}

function rejectsWith(input, reason) {
  assert.throws(
    () => createRouteTelemetryRecord(input),
    err => err instanceof RouteTelemetryViolation && err.reason === reason
  );
}

test('formal record is immutable and keeps exact fields', () => {
  const record = createRouteTelemetryRecord(validInput());
  assert.deepEqual(record, {
    segment_id: 'p1.capture',
    implementation_class: 'formal',
    owner_module: 'speech.sr',
    capability_provider: 'browser-speech',
    contract_version: CONTRACT_VERSION,
    correlation_id: 'corr-1',
    observed_at: '2026-08-04T08:00:00Z',
    safe_reason: null,
  });
  assert.equal(Object.isFrozen(record), true);
  assert.throws(() => {
    record.segment_id = 'mutated';
  }, TypeError);
  assert.equal(record.segment_id, 'p1.capture');
});

test('ledger stores in order and is queryable by segment', () => {
  const ledger = createRouteTelemetryLedger();
  const first = createRouteTelemetryRecord(validInput());
  const second = createRouteTelemetryRecord(
    validInput({
      segment_id: 'p2.commit',
      implementation_class: 'fallback',
      contract_version: null,
      safe_reason: 'browser speech fallback',
    })
  );
  const third = createRouteTelemetryRecord(validInput({ segment_id: 'p1.capture', correlation_id: 'corr-3' }));

  assert.equal(ledger.add(first), true);
  assert.equal(ledger.add(second), true);
  assert.equal(ledger.add(third), true);
  assert.equal(ledger.size(), 3);
  assert.deepEqual(ledger.list(), [first, second, third]);
  assert.deepEqual(ledger.queryBySegment('p1.capture'), [first, third]);

  const listCopy = ledger.list();
  listCopy.push(createRouteTelemetryRecord(validInput({ segment_id: 'p9' })));
  const queryCopy = ledger.queryBySegment('p1.capture');
  queryCopy.length = 0;
  assert.equal(ledger.size(), 3);
  assert.deepEqual(ledger.queryBySegment('p1.capture'), [first, third]);
});

test('missing formal owner, provider, or contract version becomes unknown', () => {
  const cases = [
    {
      input: validInput({ owner_module: null }),
      expected_reason: 'MISSING_FORMAL_PROVENANCE',
    },
    {
      input: validInput({ capability_provider: null }),
      expected_reason: 'MISSING_FORMAL_PROVENANCE',
    },
    {
      input: validInput({ contract_version: null }),
      expected_reason: 'MISSING_FORMAL_PROVENANCE',
    },
    {
      input: validInput({ contract_version: 'live-voice.contract.v1' }),
      expected_reason: 'MISSING_FORMAL_PROVENANCE',
    },
    {
      input: validInput({
        implementation_class: 'fallback',
        contract_version: null,
        owner_module: null,
      }),
      expected_reason: 'MISSING_OWNER_MODULE',
    },
    {
      input: validInput({
        implementation_class: 'fallback',
        contract_version: null,
        owner_module: '   ',
      }),
      expected_reason: 'MISSING_OWNER_MODULE',
    },
  ];
  for (const scenario of cases) {
    const record = createRouteTelemetryRecord(scenario.input);
    assert.equal(record.implementation_class, 'unknown');
    assert.equal(record.safe_reason, scenario.expected_reason);
  }
});

test('fallback, substitute, unsupported, and unknown stay visible', () => {
  const fallback = createRouteTelemetryRecord(
    validInput({
      segment_id: 'p2.commit',
      implementation_class: 'fallback',
      contract_version: null,
      safe_reason: 'browser speech fallback',
    })
  );
  assert.equal(fallback.implementation_class, 'fallback');
  assert.equal(fallback.safe_reason, 'browser speech fallback');

  const substitute = createRouteTelemetryRecord(
    validInput({
      segment_id: 'p3.agent',
      implementation_class: 'demo_substitute',
      contract_version: null,
      safe_reason: 'demo substitute until TC-B lands',
    })
  );
  assert.equal(substitute.implementation_class, 'demo_substitute');
  assert.equal(substitute.safe_reason, 'demo substitute until TC-B lands');

  const unsupported = createRouteTelemetryRecord(
    validInput({
      segment_id: 'p4.provider',
      implementation_class: 'unsupported',
      contract_version: null,
      safe_reason: 'no streaming provider selected',
    })
  );
  assert.equal(unsupported.implementation_class, 'unsupported');

  const unknown = createRouteTelemetryRecord(
    validInput({
      segment_id: 'p5.unknown',
      implementation_class: 'unknown',
      contract_version: null,
      safe_reason: 'route facts unavailable',
    })
  );
  assert.equal(unknown.implementation_class, 'unknown');
  assert.equal(unknown.safe_reason, 'route facts unavailable');
});

test('every non-formal class requires a non-empty safe reason', () => {
  for (const implementation_class of ['fallback', 'demo_substitute', 'unsupported', 'unknown']) {
    for (const safe_reason of [null, '', '   ']) {
      rejectsWith(validInput({ implementation_class, contract_version: null, safe_reason }), 'NON_FORMAL_REASON_REQUIRED');
    }
  }
});

test('route class vocabulary cannot be mutated at runtime', () => {
  assert.equal(Object.isFrozen(ROUTE_CLASSES), true);
  assert.throws(() => ROUTE_CLASSES.push('production'), TypeError);
  rejectsWith(validInput({ implementation_class: 'production' }), 'INVALID_ROUTE_CLASS');
});

test('invalid class and segment reject with stable reasons', () => {
  rejectsWith(validInput({ implementation_class: 'production' }), 'INVALID_ROUTE_CLASS');
  rejectsWith(validInput({ segment_id: '' }), 'INVALID_REQUIRED_TEXT');
  rejectsWith(validInput({ segment_id: '   ' }), 'INVALID_REQUIRED_TEXT');
  rejectsWith(validInput({ correlation_id: '' }), 'INVALID_REQUIRED_TEXT');
});

test('invalid timestamps reject with stable reasons', () => {
  for (const observed_at of ['2026-08-04', '2026-08-04T08:00:00+00:00', '2026-02-30T08:00:00Z', '2026-08-04T24:00:00Z', 'not-a-time']) {
    rejectsWith(validInput({ observed_at }), 'INVALID_UTC_TIMESTAMP');
  }
  const parsed = createRouteTelemetryRecord(validInput({ observed_at: '2024-02-29T08:00:00.123Z' }));
  assert.equal(parsed.observed_at, '2024-02-29T08:00:00.123Z');
});

test('formal route with a reason rejects', () => {
  rejectsWith(validInput({ safe_reason: 'should not be formal' }), 'FORMAL_REASON_FORBIDDEN');
});

test('unknown fields and non-plain inputs reject', () => {
  rejectsWith(validInput({ extra: true }), 'UNKNOWN_FIELD');
  rejectsWith(null, 'INVALID_JSON_OBJECT');
  rejectsWith([], 'INVALID_JSON_OBJECT');
  rejectsWith(new Date(), 'INVALID_JSON_OBJECT');
  rejectsWith(Object.assign(Object.create({ owner_module: 'inherited' }), validInput()), 'INVALID_JSON_OBJECT');
  rejectsWith(JSON.parse('{"__proto__":{"privileged":true}}'), 'UNKNOWN_FIELD');
  rejectsWith(validInput({ segment_id: '\ud800' }), 'INVALID_UNICODE_SCALAR');
});

test('accessor and symbol properties reject', () => {
  const withAccessor = validInput();
  Object.defineProperty(withAccessor, 'owner_module', {
    get: () => 'speech.sr',
    enumerable: true,
  });
  rejectsWith(withAccessor, 'INVALID_OBJECT_PROPERTY');

  const withSymbol = validInput();
  withSymbol[Symbol('hidden')] = true;
  rejectsWith(withSymbol, 'INVALID_OBJECT_KEY');
});

test('ledger re-parses raw inputs and never stores forged records', () => {
  const ledger = createRouteTelemetryLedger();
  const forged = Object.freeze({
    segment_id: 'p1.capture',
    implementation_class: 'formal',
    owner_module: null,
    capability_provider: null,
    contract_version: CONTRACT_VERSION,
    correlation_id: 'corr-forged',
    observed_at: '2026-08-04T08:00:00Z',
    safe_reason: null,
  });
  assert.equal(ledger.add(forged), true);
  const stored = ledger.list()[0];
  assert.equal(stored.implementation_class, 'unknown');
  assert.equal(stored.safe_reason, 'MISSING_FORMAL_PROVENANCE');
  assert.equal(Object.isFrozen(stored), true);

  assert.equal(ledger.add(validInput({ segment_id: 'p1.capture' })), true);
  assert.equal(ledger.size(), 2);
});

test('disabled ledger creates no records and no effects', () => {
  const ledger = createRouteTelemetryLedger({ enabled: false });
  const record = createRouteTelemetryRecord(validInput());
  assert.equal(ledger.enabled, false);
  assert.equal(ledger.add(record), false);
  assert.equal(ledger.size(), 0);
  assert.deepEqual(ledger.list(), []);
  assert.deepEqual(ledger.queryBySegment('p1.capture'), []);
});

test('non-string optional fields reject instead of being coerced', () => {
  rejectsWith(validInput({ owner_module: 123 }), 'INVALID_TEXT_TYPE');
  rejectsWith(validInput({ capability_provider: {} }), 'INVALID_TEXT_TYPE');
  rejectsWith(validInput({ contract_version: 1 }), 'INVALID_TEXT_TYPE');
  rejectsWith(validInput({ safe_reason: 42 }), 'INVALID_TEXT_TYPE');
});

test('ledger options reject non-boolean enabled', () => {
  assert.throws(
    () => createRouteTelemetryLedger({ enabled: 'yes' }),
    err => err instanceof RouteTelemetryViolation && err.reason === 'INVALID_BOOLEAN'
  );
});

test('ledger add rejects invalid records and never stores them', () => {
  const ledger = createRouteTelemetryLedger();
  assert.throws(
    () => ledger.add(validInput({ implementation_class: 'production' })),
    err => err instanceof RouteTelemetryViolation && err.reason === 'INVALID_ROUTE_CLASS'
  );
  assert.equal(ledger.size(), 0);
});

test('later mutation of the source input never changes the record', () => {
  const source = validInput();
  const record = createRouteTelemetryRecord(source);
  source.segment_id = 'mutated';
  source.safe_reason = 'injected';
  assert.equal(record.segment_id, 'p1.capture');
  assert.equal(record.safe_reason, null);
  assert.equal(Object.isFrozen(record), true);
});
