import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  PRODUCT_COMPOSITION_CONTRACT_VERSION,
  PRODUCT_EVIDENCE_IDS,
  PRODUCT_ROUTE_REASONS,
  PRODUCT_ROUTE_TRUTH,
  PRODUCT_SEGMENTS,
  ProductCompositionContractViolation,
  createProductCompositionManifest,
  routeFactFromIntegratedShell,
} from '../node_modules/.cache/live-voice-product-composition/productCompositionContract.js';

const fixtureUrl = new URL('../../../../../tests/fixtures/live_voice_product_composition_gate0_v1/contract.json', import.meta.url);

const formalEvidence = Object.freeze(['TRUSTED_AUTHORITY_RESOLVED', 'FORMAL_ACTIVATION_LEASE_OPEN', 'RUNTIME_PATH_OBSERVED']);

function segmentFormalEvidence(segment) {
  if (segment === 'p1.speech_media') return [...formalEvidence, 'MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED'];
  if (segment === 'p2.agent_interaction') return [...formalEvidence, 'P2_NOTIFICATION_BACKPRESSURE_CLOSED'];
  return [...formalEvidence];
}

function formalFact(segment, evidenceIds = segmentFormalEvidence(segment)) {
  return routeFactFromIntegratedShell({
    segment,
    feature_enabled: true,
    legacy_route_class: 'formal',
    formal_runtime_observed: true,
    formal_evidence_ids: evidenceIds,
  });
}

test('shared fixture matches the closed Gate-0 vocabulary', async () => {
  const fixture = JSON.parse(await readFile(fixtureUrl, 'utf8'));
  assert.equal(fixture.contract_version, PRODUCT_COMPOSITION_CONTRACT_VERSION);
  assert.deepEqual(fixture.route_truth, PRODUCT_ROUTE_TRUTH);
  assert.deepEqual(fixture.segments, PRODUCT_SEGMENTS);
  assert.deepEqual(fixture.reason_ids, PRODUCT_ROUTE_REASONS);
  assert.deepEqual(fixture.evidence_ids, PRODUCT_EVIDENCE_IDS);
});

test('feature-off returns without inspecting route_facts', () => {
  const input = { enabled: false };
  Object.defineProperty(input, 'route_facts', {
    get() {
      throw new Error('feature-off inspected route_facts');
    },
  });
  const manifest = createProductCompositionManifest(input);
  assert.equal(manifest.enabled, false);
  assert.deepEqual(
    manifest.routes.map(route => [route.segment, route.truth, route.reason_id]),
    PRODUCT_SEGMENTS.map(segment => [segment, 'disabled', 'FEATURE_DISABLED'])
  );
});

test('fallback and D-047 substitute remain distinct', () => {
  const fallback = routeFactFromIntegratedShell({
    segment: 'p1.speech_media',
    feature_enabled: true,
    legacy_route_class: 'fallback',
  });
  const substitute = routeFactFromIntegratedShell({
    segment: 'p3.control',
    feature_enabled: true,
    legacy_route_class: 'demo_substitute',
  });
  const manifest = createProductCompositionManifest({ enabled: true, route_facts: [fallback, substitute] });
  assert.equal(manifest.routes[1].truth, 'fallback');
  assert.equal(manifest.routes[4].truth, 'demo_substitute');
  assert.equal(manifest.routes[0].truth, 'unavailable');
});

test('enabled manifest without supplied facts defaults every segment unavailable', () => {
  const manifest = createProductCompositionManifest({ enabled: true });
  assert.equal(manifest.routes.length, PRODUCT_SEGMENTS.length);
  assert.ok(manifest.routes.every(route => route.truth === 'unavailable' && route.reason_id === 'ADAPTER_NOT_REGISTERED'));
});

test('unsupported and unknown diagnostics map to unavailable', () => {
  for (const legacy of ['unsupported', 'unknown']) {
    const fact = routeFactFromIntegratedShell({
      segment: 'p2.agent_interaction',
      feature_enabled: true,
      legacy_route_class: legacy,
    });
    assert.equal(fact.truth, 'unavailable');
    assert.equal(fact.reason_id, 'REQUESTED_ROUTE_UNAVAILABLE');
  }
});

