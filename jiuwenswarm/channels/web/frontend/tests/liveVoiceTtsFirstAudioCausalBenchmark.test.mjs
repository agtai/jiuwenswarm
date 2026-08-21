import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  parseTtsFirstAudioBenchmarkArgs,
  runTtsFirstAudioCausalBenchmark,
  writeTtsFirstAudioCausalReport,
} from '../scripts/liveVoiceTtsFirstAudioCausalBenchmark.mjs';

test('TTS causal CLI freezes the four populations and private report', async () => {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'tts-first-audio-'));
  const output = path.join(root, 'report.json');
  const config = parseTtsFirstAudioBenchmarkArgs(['--output', output, '--git-commit', 'a'.repeat(40), '--run-id', 'tts-a1-test', '--samples', '5']);

  assert.deepEqual(config, {
    output,
    gitCommit: 'a'.repeat(40),
    runId: 'tts-a1-test',
    samples: 5,
    successorAckDelaysMs: [0, 250, 750, 1100],
  });
  assert.throws(() => parseTtsFirstAudioBenchmarkArgs(['--output', output, '--unknown', 'private']), /TTS_FIRST_AUDIO_ARGUMENT_INVALID/);

  const report = Object.freeze({ schema_version: 'live-voice.tts-first-audio-causal-report.v0' });
  await writeTtsFirstAudioCausalReport(output, report);
  assert.equal((await fs.stat(output)).mode & 0o077, 0);
  await assert.rejects(writeTtsFirstAudioCausalReport(output, report), /TTS_FIRST_AUDIO_OUTPUT_EXISTS/);

  const invalidOutput = path.join(root, 'invalid.json');
  const cyclic = {};
  cyclic.self = cyclic;
  await assert.rejects(writeTtsFirstAudioCausalReport(invalidOutput, cyclic), /circular/i);
  await assert.rejects(fs.stat(invalidOutput), error => error?.code === 'ENOENT');
});

test('real P1 owner exposes successor ACK delay without forbidden business effects', async () => {
  const report = await runTtsFirstAudioCausalBenchmark({
    runId: 'tts-a1-owner',
    gitCommit: 'b'.repeat(40),
    samples: 1,
    successorAckDelaysMs: [0, 1100],
  });

  assert.equal(report.schema_version, 'live-voice.tts-first-audio-causal-report.v0');
  assert.deepEqual(Object.keys(report).sort(), [
    'candidate_mode',
    'decision',
    'forbidden_effects',
    'git_commit',
    'populations',
    'run_id',
    'samples',
    'schema_version',
    'source_clean',
    'summaries',
  ]);
  assert.ok(['legacy_sequential', 'successor_ack_decoupled'].includes(report.candidate_mode));
  assert.deepEqual(report.forbidden_effects, {
    agent: 0,
    tool: 0,
    task: 0,
    history: 0,
  });
  assert.equal(report.populations[0].attempts[0].outcome, 'completed');
  assert.equal(report.populations[0].attempts[0].tts_request_started_ms, 0);
  assert.ok(report.populations[0].attempts[0].successor_first_ack_ms >= 0);
  assert.ok(report.populations[0].attempts[0].first_source_scheduled_ms >= report.populations[0].attempts[0].downlink_opened_ms);
  const timeout = report.populations[1].attempts[0];
  if (report.candidate_mode === 'legacy_sequential') {
    assert.equal(timeout.outcome, 'failed');
    assert.equal(timeout.reason, 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED');
    assert.equal(timeout.downlink_opened_ms, null);
  } else {
    assert.equal(timeout.outcome, 'degraded_interruption');
    assert.equal(timeout.reason, 'AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED');
    assert.equal(typeof timeout.downlink_opened_ms, 'number');
    assert.equal(typeof timeout.first_source_scheduled_ms, 'number');
  }
});

test('benchmark input is closed before allocating the real P1 owner', async () => {
  const base = {
    runId: 'tts-a1-owner',
    gitCommit: 'b'.repeat(40),
    samples: 1,
    successorAckDelaysMs: [0],
  };
  for (const input of [
    { ...base, runId: '../private' },
    { ...base, gitCommit: 'B'.repeat(40) },
    { ...base, samples: 0 },
    { ...base, samples: 31 },
    { ...base, successorAckDelaysMs: [] },
    { ...base, successorAckDelaysMs: [1] },
    { ...base, successorAckDelaysMs: [0, 0] },
  ]) {
    await assert.rejects(runTtsFirstAudioCausalBenchmark(input), /TTS_FIRST_AUDIO_INPUT_INVALID/);
  }
});
