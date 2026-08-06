import assert from 'node:assert/strict';
import test from 'node:test';

import {
  INTEGRATED_WEB_SEGMENTS,
  IntegratedWebAdapterRegistry,
  IntegratedWebRouteShell,
  IntegratedWebRouteViolation,
  createCurrentIntegratedWebRouteSelection,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/integratedWebRouteShell.js';

const observedAt = '2026-08-05T12:00:00Z';

function counters() {
  return { opens: 0, closes: 0, agent: 0, tool: 0, task: 0, audio: 0, history: 0 };
}

function adapter(segmentId, implementationClass, effects, overrides = {}) {
  const formal = implementationClass === 'formal';
  return {
    segment_id: segmentId,
    adapter_id: `${segmentId}-${implementationClass}`,
    implementation_class: implementationClass,
    owner_module: `${segmentId}.test-adapter`,
    capability_provider: 'deterministic-test-provider',
    contract_version: 'live-voice.contract.v2',
    safe_reason: formal ? null : implementationClass === 'fallback' ? 'EXPLICIT_TEST_FALLBACK' : 'DETERMINISTIC_FAKE_ONLY',
    available: true,
    unavailable_reason: null,
    capabilities: [`${segmentId}.test`],
    activate: async () => {
      effects.opens += 1;
      return {
        close: async () => {
          effects.closes += 1;
        },
      };
    },
    ...overrides,
  };
}

function registryFor(implementationClass, effectsBySegment) {
  const registry = new IntegratedWebAdapterRegistry();
  for (const segmentId of INTEGRATED_WEB_SEGMENTS) {
    registry.register(adapter(segmentId, implementationClass, effectsBySegment[segmentId]));
  }
  return registry;
}

function policy(implementationClass) {
  return Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, implementationClass]));
}

function shell(options = {}) {
  return new IntegratedWebRouteShell({
    enabled: true,
    registry: options.registry ?? new IntegratedWebAdapterRegistry(),
    policy: options.policy ?? policy('formal'),
    context: {
      session_id: options.sessionId === undefined ? 'session-1' : options.sessionId,
      correlation_id: 'correlation-1',
      observed_at: observedAt,
    },
    fault_plan: options.faultPlan,
    close_wait_timeout_ms: options.closeWaitTimeoutMs,
  });
}

test('one deterministic fake journey composes all segments without claiming a formal or release route', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const route = shell({ registry: registryFor('demo_substitute', effectsBySegment), policy: policy('demo_substitute') });

  const preview = route.preview();
  assert.equal(preview.composition_state, 'degraded');
  assert.equal(preview.gate_claim, 'NONE');
  assert.equal(preview.activation_leases_active, false);
  assert.deepEqual(
    preview.segments.map(segment => [segment.segment_id, segment.requested_class, segment.implementation_class, segment.wiring_state]),
    INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, 'demo_substitute', 'demo_substitute', 'activation_seam'])
  );

  assert.equal(await route.activate(), true);
  assert.equal(route.preview().activation_leases_active, true);
  assert.equal(route.preview().teardown_state, 'idle');
  assert.equal(await route.close(), true);
  assert.equal(await route.close(), false);
  for (const effects of Object.values(effectsBySegment)) {
    assert.equal(effects.opens, 1);
    assert.equal(effects.closes, 1);
    assert.deepEqual(
      { agent: effects.agent, tool: effects.tool, task: effects.task, audio: effects.audio, history: effects.history },
      { agent: 0, tool: 0, task: 0, audio: 0, history: 0 }
    );
  }
});

test('three injected formal adapters disclose formal activation seams without claiming runtime wiring', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const route = shell({ registry: registryFor('formal', effectsBySegment), policy: policy('formal') });
  const preview = route.preview();
  assert.equal(preview.composition_state, 'formal_seams');
  assert.equal(
    preview.segments.every(segment => segment.implementation_class === 'formal'),
    true
  );
  assert.equal(
    preview.segments.every(segment => segment.contract_version === 'live-voice.contract.v2'),
    true
  );
  assert.equal(
    preview.segments.every(segment => segment.safe_reason === null),
    true
  );
  assert.equal(await route.activate(), true);
  assert.equal(await route.close(), true);
});

