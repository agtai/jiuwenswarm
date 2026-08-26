import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import {
  CANCEL_SCOPES,
  CANCEL_TARGET_SEGMENT_MATRIX,
  ERROR_CODES,
  EVENT_SEMANTIC_MATRIX,
  EVENT_NAMES,
  FAILURE_ERROR_MATRIX,
  FAILURE_SEGMENT_MATRIX,
  IDENTITY_POLICY,
  METRIC_DEFINITIONS,
  METRIC_SEMANTIC_MATRIX,
  OBSERVABILITY_SCHEMA_VERSION,
  OBSERVED_STATES,
  REASON_CODES,
  ROUTE_IMPLEMENTATION_CLASSES,
  SEGMENT_NAMES,
  SEGMENT_BINDING_MATRIX,
  TERMINAL_OUTCOMES,
  LiveVoiceObservabilityCollector,
  ObservabilityViolation,
  createBrowserAudioObservabilityObserver,
  createMetric,
  createObservation,
  createRouteDescriptor,
  createTraceBinding,
  observationFromRouteRecord,
  routeDescriptorFromRouteRecord,
} from '../node_modules/.cache/live-voice-observability/features/live-voice/formal/liveVoiceObservability.js';
import {
  CONTRACT_VERSION,
  createRouteTelemetryRecord,
} from '../node_modules/.cache/live-voice-observability/features/live-voice/formal/liveVoiceRouteTelemetry.js';

const fixture = JSON.parse(readFileSync(path.resolve(process.cwd(), '../../../../tests/fixtures/live_voice_observability_v1/contract.json'), 'utf8'));

function formalRoute(owner = 'runtime.conversation', provider = 'jiuwenswarm-runtime') {
  return {
    implementation_class: 'formal',
    owner_module: owner,
    capability_provider: provider,
    contract_version: CONTRACT_VERSION,
    reason_code: null,
  };
}

function nonFormalRoute(routeClass = 'fallback') {
  const reasons = {
    fallback: 'ROUTE_FALLBACK',
    demo_substitute: 'DEMO_SUBSTITUTE',
    unsupported: 'UNSUPPORTED_CAPABILITY',
    unknown: 'UNKNOWN_PROVENANCE',
  };
  return {
    implementation_class: routeClass,
    owner_module: routeClass === 'unknown' ? null : 'route.compatibility',
    capability_provider: null,
    contract_version: null,
    reason_code: reasons[routeClass],
  };
}

function observation(eventId, eventName, segmentName, overrides = {}) {
  const binding = { correlation_id: 'corr-journey' };
  if (segmentName === 'speech.capture' || segmentName === 'speech.recognition') binding.interaction_id = 'interaction-1';
  else if (['speech.synthesis', 'speech.playout', 'runtime.response', 'runtime.presentation'].includes(segmentName)) {
    Object.assign(binding, { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 1 });
  } else if (segmentName === 'runtime.turn') Object.assign(binding, { interaction_id: 'interaction-1', turn_id: 'turn-1' });
  else if (segmentName.startsWith('agent.')) binding.round_id = 'round-1';
  else if (segmentName.startsWith('task.')) {
    binding.task_id = 'task-1';
    if (segmentName === 'task.attempt') binding.attempt_id = 'attempt-1';
  }
  return {
    schema_version: OBSERVABILITY_SCHEMA_VERSION,
    event_id: eventId,
    event_name: eventName,
    segment_name: segmentName,
    observed_at: '2026-08-05T09:00:00Z',
    monotonic_ms: 1000,
    binding,
    route: formalRoute(),
    source_component: 'observability.test',
    ...overrides,
  };
}

function metric(measurementId, metricName, metricKind, unit, overrides = {}) {
  const binding = { correlation_id: 'corr-journey' };
  let segmentName = 'runtime.queue';
  const semanticDimensions = {};
  if (metricName === 'live_voice.segment_latency_ms') {
    Object.assign(binding, { interaction_id: 'interaction-1', turn_id: 'turn-1' });
    segmentName = 'runtime.turn';
    semanticDimensions.outcome = 'completed';
  } else if (metricName === 'live_voice.cancel_total') {
    binding.task_id = 'task-1';
    segmentName = 'task.command';
    semanticDimensions.reason_code = 'CANCEL_REQUESTED';
    semanticDimensions.cancel_scope = 'task.cancel';
  }
  if (metricName === 'live_voice.stale_fence_total') {
    Object.assign(binding, { interaction_id: 'interaction-1', response_id: 'response-1', response_generation: 1 });
    segmentName = 'runtime.presentation';
    semanticDimensions.reason_code = 'STALE_GENERATION';
    semanticDimensions.error_code = 'STALE';
  }
  if (metricName === 'live_voice.task_total') {
    binding.task_id = 'task-1';
    segmentName = 'task.progress';
    semanticDimensions.outcome = 'completed';
  }
  if (metricName === 'live_voice.failure_total') {
    binding.round_id = 'round-1';
    segmentName = 'agent.dispatch';
    semanticDimensions.reason_code = 'AGENT_FAILURE';
    semanticDimensions.error_code = 'INTERNAL';
  }
  if (metricName === 'live_voice.degradation_total') {
    segmentName = 'system.degradation';
    semanticDimensions.reason_code = 'DEGRADED';
  }
  return {
    schema_version: OBSERVABILITY_SCHEMA_VERSION,
    measurement_id: measurementId,
    metric_name: metricName,
    metric_kind: metricKind,
    unit,
    value: 1,
    observed_at: '2026-08-05T09:00:00Z',
    binding,
    route: formalRoute(),
    segment_name: segmentName,
    implementation_class: 'formal',
    ...semanticDimensions,
    ...overrides,
  };
}