test('formal registration or manifest alone remains unavailable', () => {
  const fact = routeFactFromIntegratedShell({
    segment: 'p2.agent_interaction',
    feature_enabled: true,
    legacy_route_class: 'formal',
  });
  assert.equal(fact.truth, 'unavailable');
  assert.equal(fact.reason_id, 'FORMAL_ACTIVATION_EVIDENCE_MISSING');
  assert.ok(fact.evidence_ids.includes('NO_RUNTIME_EVIDENCE'));
});

test('formal truth requires authority, active lease, and observed runtime path', () => {
  assert.throws(
    () =>
      routeFactFromIntegratedShell({
        segment: 'p2.agent_interaction',
        feature_enabled: true,
        legacy_route_class: 'formal',
        formal_runtime_observed: true,
        formal_evidence_ids: ['RUNTIME_PATH_OBSERVED'],
      }),
    ProductCompositionContractViolation
  );
  const fact = formalFact('p2.agent_interaction');
  assert.equal(fact.truth, 'formal');
});

test('formal truth requires its segment-specific activation-stop closure', () => {
  for (const [segment, required] of [
    ['p1.speech_media', 'MEDIA_LOGGER_ZERO_PERSISTENCE_VERIFIED'],
    ['p2.agent_interaction', 'P2_NOTIFICATION_BACKPRESSURE_CLOSED'],
  ]) {
    assert.throws(
      () =>
        formalFact(
          segment,
          segmentFormalEvidence(segment).filter(evidence => evidence !== required)
        ),
      /affirmative activation-stop closure evidence/
    );
    assert.equal(formalFact(segment).truth, 'formal');
  }
});

test('formal truth rejects unresolved activation-stop evidence', () => {
  for (const unresolved of ['P2_NOTIFICATION_QUEUE_BLOCKING_RISK', 'DEV_AUDIO_LOG_PERSISTENCE_RISK']) {
    assert.throws(() => formalFact('authority', [...formalEvidence, unresolved]), /contradictory evidence/);
  }
});

test('dependent formal segments require formal authority', () => {
  const dependent = formalFact('p1.speech_media');
  assert.throws(() => createProductCompositionManifest({ enabled: true, route_facts: [dependent] }), /require a formal authority segment/);
  const manifest = createProductCompositionManifest({
    enabled: true,
    route_facts: [formalFact('authority'), dependent],
  });
  assert.equal(manifest.routes[0].truth, 'formal');
  assert.equal(manifest.routes[1].truth, 'formal');
});

test('contradictory evidence fails closed', () => {
  assert.throws(
    () =>
      createProductCompositionManifest({
        enabled: true,
        route_facts: [
          {
            segment: 'p1.speech_media',
            truth: 'fallback',
            reason_id: 'EXPLICIT_FALLBACK_ACTIVE',
            evidence_ids: ['FALLBACK_ROUTE_SELECTED', 'RUNTIME_PATH_OBSERVED'],
            formal_runtime_observed: false,
          },
        ],
      }),
    /contradictory evidence/
  );
});

test('feature-off mapping does not inspect the old diagnostic value', () => {
  const fact = routeFactFromIntegratedShell({
    segment: 'browser.audio',
    feature_enabled: false,
    legacy_route_class: Symbol('must not inspect'),
  });
  assert.equal(fact.truth, 'disabled');
});

test('invalid formal observation types fail closed instead of changing truth', () => {
  assert.throws(
    () =>
      routeFactFromIntegratedShell({
        segment: 'p2.agent_interaction',
        feature_enabled: true,
        legacy_route_class: 'formal',
        formal_runtime_observed: 'yes',
      }),
    /formal_runtime_observed must be boolean/
  );
});

test('route facts and manifest arrays are immutable', () => {
  const fact = routeFactFromIntegratedShell({
    segment: 'p1.speech_media',
    feature_enabled: true,
    legacy_route_class: 'fallback',
  });
  const manifest = createProductCompositionManifest({ enabled: true, route_facts: [fact] });
  assert.ok(Object.isFrozen(fact));
  assert.ok(Object.isFrozen(fact.evidence_ids));
  assert.ok(Object.isFrozen(manifest));
  assert.ok(Object.isFrozen(manifest.routes));
});