test('a formal request never silently selects an available fallback', async () => {
  const effects = counters();
  const registry = new IntegratedWebAdapterRegistry().register(adapter('p1.speech_io', 'fallback', effects));
  const route = shell({ registry, policy: policy('formal') });
  const p1 = route.preview().segments[0];
  assert.equal(p1.requested_class, 'formal');
  assert.equal(p1.implementation_class, 'unsupported');
  assert.equal(p1.safe_reason, 'REQUESTED_ROUTE_CLASS_UNAVAILABLE');
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_NOT_ACTIVATABLE');
  assert.equal(effects.opens, 0);
});

test('the current compatibility selection is manifest-only and keeps every predecessor truthful', async () => {
  const selection = createCurrentIntegratedWebRouteSelection({
    p1_browser_speech_available: true,
    p2_text_chat_available: true,
    p3_task_compatibility_enabled: true,
    p3_task_compatibility_available: true,
  });
  const route = shell({ registry: selection.registry, policy: selection.policy });
  const preview = route.preview();
  assert.equal(preview.composition_state, 'shell_only');
  assert.deepEqual(
    preview.segments.map(segment => segment.implementation_class),
    ['fallback', 'fallback', 'demo_substitute']
  );
  assert.equal(
    preview.segments.every(segment => segment.wiring_state === 'manifest_only'),
    true
  );
  assert.equal(
    preview.segments.every(segment => segment.contract_version === null),
    true
  );
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_NOT_ACTIVATABLE');
});

test('task compatibility flag-off is explicit unsupported rather than an inferred substitute', () => {
  const selection = createCurrentIntegratedWebRouteSelection({
    p1_browser_speech_available: true,
    p2_text_chat_available: true,
    p3_task_compatibility_enabled: false,
    p3_task_compatibility_available: true,
  });
  const preview = shell({ registry: selection.registry, policy: selection.policy }).preview();
  const task = preview.segments.find(segment => segment.segment_id === 'p3alpha.task_control');
  assert.equal(task.requested_class, 'unsupported');
  assert.equal(task.implementation_class, 'unsupported');
  assert.equal(task.safe_reason, 'CAPABILITY_NOT_REQUESTED');
});

test('an unavailable current predecessor keeps its adapter identity but no v2 or success claim', () => {
  const selection = createCurrentIntegratedWebRouteSelection({
    p1_browser_speech_available: false,
    p2_text_chat_available: true,
    p3_task_compatibility_enabled: false,
    p3_task_compatibility_available: false,
  });
  const p1 = shell({ registry: selection.registry, policy: selection.policy }).preview().segments[0];
  assert.equal(p1.implementation_class, 'unsupported');
  assert.equal(p1.owner_module, 'P1.BrowserSpeechCompatibility');
  assert.equal(p1.adapter_id, 'compat.browser-speech');
  assert.equal(p1.contract_version, null);
  assert.equal(p1.safe_reason, 'BROWSER_SPEECH_UNAVAILABLE');
});

test('integrated flag-off yields three explicit facts and zero activation or business effects', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const route = new IntegratedWebRouteShell({
    enabled: false,
    registry: registryFor('formal', effectsBySegment),
    policy: policy('formal'),
    context: { session_id: 'session-1', correlation_id: 'correlation-off', observed_at: observedAt },
  });
  const preview = route.preview();
  assert.equal(preview.composition_state, 'flag_off');
  assert.equal(preview.segments.length, 3);
  assert.equal(
    preview.segments.every(segment => segment.implementation_class === 'unsupported' && segment.safe_reason === 'FEATURE_DISABLED'),
    true
  );
  assert.equal(await route.activate(), false);
  assert.equal(
    Object.values(effectsBySegment).every(effects => effects.opens === 0 && effects.closes === 0),
    true
  );
});