function rejectsWith(factory, reason) {
  assert.throws(factory, error => error instanceof ObservabilityViolation && error.reason === reason);
}

test('TypeScript matches the shared observation and metric fixture', () => {
  const event = createObservation(fixture.observation);
  const measurement = createMetric(fixture.metric);

  assert.deepEqual(event, fixture.observation);
  assert.deepEqual(measurement, fixture.metric);
  assert.equal(Object.isFrozen(event), true);
  assert.equal(Object.isFrozen(event.binding), true);
  assert.equal(Object.isFrozen(event.route), true);
  assert.deepEqual(ROUTE_IMPLEMENTATION_CLASSES, fixture.vocabulary.route_classes);
  assert.deepEqual(CANCEL_SCOPES, fixture.vocabulary.cancel_scopes);
  assert.deepEqual(SEGMENT_NAMES, fixture.vocabulary.segments);
  assert.deepEqual(EVENT_NAMES, fixture.vocabulary.events);
  assert.deepEqual(OBSERVED_STATES, fixture.vocabulary.states);
  assert.deepEqual(TERMINAL_OUTCOMES, fixture.vocabulary.outcomes);
  assert.deepEqual(ERROR_CODES, fixture.vocabulary.error_codes);
  assert.deepEqual(REASON_CODES, fixture.vocabulary.reason_codes);
  assert.deepEqual(METRIC_DEFINITIONS, fixture.vocabulary.metrics);
  assert.deepEqual(EVENT_SEMANTIC_MATRIX, fixture.vocabulary.event_semantics);
  assert.deepEqual(METRIC_SEMANTIC_MATRIX, fixture.vocabulary.metric_semantics);
  assert.deepEqual(FAILURE_ERROR_MATRIX, fixture.vocabulary.failure_error_matrix);
  assert.deepEqual(FAILURE_SEGMENT_MATRIX, fixture.vocabulary.failure_segment_matrix);
  assert.deepEqual(SEGMENT_BINDING_MATRIX, fixture.vocabulary.segment_binding_matrix);
  assert.deepEqual(CANCEL_TARGET_SEGMENT_MATRIX, fixture.vocabulary.cancel_target_segment_matrix);
  assert.deepEqual(IDENTITY_POLICY, fixture.vocabulary.identity_policy);
});

function adversarialPayload(name) {
  if (name === 'capture_state_missing_state') {
    return ['observation', observation('bad-capture-state', 'speech.capture_state', 'speech.capture')];
  }
  if (name === 'completed_with_failure_truth') {
    return [
      'observation',
      observation('bad-completed', 'segment.completed', 'runtime.response', {
        outcome: 'failed',
        reason_code: 'AGENT_FAILURE',
        error_code: 'INTERNAL',
        duration_ms: 1,
      }),
    ];
  }
  if (name === 'outbox_wrong_segment_missing_binding_source') {
    return ['observation', observation('bad-outbox', 'task.dispatch_outbox_observed', 'speech.capture', { binding: { correlation_id: 'corr' } })];
  }
  if (name === 'segment_latency_with_failure_truth') {
    return [
      'metric',
      metric('bad-latency', 'live_voice.segment_latency_ms', 'histogram', 'milliseconds', {
        outcome: 'failed',
        reason_code: 'TASK_FAILURE',
        error_code: 'INTERNAL',
      }),
    ];
  }
  const [identity, safeSuffix] = {
    identity_url: ['https://example.invalid/trace', 'url'],
    identity_api_key: ['api_key=private', 'api'],
    identity_secret: ['corr-secret-private', 'marker'],
    identity_transcript: ['complete transcript text', 'text'],
  }[name];
  return ['observation', observation(`bad-identity-${safeSuffix}`, 'segment.started', 'runtime.response', { binding: { correlation_id: identity } })];
}

