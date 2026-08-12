import assert from 'node:assert/strict';
import test from 'node:test';

import {
  WEB_LIFECYCLE_OBSERVATION_SCOPE,
  WEB_LIFECYCLE_EXPECTED_TERMINAL_REASON,
  WEB_LIFECYCLE_SCENARIOS,
  WebLifecycleObservationRecorder,
} from '../node_modules/.cache/live-voice-web-lifecycle/webLifecycleObservationRecorder.mjs';

const candidateSha = '161c44bd6adccc413cedd7333387e3da88a222a9';

function context(overrides = {}) {
  return {
    context_binding_id: 'context_ref:001122334455',
    candidate_sha: candidateSha,
    run_id: 'run_ref:aabbccddeeff',
    observation_source: 'controlled_real_chrome',
    browser_family: 'google_chrome',
    browser_version: '150.0.7871.116',
    os_family: 'windows',
    os_version_ref: 'os-version:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
    origin: 'https://voice.example.test',
    input_device_ref: 'device_ref:0123456789abcdef',
    output_device_ref: 'system_default',
    input_selection: 'explicit',
    output_selection: 'system_default',
    network_profile_ref: 'network_ref:fedcba9876543210',
    initial_page_epoch_id: 'page_ref:111111111111',
    ...overrides,
  };
}

function terminal(overrides = {}) {
  return {
    context_binding_id: 'context_ref:001122334455',
    candidate_sha: candidateSha,
    run_id: 'run_ref:aabbccddeeff',
    observation_source: 'controlled_real_chrome',
    scenario_id: 'microphone_permission_grant',
    sequence: 0,
    page_epoch_id: 'page_ref:111111111111',
    successor_page_epoch_id: null,
    result: 'expected_boundary_observed',
    reason_id: 'MICROPHONE_PERMISSION_GRANTED',
    observed_at_monotonic_ms: 10,
    stale_effect_count: 0,
    business_cancel_count_delta: 0,
    automatic_retry_count: 0,
    raw_audio_persisted: false,
    credential_material_observed: false,
    ...overrides,
  };
}

test('empty recorder binds a sanitized environment without claiming verification or Gate credit', () => {
  const recorder = new WebLifecycleObservationRecorder(context());
  const snapshot = recorder.snapshot();

  assert.equal(snapshot.schema_version, 1);
  assert.equal(snapshot.evidence_scope, WEB_LIFECYCLE_OBSERVATION_SCOPE);
  assert.equal(snapshot.source_is_declared_provenance, true);
  assert.equal(snapshot.context.candidate_sha, candidateSha);
  assert.equal(snapshot.context.browser_family, 'google_chrome');
  assert.equal(snapshot.context.origin, 'https://voice.example.test');
  assert.equal(snapshot.binding_verified, false);
  assert.equal(snapshot.evidence_verified, false);
  assert.equal(snapshot.alpha_gate_pass, false);
  assert.equal(snapshot.refresh_reconnect_authority, 'unproven');
  assert.equal(snapshot.all_scenarios_observed, false);
  assert.equal(snapshot.all_expected_boundaries, false);
  assert.equal(snapshot.expected_boundary_observation_count, 0);
  assert.equal(snapshot.unexpected_boundary_observation_count, 0);
  assert.deepEqual(snapshot.missing_scenarios, WEB_LIFECYCLE_SCENARIOS);
  assert.equal(snapshot.controlled_real_observation_count, 0);
  assert.equal(snapshot.automated_observation_count, 0);
  assert.throws(() => recorder.finalizeCompleteLedger(), /missing required terminal scenarios/);
});