test('a missing persisted Session fails every segment closed before activation', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const route = shell({ registry: registryFor('formal', effectsBySegment), policy: policy('formal'), sessionId: null });
  const preview = route.preview();
  assert.equal(preview.composition_state, 'unsupported');
  assert.equal(
    preview.segments.every(segment => segment.safe_reason === 'PERSISTED_SESSION_REQUIRED'),
    true
  );
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_NOT_ACTIVATABLE');
  assert.equal(
    Object.values(effectsBySegment).every(effects => effects.opens === 0),
    true
  );
});

test('capability fault injection is visible and causes zero adapter effects', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const route = shell({
    registry: registryFor('formal', effectsBySegment),
    policy: policy('formal'),
    faultPlan: { unavailable_segments: ['p2.realtime_conversation'] },
  });
  const preview = route.preview();
  assert.equal(preview.composition_state, 'unsupported');
  assert.equal(preview.segments[1].safe_reason, 'INJECTED_CAPABILITY_UNAVAILABLE');
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_NOT_ACTIVATABLE');
  assert.equal(
    Object.values(effectsBySegment).every(effects => effects.opens === 0),
    true
  );
});

test('activation fault rolls back earlier segment resources and never widens into business scopes', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const route = shell({
    registry: registryFor('formal', effectsBySegment),
    policy: policy('formal'),
    faultPlan: { fail_activation_segments: ['p2.realtime_conversation'] },
  });
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'INJECTED_ACTIVATION_FAILURE');
  assert.equal(effectsBySegment['p1.speech_io'].opens, 1);
  assert.equal(effectsBySegment['p1.speech_io'].closes, 1);
  assert.equal(effectsBySegment['p2.realtime_conversation'].opens, 0);
  assert.equal(effectsBySegment['p3alpha.task_control'].opens, 0);
  assert.equal(route.preview().activation_leases_active, false);
  for (const effects of Object.values(effectsBySegment)) {
    assert.equal(effects.agent + effects.tool + effects.task + effects.audio + effects.history, 0);
  }
});

test('concurrent activation requests coalesce and open every segment exactly once', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const route = shell({ registry: registryFor('formal', effectsBySegment), policy: policy('formal') });

  assert.deepEqual(await Promise.all([route.activate(), route.activate()]), [true, true]);
  for (const effects of Object.values(effectsBySegment)) assert.equal(effects.opens, 1);
  assert.equal(await route.close(), true);
});

test('close fences a pending activation, closes its late lease, and opens no later segment', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  let releaseP1;
  let reportP1Started;
  const p1Started = new Promise(resolve => {
    reportP1Started = resolve;
  });
  const p1Release = new Promise(resolve => {
    releaseP1 = resolve;
  });
  const registry = registryFor('formal', effectsBySegment);
  const fencedRegistry = new IntegratedWebAdapterRegistry();
  for (const registered of registry.list()) {
    fencedRegistry.register(
      registered.segment_id === 'p1.speech_io'
        ? {
            ...registered,
            activate: async () => {
              effectsBySegment[registered.segment_id].opens += 1;
              reportP1Started();
              await p1Release;
              return {
                close: async () => {
                  effectsBySegment[registered.segment_id].closes += 1;
                },
              };
            },
          }
        : registered
    );
  }
  const route = shell({ registry: fencedRegistry, policy: policy('formal') });

  const activation = route.activate();
  await p1Started;
  const activationRejection = assert.rejects(activation, error => error instanceof IntegratedWebRouteViolation && error.reason === 'ACTIVATION_FENCED');
  const closing = route.close();
  releaseP1();

  await activationRejection;
  assert.equal(await closing, true);
  assert.equal(effectsBySegment['p1.speech_io'].opens, 1);
  assert.equal(effectsBySegment['p1.speech_io'].closes, 1);
  assert.equal(effectsBySegment['p2.realtime_conversation'].opens, 0);
  assert.equal(effectsBySegment['p3alpha.task_control'].opens, 0);
  assert.equal(route.preview().activation_leases_active, false);
});