test('shared adversarial cases fail closed with zero sink effect', () => {
  const delivered = [];
  const collector = new LiveVoiceObservabilityCollector({
    observation_sink: value => delivered.push(value),
    metric_sink: value => delivered.push(value),
  });
  for (const caseRecord of fixture.vocabulary.adversarial_cases) {
    const [kind, payload] = adversarialPayload(caseRecord.name);
    rejectsWith(() => (kind === 'observation' ? createObservation(payload) : createMetric(payload)), caseRecord.reason);
    const accepted = kind === 'observation' ? collector.emitObservation(payload) : collector.emitMetric(payload);
    assert.equal(accepted, false);
  }
  assert.deepEqual(delivered, []);
  assert.deepEqual(collector.observations(), []);
  assert.deepEqual(collector.metrics(), []);
});

test('Task source rules require exact kind, identity, sequence, and state', () => {
  const delivered = [];
  const collector = new LiveVoiceObservabilityCollector({ observation_sink: value => delivered.push(value) });
  const cases = [
    [
      observation('outbox-missing-source', 'task.dispatch_outbox_observed', 'task.queue', {
        binding: { correlation_id: 'corr', task_id: 'task-1', attempt_id: 'attempt-1' },
      }),
      'EVENT_FACT_REQUIRED',
    ],
    [
      observation('outbox-missing-target', 'task.dispatch_outbox_observed', 'task.queue', {
        binding: { correlation_id: 'corr' },
        source_record_id: 'outbox-1',
        source_seq: 1,
        state: 'pending',
      }),
      'SEMANTIC_TARGET_BINDING_REQUIRED',
    ],
    [
      observation('outbox-event-source', 'task.cancel_outbox_observed', 'task.queue', {
        binding: { correlation_id: 'corr', task_id: 'task-1', attempt_id: 'attempt-1' },
        source_event_id: 'event-1',
        source_occurred_at: '2026-08-05T09:00:00Z',
        source_seq: 1,
        state: 'pending',
      }),
      'EVENT_FACT_FORBIDDEN',
    ],
  ];
  for (const [payload, reason] of cases) {
    rejectsWith(() => createObservation(payload), reason);
    assert.equal(collector.emitObservation(payload), false);
  }
  assert.deepEqual(delivered, []);
});

test('metric matrix requires exact targets with zero sink effect', () => {
  const delivered = [];
  const collector = new LiveVoiceObservabilityCollector({ metric_sink: value => delivered.push(value) });
  const cases = [
    [metric('cancel-no-task', 'live_voice.cancel_total', 'counter', 'count', { binding: { correlation_id: 'corr' } }), 'CANCEL_TARGET_BINDING_REQUIRED'],
    [
      metric('fence-no-response', 'live_voice.stale_fence_total', 'counter', 'count', { binding: { correlation_id: 'corr' } }),
      'SEMANTIC_TARGET_BINDING_REQUIRED',
    ],
    [metric('task-no-task', 'live_voice.task_total', 'counter', 'count', { binding: { correlation_id: 'corr' } }), 'SEMANTIC_TARGET_BINDING_REQUIRED'],
    [metric('failure-no-round', 'live_voice.failure_total', 'counter', 'count', { binding: { correlation_id: 'corr' } }), 'FAILURE_TARGET_BINDING_REQUIRED'],
    [
      metric('agent-queue-no-round', 'live_voice.queue_depth', 'gauge', 'items', {
        binding: { correlation_id: 'corr' },
        segment_name: 'agent.queue',
      }),
      'SEMANTIC_TARGET_BINDING_REQUIRED',
    ],
  ];
  for (const [payload, reason] of cases) {
    rejectsWith(() => createMetric(payload), reason);
    assert.equal(collector.emitMetric(payload), false);
  }
  assert.deepEqual(delivered, []);
});

test('one journey correlates speech, runtime, Agent, and Task identities', () => {
  const collector = new LiveVoiceObservabilityCollector();
  const cases = [
    ['speech', 'speech.recognition', { correlation_id: 'corr-one', interaction_id: 'interaction-1', turn_id: 'turn-1' }],
    [
      'runtime',
      'runtime.response',
      {
        correlation_id: 'corr-one',
        interaction_id: 'interaction-1',
        turn_id: 'turn-1',
        response_id: 'response-1',
        response_generation: 3,
      },
    ],
    [
      'agent',
      'agent.dispatch',
      {
        correlation_id: 'corr-one',
        interaction_id: 'interaction-1',
        turn_id: 'turn-1',
        response_id: 'response-1',
        response_generation: 3,
        round_id: 'round-1',
      },
    ],
    [
      'task',
      'task.attempt',
      {
        correlation_id: 'corr-one',
        interaction_id: 'interaction-1',
        turn_id: 'turn-1',
        response_id: 'response-1',
        response_generation: 3,
        round_id: 'round-1',
        task_id: 'task-1',
        attempt_id: 'attempt-1',
      },
    ],
  ];

  for (const [eventId, segmentName, binding] of cases) {
    assert.equal(collector.emitObservation(observation(eventId, 'segment.started', segmentName, { binding })), true);
  }

  assert.deepEqual(
    collector.byCorrelation('corr-one').map(event => event.segment_name),
    cases.map(([, segment]) => segment)
  );
  assert.equal(collector.byCorrelation('other').length, 0);
  assert.equal(collector.observations()[3].binding.attempt_id, 'attempt-1');
});