test('checkpoint restoration advances an explicit refresh epoch and permits its local clock reset', () => {
  const recorder = new WebLifecycleObservationRecorder(context());
  recorder.recordTerminal(terminal());
  recorder.recordTerminal(
    terminal({
      scenario_id: 'refresh_reconnect',
      sequence: 1,
      reason_id: 'REFRESH_OBSERVED_RECONNECT_UNPROVEN',
      successor_page_epoch_id: 'page_ref:222222222222',
      observed_at_monotonic_ms: 20,
    })
  );
  const checkpoint = recorder.checkpoint();
  const restored = WebLifecycleObservationRecorder.fromCheckpoint(checkpoint);
  restored.recordTerminal(
    terminal({
      scenario_id: 'visible_diagnostics',
      sequence: 2,
      page_epoch_id: 'page_ref:222222222222',
      reason_id: 'VISIBLE_DIAGNOSTICS_OBSERVED',
      observed_at_monotonic_ms: 1,
    })
  );

  const snapshot = restored.snapshot();
  assert.equal(snapshot.current_page_epoch_id, 'page_ref:222222222222');
  assert.equal(snapshot.next_sequence, 3);
  assert.equal(snapshot.controlled_real_observation_count, 3);
  assert.equal(snapshot.automated_observation_count, 0);
  assert.equal(snapshot.expected_boundary_observation_count, 3);
  assert.equal(snapshot.unexpected_boundary_observation_count, 0);
  assert.equal(snapshot.all_expected_boundaries, false);
  assert.equal(snapshot.binding_verified, false);
  assert.equal(snapshot.evidence_verified, false);
  assert.equal(snapshot.alpha_gate_pass, false);
  assert.equal(snapshot.refresh_reconnect_authority, 'unproven');
  assert.deepEqual(
    snapshot.observations.map(observation => observation.sequence),
    [0, 1, 2]
  );

  assert.throws(
    () =>
      restored.recordTerminal(
        terminal({
          scenario_id: 'network_transport_close',
          sequence: 3,
          page_epoch_id: 'page_ref:111111111111',
          reason_id: 'MEDIA_TRANSPORT_CLOSED_NO_RETRY',
        })
      ),
    /stale or foreign page epoch/
  );
  assert.throws(
    () =>
      restored.recordTerminal(
        terminal({
          scenario_id: 'network_transport_close',
          sequence: 3,
          page_epoch_id: 'page_ref:222222222222',
          reason_id: 'MEDIA_TRANSPORT_CLOSED_NO_RETRY',
          observed_at_monotonic_ms: 0,
        })
      ),
    /monotonic time regressed/
  );
  assert.equal(restored.snapshot().next_sequence, 3);
});

test('normalized snapshots and checkpoints drop arbitrary OS labels and terminal details', () => {
  const recorder = new WebLifecycleObservationRecorder(context({ os_display_name: 'Windows private build label', unrelated_secret: 'not-for-evidence' }));
  recorder.recordTerminal(terminal({ raw_detail: 'private terminal message', provider_token: 'not-for-evidence' }));

  const serializedSnapshot = JSON.stringify(recorder.snapshot());
  const serializedCheckpoint = JSON.stringify(recorder.checkpoint());
  for (const serialized of [serializedSnapshot, serializedCheckpoint]) {
    assert.equal(serialized.includes('Windows private build label'), false);
    assert.equal(serialized.includes('private terminal message'), false);
    assert.equal(serialized.includes('not-for-evidence'), false);
    assert.equal(serialized.includes('25H2'), false);
  }
});

test('automated conformance can complete the scenario ledger but never becomes verified real evidence', () => {
  const automatedContext = context({
    observation_source: 'automated_conformance',
    browser_family: 'simulated_google_chrome_contract',
  });
  const recorder = new WebLifecycleObservationRecorder(automatedContext);
  let pageEpoch = automatedContext.initial_page_epoch_id;

  WEB_LIFECYCLE_SCENARIOS.forEach((scenario, sequence) => {
    const refresh = scenario === 'refresh_reconnect';
    recorder.recordTerminal(
      terminal({
        observation_source: 'automated_conformance',
        scenario_id: scenario,
        sequence,
        page_epoch_id: pageEpoch,
        successor_page_epoch_id: refresh ? 'page_ref:222222222222' : null,
        reason_id: WEB_LIFECYCLE_EXPECTED_TERMINAL_REASON[scenario],
        observed_at_monotonic_ms: sequence,
      })
    );
    if (refresh) pageEpoch = 'page_ref:222222222222';
  });

  const snapshot = recorder.finalizeCompleteLedger();
  assert.equal(snapshot.all_scenarios_observed, true);
  assert.deepEqual(snapshot.missing_scenarios, []);
  assert.equal(snapshot.automated_observation_count, WEB_LIFECYCLE_SCENARIOS.length);
  assert.equal(snapshot.controlled_real_observation_count, 0);
  assert.equal(snapshot.binding_verified, false);
  assert.equal(snapshot.evidence_verified, false);
  assert.equal(snapshot.alpha_gate_pass, false);
  assert.equal(snapshot.refresh_reconnect_authority, 'unproven');
  assert.equal(snapshot.expected_boundary_observation_count, WEB_LIFECYCLE_SCENARIOS.length);
  assert.equal(snapshot.unexpected_boundary_observation_count, 0);
  assert.equal(snapshot.all_expected_boundaries, true);
});