test('close aborts a cooperative pending adapter before any later segment can open', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  let reportP1Started;
  const p1Started = new Promise(resolve => {
    reportP1Started = resolve;
  });
  const registry = registryFor('formal', effectsBySegment);
  const abortableRegistry = new IntegratedWebAdapterRegistry();
  for (const registered of registry.list()) {
    abortableRegistry.register(
      registered.segment_id === 'p1.speech_io'
        ? {
            ...registered,
            activate: async ({ signal }) => {
              effectsBySegment[registered.segment_id].opens += 1;
              reportP1Started();
              await new Promise((resolve, reject) => {
                signal.addEventListener('abort', () => reject(new Error('adapter activation aborted')), { once: true });
              });
              throw new Error('unreachable');
            },
          }
        : registered
    );
  }
  const route = shell({ registry: abortableRegistry, policy: policy('formal') });

  const activation = route.activate();
  await p1Started;
  const activationRejection = assert.rejects(activation, error => error instanceof IntegratedWebRouteViolation && error.reason === 'ACTIVATION_FENCED');
  assert.equal(await route.close(), true);
  await activationRejection;
  assert.equal(effectsBySegment['p1.speech_io'].opens, 1);
  assert.equal(effectsBySegment['p1.speech_io'].closes, 0);
  assert.equal(effectsBySegment['p2.realtime_conversation'].opens, 0);
  assert.equal(effectsBySegment['p3alpha.task_control'].opens, 0);
});

