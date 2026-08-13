import assert from 'node:assert/strict';
import test from 'node:test';

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { TaskRevisionTruthProjection } from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';
import {
  TaskRevisionTruthReplica,
  parseTaskRevisionTruth,
  parseTaskRevisionTruthStatusResponse,
  taskRevisionApplicationState,
  taskRevisionWarning,
} from '../node_modules/.cache/live-voice-integrated-web/features/live-voice/formal/taskRevisionTruth.js';

function constraints() {
  return {
    write_scope: ['src/calculator.py'],
    dependency_policy: 'locked',
    public_api_policy: 'preserve',
    configuration_policy: 'preserve',
    regression_verifier_required: true,
  };
}

function revision(number, attemptId, commandId) {
  return {
    task_id: 'task-1',
    task_revision: number,
    predecessor_revision: number === 1 ? null : number - 1,
    attempt_id: attemptId,
    base_instruction: 'Fix the calculator defect.',
    additive_facts: number === 1 ? [] : ['Zero is a supported operand.'],
    constraints: constraints(),
    origin_commit_id: number === 1 ? 'commit-create' : 'commit-revision',
    created_by_command_id: commandId,
  };
}

function pendingTruth(state = 'fencing') {
  return {
    task_id: 'task-1',
    task_state: 'running',
    outcome: null,
    current_revision: 1,
    current_attempt_id: 'attempt-1',
    attempt_number: 1,
    revision_history: [revision(1, 'attempt-1', 'command-create')],
    pending_command: {
      command_id: 'command-revision',
      task_id: 'task-1',
      application_state: state,
      predecessor_revision: 1,
      successor_revision: 2,
      predecessor_attempt_id: 'attempt-1',
      successor_attempt_id: null,
      fence_outbox_id: 'fence-1',
      dispatch_outbox_id: null,
      replayed: false,
    },
    cleanup: null,
    execution: null,
  };
}

function appliedTruth({ verifierResult = 'passed', verifiedSuccess = verifierResult === 'passed' } = {}) {
  return {
    task_id: 'task-1',
    task_state: verifierResult === 'passed' ? 'terminal' : 'running',
    outcome: verifierResult === 'passed' ? 'completed' : null,
    current_revision: 2,
    current_attempt_id: 'attempt-2',
    attempt_number: 2,
    revision_history: [
      revision(1, 'attempt-1', 'command-create'),
      revision(2, 'attempt-2', 'command-revision'),
    ],
    pending_command: null,
    cleanup: {
      command_id: 'command-revision',
      predecessor_attempt_id: 'attempt-1',
      cleanup_id: 'cleanup-1',
      checkout_identity: 'checkout-attempt-1',
      unapplied_changes_discarded: true,
      acknowledged_at: '2026-08-13T12:00:00Z',
    },
    execution: {
      task_id: 'task-1',
      task_revision: 2,
      attempt_id: 'attempt-2',
      executor_ref: 'executor-attempt-2',
      fixture_identity: 'fixture-v1',
      execution_ack: true,
      changed_paths: ['src/calculator.py'],
      diff_summary: '1 file changed',
      verifier: {
        verifier_id: 'calculator-regression-v1',
        result: verifierResult,
        exit_code: verifierResult === 'passed' ? 0 : 1,
        timed_out: false,
        output_digest: 'a'.repeat(64),
        output_summary: verifierResult,
      },
      cleanup_state: 'successor_cleanup_resolved',
      forbidden_side_effect_count: 0,
      verified_success: verifiedSuccess,
    },
  };
}

test('strict parser keeps command application separate from task success', () => {
  const pending = parseTaskRevisionTruth(pendingTruth(), 'task-1');
  assert.equal(taskRevisionApplicationState(pending), 'fencing');
  assert.equal(pending.task_state, 'running');
  assert.equal(pending.execution, null);
  assert.equal(taskRevisionWarning(pending), null);

  const applied = parseTaskRevisionTruth(appliedTruth(), 'task-1');
  assert.equal(taskRevisionApplicationState(applied), 'applied');
  assert.equal(applied.execution.verified_success, true);
  assert.equal(taskRevisionWarning(applied), null);
});

test('status projection requires an authoritative explicit extension', () => {
  const truth = parseTaskRevisionTruthStatusResponse({
    ok: true,
    result: { task_revision: pendingTruth() },
  }, 'task-1');
  assert.equal(truth.current_revision, 1);
  assert.equal(parseTaskRevisionTruthStatusResponse({
    ok: true,
    result: { task_revision: null },
  }, 'task-1'), null);
  assert.throws(
    () => parseTaskRevisionTruthStatusResponse({ ok: true, result: {} }, 'task-1'),
    /no task revision authority/,
  );
  assert.throws(
    () => parseTaskRevisionTruthStatusResponse({ ok: false, result: null }, 'task-1'),
    /unavailable/,
  );
});