test('a complete ledger with one unexpected terminal remains explicitly nonconformant', () => {
  const recorder = new WebLifecycleObservationRecorder(
    context({ observation_source: 'automated_conformance', browser_family: 'simulated_google_chrome_contract' })
  );
  let pageEpoch = 'page_ref:111111111111';
  WEB_LIFECYCLE_SCENARIOS.forEach((scenario, sequence) => {
    const refresh = scenario === 'refresh_reconnect';
    const unexpected = scenario === 'output_loss';
    recorder.recordTerminal(
      terminal({
        observation_source: 'automated_conformance',
        scenario_id: scenario,
        sequence,
        page_epoch_id: pageEpoch,
        successor_page_epoch_id: refresh ? 'page_ref:222222222222' : null,
        result: unexpected ? 'unexpected_boundary_observed' : 'expected_boundary_observed',
        reason_id: unexpected ? 'UNEXPECTED_LIFECYCLE_BOUNDARY' : WEB_LIFECYCLE_EXPECTED_TERMINAL_REASON[scenario],
        observed_at_monotonic_ms: sequence,
      })
    );
    if (refresh) pageEpoch = 'page_ref:222222222222';
  });

  const snapshot = recorder.finalizeCompleteLedger();
  assert.equal(snapshot.all_scenarios_observed, true);
  assert.equal(snapshot.expected_boundary_observation_count, WEB_LIFECYCLE_SCENARIOS.length - 1);
  assert.equal(snapshot.unexpected_boundary_observation_count, 1);
  assert.equal(snapshot.all_expected_boundaries, false);
  assert.equal(snapshot.alpha_gate_pass, false);
});

test('declared provenance cannot masquerade as another browser evidence class', () => {
  assert.throws(() => new WebLifecycleObservationRecorder(context({ browser_family: 'simulated_google_chrome_contract' })), /controlled_real_chrome requires/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ observation_source: 'automated_conformance' })), /automated_conformance requires/);
});

test('candidate, origin, device, network, and version bindings reject noncanonical or sensitive-looking values', () => {
  assert.throws(() => new WebLifecycleObservationRecorder(context({ candidate_sha: '161c44bd' })), /exact lowercase Git SHA/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ context_binding_id: 'plain-binding-id' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ run_id: 'run-with-raw-label' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ initial_page_epoch_id: 'page-from-browser-storage' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ origin: 'https://user:password@voice.example.test' })), /exact HTTP\(S\) origin/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ origin: 'https://voice.example.test/?token=value' })), /exact HTTP\(S\) origin/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ origin: 'http://voice.example.test' })), /requires HTTPS or a localhost/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ input_device_ref: 'Jabra Raw Device Label' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ input_device_ref: 'raw-browser-device-id' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ input_device_ref: 'unknown' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ input_device_ref: 'system_default' })), /input_selection.*inconsistent/);
  assert.throws(
    () => new WebLifecycleObservationRecorder(context({ input_selection: 'default', input_device_ref: 'device_ref:0123456789abcdef' })),
    /input_selection.*inconsistent/
  );
  assert.throws(
    () => new WebLifecycleObservationRecorder(context({ output_selection: 'explicit', output_device_ref: 'system_default' })),
    /output_selection.*inconsistent/
  );
  assert.throws(
    () => new WebLifecycleObservationRecorder(context({ output_selection: 'system_default', output_device_ref: 'device_ref:0123456789abcdef' })),
    /output_selection.*inconsistent/
  );
  assert.throws(() => new WebLifecycleObservationRecorder(context({ network_profile_ref: 'wifi-password-value' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ network_profile_ref: 'unknown' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ browser_version: 'Chrome 150' })), /exact four-part Chrome version/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ browser_version: '150.0.7871' })), /exact four-part Chrome version/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ browser_version: '0150.0.7871.116' })), /exact four-part Chrome version/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ browser_version: '150SECRET.0.7871.116' })), /exact four-part Chrome version/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ browser_version: '106.0.0.0' })), /Chrome 107 or later/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ os_family: 'other' })), /os_family is not supported/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ os_version_ref: '25H2.26200.8875' })), /canonical sanitized reference/);
  assert.throws(() => new WebLifecycleObservationRecorder(context({ os_version_ref: 'os-version:0123456789ab' })), /canonical sanitized reference/);
  assert.throws(
    () => new WebLifecycleObservationRecorder(context({ os_version_ref: 'os-version:0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF0123456789ABCDEF' })),
    /canonical sanitized reference/
  );
});