test('route telemetry maps every implementation class without exporting safe_reason', () => {
  const reasonByClass = {
    fallback: 'ROUTE_FALLBACK',
    demo_substitute: 'DEMO_SUBSTITUTE',
    unsupported: 'UNSUPPORTED_CAPABILITY',
    unknown: 'UNKNOWN_PROVENANCE',
  };
  for (const routeClass of Object.keys(reasonByClass)) {
    const routeRecord = createRouteTelemetryRecord({
      segment_id: 'legacy.route',
      implementation_class: routeClass,
      owner_module: routeClass === 'unknown' ? null : 'formal.adapters.browserSpeechRecognitionAdapter',
      capability_provider: null,
      contract_version: null,
      correlation_id: 'corr-route',
      observed_at: '2026-08-05T09:00:00Z',
      safe_reason: 'Bearer secret-token and complete user text',
    });
    const route = routeDescriptorFromRouteRecord(routeRecord);
    const event = observationFromRouteRecord({
      record: routeRecord,
      event_id: `route-${routeClass}`,
      segment_name: 'route.fallback',
      monotonic_ms: 50,
      binding: { correlation_id: 'corr-route' },
    });
    assert.equal(route.implementation_class, routeClass);
    assert.equal(route.reason_code, reasonByClass[routeClass]);
    assert.equal(event.reason_code, reasonByClass[routeClass]);
    assert.equal(JSON.stringify(event).includes('secret-token'), false);
    assert.equal(JSON.stringify(event).includes('complete user text'), false);
  }
});

test('non-formal contract-version markers are closed before observability storage or sink delivery', () => {
  const delivered = [];
  const collector = new LiveVoiceObservabilityCollector({
    observation_sink: event => delivered.push(event),
  });
  const forbidden = [
    ['private-marker', 'private-token-marker'],
    ['blank-marker', ' '],
    ['over-bound-marker', 'v'.repeat(65)],
    ['overlong-marker', 'v'.repeat(200)],
  ];

  const results = forbidden.map(([suffix, contractVersion]) => [
    suffix,
    collector.emitObservation(
      observation(`route-${suffix}`, 'route.selected', 'route.fallback', {
        route: { ...nonFormalRoute(), contract_version: contractVersion },
        reason_code: 'ROUTE_FALLBACK',
      })
    ),
  ]);
  assert.deepEqual(
    {
      results,
      delivered: delivered.length,
      stored: collector.observations().length,
      rejected: collector.stats().rejected_observations,
    },
    {
      results: forbidden.map(([suffix]) => [suffix, false]),
      delivered: 0,
      stored: 0,
      rejected: forbidden.length,
    },
  );
});

test('non-formal contract-version accepts the exact stable-token bound', () => {
  const descriptor = createRouteDescriptor({
    ...nonFormalRoute(),
    contract_version: 'v'.repeat(64),
  });

  assert.equal(descriptor.contract_version, 'v'.repeat(64));
});

test('cancel, stale fence, queue, provider, Agent, Task, and degradation facts are closed', () => {
  const collector = new LiveVoiceObservabilityCollector();
  const binding = {
    correlation_id: 'corr-fault',
    interaction_id: 'interaction-1',
    response_id: 'response-1',
    response_generation: 9,
    round_id: 'round-1',
    task_id: 'task-1',
    attempt_id: 'attempt-1',
  };
  const cases = [
    observation('cancel', 'cancel.requested', 'runtime.response', {
      binding,
      reason_code: 'CANCEL_REQUESTED',
      cancel_scope: 'response.cancel',
    }),
    observation('cancel-unknown', 'cancel.result_unknown', 'runtime.response', {
      binding,
      outcome: 'unknown',
      reason_code: 'CANCEL_RESULT_UNKNOWN',
      error_code: 'RESULT_UNKNOWN',
      cancel_scope: 'response.cancel',
    }),
    observation('stale', 'fence.stale_dropped', 'runtime.presentation', {
      binding,
      reason_code: 'STALE_GENERATION',
      error_code: 'STALE',
    }),
    observation('queue', 'queue.pressure', 'agent.queue', {
      binding,
      reason_code: 'QUEUE_CAPACITY',
      queue_depth: 4,
      queue_capacity: 4,
    }),
    observation('provider', 'failure.observed', 'speech.recognition', {
      binding,
      reason_code: 'PROVIDER_FAILURE',
      error_code: 'UNAVAILABLE',
    }),
    observation('agent', 'failure.observed', 'agent.dispatch', {
      binding,
      reason_code: 'AGENT_FAILURE',
      error_code: 'INTERNAL',
    }),
    observation('task', 'failure.observed', 'task.attempt', {
      binding,
      reason_code: 'TASK_FAILURE',
      error_code: 'INTERNAL',
    }),
    observation('degraded', 'degradation.activated', 'system.degradation', {
      binding,
      route: nonFormalRoute(),
      reason_code: 'DEGRADED',
    }),
  ];
  for (const event of cases) assert.equal(collector.emitObservation(event), true);
  assert.deepEqual(
    new Set(collector.observations().map(event => event.reason_code)),
    new Set([
      'CANCEL_REQUESTED',
      'CANCEL_RESULT_UNKNOWN',
      'STALE_GENERATION',
      'QUEUE_CAPACITY',
      'PROVIDER_FAILURE',
      'AGENT_FAILURE',
      'TASK_FAILURE',
      'DEGRADED',
    ])
  );
});