test('unknown cleanup and verifier failure remain explicit non-success truth', () => {
  const unknown = parseTaskRevisionTruth(pendingTruth('unknown'));
  assert.match(taskRevisionWarning(unknown), /cleanup is unknown/);

  const failed = parseTaskRevisionTruth(appliedTruth({ verifierResult: 'failed', verifiedSuccess: false }));
  assert.equal(failed.execution.verified_success, false);
  assert.match(taskRevisionWarning(failed), /Verification failed/);
});

test('replica deduplicates replay, accepts one advance, and rejects stale or rewritten truth', () => {
  const replica = new TaskRevisionTruthReplica(true);
  const generation = replica.connectionGeneration();
  const first = replica.adopt(pendingTruth(), { task_id: 'task-1', connection_generation: generation });
  const replay = replica.adopt(pendingTruth(), { task_id: 'task-1', connection_generation: generation });
  assert.equal(replay, first);

  const applied = replica.adopt(appliedTruth(), { task_id: 'task-1', connection_generation: generation });
  assert.equal(applied.current_revision, 2);
  assert.throws(
    () => replica.adopt(pendingTruth(), { task_id: 'task-1', connection_generation: generation }),
    /cannot regress/,
  );
  const rewritten = appliedTruth();
  rewritten.revision_history[0].attempt_id = 'attempt-forged';
  assert.throws(
    () => replica.adopt(rewritten, { task_id: 'task-1', connection_generation: generation }),
    /self-contradictory|rewrite authority/,
  );
});

test('replica rejects task lifecycle regression within one revision', () => {
  const replica = new TaskRevisionTruthReplica(true);
  const generation = replica.connectionGeneration();
  replica.adopt(pendingTruth(), { task_id: 'task-1', connection_generation: generation });
  const regressed = pendingTruth();
  regressed.task_state = 'accepted';
  assert.throws(
    () => replica.adopt(regressed, { task_id: 'task-1', connection_generation: generation }),
    /cannot regress/,
  );
});

test('disconnect fences late responses and feature-off adopts no truth', () => {
  const replica = new TaskRevisionTruthReplica(true);
  const generation = replica.connectionGeneration();
  replica.disconnect();
  assert.throws(
    () => replica.adopt(pendingTruth(), { task_id: 'task-1', connection_generation: generation }),
    /stale after disconnect/,
  );
  replica.reconnect();
  assert.throws(
    () => replica.adopt(pendingTruth(), { task_id: 'task-1', connection_generation: generation }),
    /stale after disconnect/,
  );

  const disabled = new TaskRevisionTruthReplica(false);
  assert.throws(
    () => disabled.adopt(pendingTruth(), { task_id: 'task-1', connection_generation: 1 }),
    /disabled/,
  );
  assert.equal(disabled.snapshot(), null);
});

test('parser rejects wrong target, missing cleanup, unknown fields and inferred success', () => {
  assert.throws(() => parseTaskRevisionTruth(pendingTruth(), 'task-other'), /target mismatch/);

  const missingCleanup = appliedTruth();
  missingCleanup.cleanup = null;
  assert.throws(() => parseTaskRevisionTruth(missingCleanup), /self-contradictory/);

  const unknownField = pendingTruth();
  unknownField.inferred_success = true;
  assert.throws(() => parseTaskRevisionTruth(unknownField), /fields are incomplete or unknown/);

  const inferredSuccess = appliedTruth();
  inferredSuccess.execution.verified_success = false;
  assert.throws(() => parseTaskRevisionTruth(inferredSuccess), /execution authority truth is inconsistent/);
});

test('projection exposes lineage and labels unverified execution without inference', () => {
  const truth = parseTaskRevisionTruth(appliedTruth({ verifierResult: 'failed', verifiedSuccess: false }));
  const html = renderToStaticMarkup(React.createElement(TaskRevisionTruthProjection, { truth }));
  assert.match(html, /aria-label="Task revision truth"/);
  assert.match(html, /r1:attempt-1 -&gt; r2:attempt-2/);
  assert.match(html, /Command application/);
  assert.match(html, /Task lifecycle/);
  assert.match(html, /not_established/);
  assert.match(html, /Verification failed/);
});