test('duplicates, gaps, foreign context, and illegal epoch changes fail before ledger mutation', () => {
  const recorder = new WebLifecycleObservationRecorder(context());
  assert.throws(() => recorder.recordTerminal(terminal({ sequence: 1 })), /sequence is not contiguous/);
  assert.equal(recorder.snapshot().next_sequence, 0);
  assert.throws(() => recorder.recordTerminal(terminal({ candidate_sha: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' })), /context binding/);
  assert.equal(recorder.snapshot().next_sequence, 0);
  assert.throws(() => recorder.recordTerminal(terminal({ successor_page_epoch_id: 'page_ref:222222222222' })), /only refresh_reconnect/);
  assert.equal(recorder.snapshot().next_sequence, 0);

  recorder.recordTerminal(terminal());
  assert.throws(() => recorder.recordTerminal(terminal({ sequence: 1 })), /already terminal/);
  assert.equal(recorder.snapshot().next_sequence, 1);
});

test('refresh requires a distinct successor and every later receipt must use it', () => {
  const sameEpoch = new WebLifecycleObservationRecorder(context());
  assert.throws(
    () =>
      sameEpoch.recordTerminal(
        terminal({ scenario_id: 'refresh_reconnect', successor_page_epoch_id: 'page_ref:111111111111', reason_id: 'REFRESH_OBSERVED_RECONNECT_UNPROVEN' })
      ),
    /must be distinct/
  );
  assert.equal(sameEpoch.snapshot().next_sequence, 0);

  const missingEpoch = new WebLifecycleObservationRecorder(context());
  assert.throws(
    () =>
      missingEpoch.recordTerminal(
        terminal({ scenario_id: 'refresh_reconnect', successor_page_epoch_id: null, reason_id: 'REFRESH_OBSERVED_RECONNECT_UNPROVEN' })
      ),
    /successor_page_epoch_id must be a canonical sanitized reference/
  );
});

test('terminal diagnostics and zero-effect privacy facts are fail closed', () => {
  const variants = [
    { reason_id: 'contains a raw message' },
    { observed_at_monotonic_ms: Number.NaN },
    { observed_at_monotonic_ms: 10.25 },
    { stale_effect_count: 1 },
    { business_cancel_count_delta: 1 },
    { automatic_retry_count: 1 },
    { raw_audio_persisted: true },
    { credential_material_observed: true },
  ];
  for (const variant of variants) {
    const recorder = new WebLifecycleObservationRecorder(context());
    assert.throws(() => recorder.recordTerminal(terminal(variant)));
    assert.equal(recorder.snapshot().next_sequence, 0);
  }
});

test('terminal observation time is a nondecreasing safe-integer millisecond clock', () => {
  const recorder = new WebLifecycleObservationRecorder(context());
  recorder.recordTerminal(terminal({ observed_at_monotonic_ms: 20 }));
  recorder.recordTerminal(
    terminal({
      scenario_id: 'microphone_permission_denial',
      sequence: 1,
      reason_id: 'MICROPHONE_PERMISSION_DENIED',
      observed_at_monotonic_ms: 20,
    })
  );
  assert.throws(
    () =>
      recorder.recordTerminal(
        terminal({
          scenario_id: 'device_change',
          sequence: 2,
          reason_id: 'DEVICE_CHANGE_DIAGNOSTIC_ONLY',
          observed_at_monotonic_ms: 19,
        })
      ),
    /monotonic time regressed/
  );
  assert.equal(recorder.snapshot().next_sequence, 2);
});

test('checkpoint restoration replays every invariant and rejects promoted or tampered evidence', () => {
  const recorder = new WebLifecycleObservationRecorder(context());
  recorder.recordTerminal(terminal());
  const checkpoint = JSON.parse(JSON.stringify(recorder.checkpoint()));

  checkpoint.binding_verified = true;
  assert.throws(() => WebLifecycleObservationRecorder.fromCheckpoint(checkpoint), /checkpoint is not supported/);
  checkpoint.binding_verified = false;
  checkpoint.evidence_verified = true;
  assert.throws(() => WebLifecycleObservationRecorder.fromCheckpoint(checkpoint), /checkpoint is not supported/);
  checkpoint.evidence_verified = false;
  checkpoint.source_is_declared_provenance = false;
  assert.throws(() => WebLifecycleObservationRecorder.fromCheckpoint(checkpoint), /checkpoint is not supported/);
  checkpoint.source_is_declared_provenance = true;
  checkpoint.observations[0].sequence = 3;
  assert.throws(() => WebLifecycleObservationRecorder.fromCheckpoint(checkpoint), /sequence is not contiguous/);
});