test('each ACG cancel scope requires its exact target and rejects with zero sink effect', () => {
  const cases = [
    [
      'playback.stop',
      'speech.playout',
      {
        correlation_id: 'corr-cancel',
        interaction_id: 'interaction-1',
        response_id: 'response-1',
        response_generation: 1,
      },
    ],
    [
      'response.cancel',
      'runtime.response',
      {
        correlation_id: 'corr-cancel',
        interaction_id: 'interaction-1',
        response_id: 'response-1',
        response_generation: 1,
      },
    ],
    ['round.cancel', 'agent.progress', { correlation_id: 'corr-cancel', round_id: 'round-1' }],
    ['task.cancel', 'task.command', { correlation_id: 'corr-cancel', task_id: 'task-1' }],
  ];
  for (const [cancel_scope, segment_name, binding] of cases) {
    const delivered = [];
    const collector = new LiveVoiceObservabilityCollector({ observation_sink: event => delivered.push(event.event_id) });
    assert.equal(
      collector.emitObservation(
        observation(`accepted-${cancel_scope}`, 'cancel.requested', segment_name, {
          binding,
          reason_code: 'CANCEL_REQUESTED',
          cancel_scope,
        })
      ),
      true
    );
    assert.equal(
      collector.emitObservation(
        observation(`rejected-${cancel_scope}`, 'cancel.requested', segment_name, {
          binding: { correlation_id: 'corr-cancel' },
          reason_code: 'CANCEL_REQUESTED',
          cancel_scope,
        })
      ),
      false
    );
    assert.deepEqual(delivered, [`accepted-${cancel_scope}`]);
    assert.equal(collector.stats().rejected_observations, 1);
  }
});

test('event names reject misleading reason, queue, failure, and terminal facts', () => {
  rejectsWith(
    () =>
      createObservation(
        observation('bad-cancel', 'cancel.requested', 'runtime.response', {
          binding: {
            correlation_id: 'corr',
            interaction_id: 'interaction',
            response_id: 'response',
            response_generation: 1,
          },
          reason_code: 'AGENT_FAILURE',
          cancel_scope: 'response.cancel',
        })
      ),
    'EVENT_VALUE_MISMATCH'
  );
  rejectsWith(
    () =>
      createObservation(
        observation('bad-queue', 'queue.pressure', 'agent.queue', {
          reason_code: 'QUEUE_CAPACITY',
          queue_depth: 3,
          queue_capacity: 4,
        })
      ),
    'QUEUE_PRESSURE_INCOMPLETE'
  );
  rejectsWith(
    () =>
      createObservation(
        observation('bad-segment', 'segment.failed', 'agent.dispatch', {
          duration_ms: 1,
          reason_code: 'AGENT_FAILURE',
        })
      ),
    'EVENT_FACT_REQUIRED'
  );
  rejectsWith(
    () =>
      createObservation(
        observation('bad-task-terminal', 'task.state_observed', 'task.progress', {
          binding: { correlation_id: 'corr', task_id: 'task-1' },
          source_event_id: 'task-event-1',
          source_occurred_at: '2026-08-05T09:00:00Z',
          source_seq: 1,
          state: 'terminal',
          outcome: 'failed',
          reason_code: 'PROVIDER_FAILURE',
        })
      ),
    'SEMANTIC_TARGET_BINDING_REQUIRED'
  );
  rejectsWith(
    () =>
      createObservation(
        observation('bad-agent-failure-target', 'failure.observed', 'agent.dispatch', {
          binding: { correlation_id: 'corr' },
          reason_code: 'AGENT_FAILURE',
          error_code: 'INTERNAL',
        })
      ),
    'FAILURE_TARGET_BINDING_REQUIRED'
  );
  rejectsWith(
    () =>
      createObservation(
        observation('bad-queue-segment', 'queue.pressure', 'runtime.response', {
          reason_code: 'QUEUE_CAPACITY',
          queue_depth: 4,
          queue_capacity: 4,
        })
      ),
    'EVENT_SEGMENT_MISMATCH'
  );
});