test('close times out honestly while a non-cooperative activation remains fenced and coordinated', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  let releaseP1;
  let reportP1Started;
  const p1Started = new Promise(resolve => {
    reportP1Started = resolve;
  });
  const p1Release = new Promise(resolve => {
    releaseP1 = resolve;
  });
  const registry = registryFor('formal', effectsBySegment);
  const nonCooperativeRegistry = new IntegratedWebAdapterRegistry();
  for (const registered of registry.list()) {
    nonCooperativeRegistry.register(
      registered.segment_id === 'p1.speech_io'
        ? {
            ...registered,
            activate: async () => {
              effectsBySegment[registered.segment_id].opens += 1;
              reportP1Started();
              await p1Release;
              return {
                close: async () => {
                  effectsBySegment[registered.segment_id].closes += 1;
                },
              };
            },
          }
        : registered
    );
  }
  const route = shell({ registry: nonCooperativeRegistry, policy: policy('formal'), closeWaitTimeoutMs: 5 });

  const activation = route.activate();
  await p1Started;
  const activationRejection = assert.rejects(activation, error => error instanceof IntegratedWebRouteViolation && error.reason === 'ACTIVATION_FENCED');
  await assert.rejects(route.close(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_CLOSE_TIMEOUT');
  assert.equal(route.preview().teardown_state, 'pending');
  assert.equal(route.preview().activation_leases_active, false);
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_CLOSE_IN_PROGRESS');
  await assert.rejects(route.close(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_CLOSE_TIMEOUT');

  releaseP1();
  await activationRejection;
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(route.preview().teardown_state, 'idle');
  assert.equal(await route.close(), false);
  assert.equal(effectsBySegment['p1.speech_io'].closes, 1);
  assert.equal(effectsBySegment['p2.realtime_conversation'].opens, 0);
  assert.equal(effectsBySegment['p3alpha.task_control'].opens, 0);
});

test('multiple rollback close failures retain acquisition order for every LIFO retry', async () => {
  const order = [];
  const closeAttempts = new Map();
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  const registry = new IntegratedWebAdapterRegistry();
  for (const segmentId of INTEGRATED_WEB_SEGMENTS) {
    registry.register(
      adapter(segmentId, 'formal', effectsBySegment[segmentId], {
        activate: async () => {
          effectsBySegment[segmentId].opens += 1;
          return {
            close: async () => {
              const attempt = (closeAttempts.get(segmentId) ?? 0) + 1;
              closeAttempts.set(segmentId, attempt);
              order.push(`${segmentId}#${attempt}`);
              effectsBySegment[segmentId].closes += 1;
              if (attempt === 1) throw new Error(`first close failed for ${segmentId}`);
            },
          };
        },
      })
    );
  }
  const route = shell({ registry, policy: policy('formal'), faultPlan: { fail_activation_segments: ['p3alpha.task_control'] } });

  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ACTIVATION_ROLLBACK_FAILED');
  assert.deepEqual(order, ['p2.realtime_conversation#1', 'p1.speech_io#1']);
  assert.equal(route.preview().teardown_state, 'cleanup_required');
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_CLEANUP_REQUIRED');
  assert.equal(await route.close(), true);
  assert.deepEqual(order, ['p2.realtime_conversation#1', 'p1.speech_io#1', 'p2.realtime_conversation#2', 'p1.speech_io#2']);
  assert.equal(route.preview().teardown_state, 'idle');
});

test('a failed close remains retryable while every other segment still closes', async () => {
  const effectsBySegment = Object.fromEntries(INTEGRATED_WEB_SEGMENTS.map(segmentId => [segmentId, counters()]));
  let firstClose = true;
  const registry = registryFor('formal', effectsBySegment);
  const retryRegistry = new IntegratedWebAdapterRegistry();
  for (const registered of registry.list()) {
    retryRegistry.register(
      registered.segment_id === 'p1.speech_io'
        ? {
            ...registered,
            activate: async () => {
              effectsBySegment[registered.segment_id].opens += 1;
              return {
                close: async () => {
                  effectsBySegment[registered.segment_id].closes += 1;
                  if (firstClose) {
                    firstClose = false;
                    throw new Error('transient close failure');
                  }
                },
              };
            },
          }
        : registered
    );
  }
  const route = shell({ registry: retryRegistry, policy: policy('formal') });
  await route.activate();
  await assert.rejects(route.close(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_CLOSE_FAILED');
  assert.equal(effectsBySegment['p2.realtime_conversation'].closes, 1);
  assert.equal(effectsBySegment['p3alpha.task_control'].closes, 1);
  await assert.rejects(route.activate(), error => error instanceof IntegratedWebRouteViolation && error.reason === 'ROUTE_CLEANUP_REQUIRED');
  assert.equal(effectsBySegment['p1.speech_io'].opens, 1);
  assert.equal(await route.close(), true);
  assert.equal(effectsBySegment['p1.speech_io'].closes, 2);
});

test('ambiguous bindings and incomplete formal provenance reject at registration', () => {
  const effects = counters();
  const registry = new IntegratedWebAdapterRegistry().register(adapter('p1.speech_io', 'fallback', effects));
  assert.throws(
    () => registry.register(adapter('p1.speech_io', 'fallback', effects, { adapter_id: 'another-fallback' })),
    error => error instanceof IntegratedWebRouteViolation && error.reason === 'AMBIGUOUS_ROUTE_BINDING'
  );
  assert.throws(
    () => new IntegratedWebAdapterRegistry().register(adapter('p1.speech_io', 'formal', effects, { capability_provider: null, contract_version: null })),
    error => error instanceof IntegratedWebRouteViolation && error.reason === 'INCOMPLETE_ADAPTER_PROVENANCE'
  );
});

test('invalid policy and Session input reject before any route can activate', () => {
  assert.throws(
    () => shell({ policy: { ...policy('formal'), 'p2.realtime_conversation': 'unknown' } }),
    error => error instanceof IntegratedWebRouteViolation && error.reason === 'INVALID_REQUESTED_CLASS'
  );
  assert.throws(
    () => shell({ sessionId: 42 }),
    error => error instanceof IntegratedWebRouteViolation && error.reason === 'INVALID_SESSION_ID'
  );
  assert.throws(
    () => shell({ closeWaitTimeoutMs: 0 }),
    error => error instanceof IntegratedWebRouteViolation && error.reason === 'INVALID_CLOSE_WAIT_TIMEOUT'
  );
  assert.throws(
    () => shell({ closeWaitTimeoutMs: 60_001 }),
    error => error instanceof IntegratedWebRouteViolation && error.reason === 'INVALID_CLOSE_WAIT_TIMEOUT'
  );
  assert.throws(
    () =>
      createCurrentIntegratedWebRouteSelection({
        p1_browser_speech_available: 'yes',
        p2_text_chat_available: true,
        p3_task_compatibility_enabled: false,
        p3_task_compatibility_available: false,
      }),
    error => error instanceof IntegratedWebRouteViolation && error.reason === 'INVALID_CURRENT_ROUTE_FACT'
  );
});