test('metric vocabulary and dimensions reject arbitrary cardinality', () => {
  let index = 0;
  for (const [name, definition] of Object.entries(METRIC_DEFINITIONS)) {
    const record = createMetric(metric(`metric-${index}`, name, definition.metric_kind, definition.unit));
    assert.equal(record.metric_name, name);
    assert.equal('labels' in record, false);
    assert.equal('attributes' in record, false);
    index += 1;
  }
  rejectsWith(
    () =>
      createObservation(
        observation('cancel-without-scope', 'cancel.requested', 'runtime.response', {
          binding: {
            correlation_id: 'corr',
            interaction_id: 'interaction',
            response_id: 'response',
            response_generation: 1,
          },
          reason_code: 'CANCEL_REQUESTED',
        })
      ),
    'EVENT_FACT_REQUIRED'
  );
  rejectsWith(
    () =>
      createObservation(
        observation('stale-without-response', 'fence.stale_dropped', 'runtime.presentation', {
          binding: { correlation_id: 'corr' },
          reason_code: 'STALE_GENERATION',
          error_code: 'STALE',
        })
      ),
    'SEMANTIC_TARGET_BINDING_REQUIRED'
  );
  rejectsWith(() => createMetric({ ...metric('labels', 'live_voice.failure_total', 'counter', 'count'), labels: { user_id: 'u-1' } }), 'UNKNOWN_FIELD');
  rejectsWith(() => createMetric({ ...metric('reason', 'live_voice.failure_total', 'counter', 'count'), reason_code: 'USER_TEXT' }), 'INVALID_VOCABULARY');
  rejectsWith(
    () =>
      createMetric(
        metric('route-class', 'live_voice.queue_depth', 'gauge', 'items', {
          route: { ...formalRoute(), implementation_class: 'fallback', reason_code: 'ROUTE_FALLBACK' },
        })
      ),
    'METRIC_ROUTE_CLASS_MISMATCH'
  );
  rejectsWith(() => createRouteDescriptor({ ...formalRoute(), capability_provider: 'https://provider.example/?token=secret' }), 'INVALID_STABLE_TOKEN');
});

test('sink failure and reentrant delivery do not affect accepted business facts', () => {
  const delivered = [];
  let collector;
  collector = new LiveVoiceObservabilityCollector({
    observation_sink(event) {
      delivered.push(event.event_id);
      if (event.event_id === 'outer') {
        assert.equal(collector.emitObservation(observation('inner', 'segment.started', 'runtime.response')), true);
      }
      if (event.event_id === 'raises') throw new Error('sink unavailable');
    },
    metric_sink() {
      throw new Error('metric sink unavailable');
    },
  });

  assert.equal(collector.emitObservation(observation('outer', 'segment.started', 'runtime.response')), true);
  assert.equal(collector.emitObservation(observation('raises', 'segment.started', 'runtime.response')), true);
  assert.equal(collector.emitMetric(metric('metric-sink', 'live_voice.queue_depth', 'gauge', 'items')), true);
  assert.deepEqual(
    collector.observations().map(event => event.event_id),
    ['outer', 'inner', 'raises']
  );
  assert.deepEqual(delivered, ['outer', 'inner', 'raises']);
  assert.equal(collector.stats().sink_failures, 2);
});

test('rejected asynchronous sink work is contained after product return', async () => {
  const collector = new LiveVoiceObservabilityCollector({
    observation_sink: async () => {
      throw new Error('async sink unavailable');
    },
    metric_sink: async () => {
      throw new Error('async metric sink unavailable');
    },
  });

  assert.equal(collector.emitObservation(observation('async-event', 'segment.started', 'runtime.response')), true);
  assert.equal(collector.emitMetric(metric('async-metric', 'live_voice.queue_depth', 'gauge', 'items')), true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(collector.stats().sink_failures, 2);
  assert.equal(collector.observations().length, 1);
  assert.equal(collector.metrics().length, 1);
});

test('flag off performs no validation, sink, timer, network, or storage work', () => {
  const effects = [];
  const collector = new LiveVoiceObservabilityCollector({
    enabled: false,
    observation_sink: event => effects.push(event),
    metric_sink: value => effects.push(value),
  });
  const explosive = {};
  Object.defineProperty(explosive, 'schema_version', {
    enumerable: true,
    get() {
      throw new Error('disabled collector inspected input');
    },
  });

  assert.equal(collector.emitObservation(explosive), false);
  assert.equal(collector.emitMetric(explosive), false);
  assert.deepEqual(collector.observations(), []);
  assert.deepEqual(collector.metrics(), []);
  assert.deepEqual(effects, []);

  const explosiveRoute = {};
  Object.defineProperty(explosiveRoute, 'implementation_class', {
    enumerable: true,
    get() {
      throw new Error('disabled browser observer inspected route');
    },
  });
  const observer = createBrowserAudioObservabilityObserver({
    collector,
    route: explosiveRoute,
    binding: () => {
      effects.push('binding');
      throw new Error('disabled browser observer invoked binding');
    },
    clock: () => {
      effects.push('clock');
      throw new Error('disabled browser observer invoked clock');
    },
    next_event_id: () => {
      effects.push('event-id');
      throw new Error('disabled browser observer invoked event ID provider');
    },
  });
  assert.deepEqual(observer, {});
  assert.deepEqual(effects, []);
});

test('event and measurement IDs are idempotent but conflicts fail closed', () => {
  const delivered = [];
  const collector = new LiveVoiceObservabilityCollector({ observation_sink: event => delivered.push(event.event_id) });
  const event = observation('same-event', 'segment.started', 'runtime.response');
  const measurement = metric('same-metric', 'live_voice.queue_depth', 'gauge', 'items');

  assert.equal(collector.emitObservation(event), true);
  assert.equal(collector.emitObservation(event), true);
  assert.equal(collector.emitObservation(observation('same-event', 'segment.started', 'agent.dispatch')), false);
  assert.equal(collector.emitMetric(measurement), true);
  assert.equal(collector.emitMetric(measurement), true);
  assert.equal(collector.emitMetric({ ...measurement, segment_name: 'agent.queue' }), false);
  assert.deepEqual(delivered, ['same-event']);
  assert.deepEqual(collector.stats(), {
    accepted_observations: 1,
    duplicate_observations: 1,
    rejected_observations: 1,
    accepted_metrics: 1,
    duplicate_metrics: 1,
    rejected_metrics: 1,
    sink_failures: 0,
  });
});

test('collector capacity rejects new identities without eviction or redelivery', () => {
  const delivered = [];
  const collector = new LiveVoiceObservabilityCollector({
    max_observations: 1,
    max_metrics: 1,
    observation_sink: event => delivered.push(event.event_id),
    metric_sink: measurement => delivered.push(measurement.measurement_id),
  });
  const firstEvent = observation('event-first', 'segment.started', 'runtime.response');
  const firstMetric = metric('metric-first', 'live_voice.queue_depth', 'gauge', 'items');

  assert.equal(collector.emitObservation(firstEvent), true);
  assert.equal(collector.emitMetric(firstMetric), true);
  assert.equal(collector.emitObservation(firstEvent), true);
  assert.equal(collector.emitMetric(firstMetric), true);
  assert.equal(collector.emitObservation(observation('event-overflow', 'segment.started', 'runtime.response')), false);
  assert.equal(collector.emitMetric(metric('metric-overflow', 'live_voice.queue_depth', 'gauge', 'items')), false);
  assert.deepEqual(
    collector.observations().map(event => event.event_id),
    ['event-first']
  );
  assert.deepEqual(
    collector.metrics().map(measurement => measurement.measurement_id),
    ['metric-first']
  );
  assert.deepEqual(delivered, ['event-first', 'metric-first']);
  assert.equal(collector.stats().duplicate_observations, 1);
  assert.equal(collector.stats().duplicate_metrics, 1);
  assert.equal(collector.stats().rejected_observations, 1);
  assert.equal(collector.stats().rejected_metrics, 1);
  rejectsWith(() => new LiveVoiceObservabilityCollector({ max_observations: 0 }), 'INVALID_CAPACITY');
});

test('identity, clock, unknown fields, accessors, and symbol properties fail closed', () => {
  rejectsWith(() => createTraceBinding({ correlation_id: 'corr', turn_id: 'turn' }), 'TURN_INTERACTION_BINDING_REQUIRED');
  rejectsWith(() => createTraceBinding({ correlation_id: 'corr', interaction_id: 'interaction', response_id: 'response' }), 'RESPONSE_BINDING_INCOMPLETE');
  rejectsWith(() => createTraceBinding({ correlation_id: 'corr', attempt_id: 'attempt' }), 'ATTEMPT_TASK_BINDING_REQUIRED');
  for (const observed_at of ['2026-08-05', '2026-08-05T09:00:00+00:00', '2026-02-30T09:00:00Z', '0000-08-05T09:00:00Z', '2026-08-05T09:00:00.1234567890Z']) {
    rejectsWith(() => createObservation({ ...observation('clock', 'segment.started', 'runtime.response'), observed_at }), 'INVALID_UTC_TIMESTAMP');
  }
  rejectsWith(
    () => createObservation({ ...observation('content', 'segment.started', 'runtime.response'), user_content: 'complete transcript' }),
    'UNKNOWN_FIELD'
  );
  const accessor = observation('accessor', 'segment.started', 'runtime.response');
  Object.defineProperty(accessor, 'source_component', { enumerable: true, get: () => 'observability.test' });
  rejectsWith(() => createObservation(accessor), 'INVALID_OBJECT_PROPERTY');
  const symbolic = observation('symbol', 'segment.started', 'runtime.response');
  symbolic[Symbol('raw_audio')] = new Float32Array([1]);
  rejectsWith(() => createObservation(symbolic), 'INVALID_OBJECT_KEY');
  rejectsWith(
    () =>
      createMetric({
        ...metric('unsafe-counter', 'live_voice.failure_total', 'counter', 'count'),
        value: Number.MAX_SAFE_INTEGER + 1,
      }),
    'INVALID_COUNTER'
  );
  rejectsWith(
    () =>
      createObservation({
        ...observation('source-conflict', 'segment.started', 'task.progress'),
        source_event_id: 'event-1',
        source_record_id: 'row-1',
      }),
    'SOURCE_KIND_CONFLICT'
  );
  rejectsWith(
    () =>
      createObservation({
        ...observation('source-time', 'segment.started', 'task.progress'),
        source_occurred_at: '2026-08-05T09:00:00Z',
      }),
    'SOURCE_EVENT_REQUIRED'
  );
});

test('route observation requires exact correlation binding', () => {
  const record = createRouteTelemetryRecord({
    segment_id: 'p1.capture',
    implementation_class: 'formal',
    owner_module: 'speech.capture',
    capability_provider: 'browser-audio',
    contract_version: CONTRACT_VERSION,
    correlation_id: 'corr-route',
    observed_at: '2026-08-05T09:00:00Z',
    safe_reason: null,
  });
  rejectsWith(
    () =>
      observationFromRouteRecord({
        record,
        event_id: 'route-mismatch',
        segment_name: 'speech.capture',
        monotonic_ms: 1,
        binding: { correlation_id: 'other' },
      }),
    'CORRELATION_BINDING_MISMATCH'
  );
});

test('browser Audio I/O observer uses the public seam and sanitizes reasons', () => {
  const collector = new LiveVoiceObservabilityCollector();
  let eventId = 0;
  const route = formalRoute('audio.browser', 'browser-audio');
  const observer = createBrowserAudioObservabilityObserver({
    collector,
    route,
    binding: { correlation_id: 'corr-audio', interaction_id: 'interaction-1' },
    clock: () => ({ observed_at: '2026-08-05T09:00:00Z', monotonic_ms: eventId * 10 }),
    next_event_id: () => `audio-${eventId++}`,
  });
  route.owner_module = null;
  route.capability_provider = 'https://mutated.example';

  observer.onCaptureState?.({
    state: 'failed',
    reason: 'microphone token=secret complete user text',
    capture_id: 'capture-private',
    capture_generation: 2,
  });
  observer.onDeviceChange?.({ audio_input_count: 3, reason: 'enumeration_failed' });
  observer.onPlayoutState?.({
    state: 'playing',
    reason: 'private unit content',
    response: {
      interaction_id: 'interaction-1',
      response_id: 'response-2',
      response_generation: 5,
    },
    unit_id: 'private-unit-id',
    through_seq: 7,
  });

  assert.equal(collector.observations().length, 3);
  assert.deepEqual(
    collector.observations().map(event => event.event_name),
    ['speech.capture_state', 'speech.device_change', 'speech.playout_state']
  );
  assert.equal(collector.observations()[0].reason_code, 'UNAVAILABLE');
  assert.equal(collector.observations()[0].error_code, 'UNAVAILABLE');
  assert.equal(collector.observations()[1].reason_code, 'DEVICE_ENUMERATION_FAILED');
  assert.equal(collector.observations()[2].binding.response_id, 'response-2');
  const serialized = JSON.stringify(collector.observations());
  for (const forbidden of ['token=secret', 'complete user text', 'capture-private', 'private-unit-id']) {
    assert.equal(serialized.includes(forbidden), false);
  }
});

test('browser observer callback helper failure is isolated from the product callback', () => {
  const collector = new LiveVoiceObservabilityCollector();
  const observer = createBrowserAudioObservabilityObserver({
    collector,
    route: formalRoute('audio.browser', 'browser-audio'),
    binding: () => {
      throw new Error('context unavailable');
    },
    clock: () => {
      throw new Error('clock unavailable');
    },
    next_event_id: () => {
      throw new Error('id unavailable');
    },
  });

  assert.doesNotThrow(() => observer.onCaptureState?.({ state: 'active', reason: 'started', capture_id: null, capture_generation: null }));
  assert.equal(collector.observations().length, 0);
});
