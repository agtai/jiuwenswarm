import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createPostCapturePipelineBenchmark,
  parsePostCaptureBenchmarkConfig,
} from '../node_modules/.cache/live-voice-post-capture-benchmark/postCapturePipelineBenchmark.mjs';

const validSearch =
  '?live_voice_post_capture_benchmark=1&run_id=run-20260820-a&profile_id=dialogue_no_tool&input_case_id=dialogue-paris-en-v1&round_index=0&session_id=web_benchmark_session&fixture_url=http%3A%2F%2F127.0.0.1%3A41731%2Ffixture%2Fdialogue-paris-en-v1.wav&result_url=http%3A%2F%2F127.0.0.1%3A41731%2Fresult&start_delay_ms=1000';

function fixtureResponse(byteLength = 8) {
  return {
    wav_bytes: new ArrayBuffer(byteLength),
    expected_transcript_sha256: 'a'.repeat(64),
  };
}

test('post-capture parser is default-off before reading the location', () => {
  const location = {
    get search() {
      throw new Error('private location');
    },
    origin: 'http://localhost:5173',
    pathname: '/chat/web_benchmark_session',
  };
  assert.equal(parsePostCaptureBenchmarkConfig(false, location), null);
});

test('post-capture parser accepts one closed loopback configuration', () => {
  const config = parsePostCaptureBenchmarkConfig(true, { search: validSearch, origin: 'http://localhost:5173', pathname: '/chat/web_benchmark_session' });
  assert.deepEqual(config, {
    run_id: 'run-20260820-a',
    profile_id: 'dialogue_no_tool',
    input_case_id: 'dialogue-paris-en-v1',
    round_index: 0,
    session_id: 'web_benchmark_session',
    fixture_url: 'http://127.0.0.1:41731/fixture/dialogue-paris-en-v1.wav',
    result_url: 'http://127.0.0.1:41731/result',
    start_delay_ms: 1000,
  });
});

test('post-capture parser rejects duplicate, foreign, mismatched and non-canonical configuration', () => {
  const base = { origin: 'http://localhost:5173', pathname: '/chat/web_benchmark_session' };
  for (const search of [
    `${validSearch}&round_index=1`,
    validSearch.replace('round_index=0', 'round_index=00'),
    validSearch.replace('127.0.0.1', 'example.test'),
    validSearch.replace('dialogue-paris-en-v1.wav', 'other.wav'),
    `${validSearch}&unknown=1`,
  ])
    assert.equal(parsePostCaptureBenchmarkConfig(true, { ...base, search }), null);
  assert.equal(
    parsePostCaptureBenchmarkConfig(true, {
      ...base,
      pathname: '/project/web_benchmark_session',
      search: validSearch,
    }),
    null,
  );
});

test('controller fetches once, starts product once, and posts only its completed batch receipt', async () => {
  const config = parsePostCaptureBenchmarkConfig(true, { search: validSearch, origin: 'http://localhost:5173', pathname: '/chat/web_benchmark_session' });
  const calls = [];
  const controller = createPostCapturePipelineBenchmark(config, {
    async fetchFixture(url) {
      calls.push(['fetch', url]);
      return fixtureResponse();
    },
    async postResult(result) {
      calls.push(['result', result]);
    },
    async digestTranscript(value) {
      calls.push(['digest', value]);
      return 'a'.repeat(64);
    },
  });
  await controller.start({
    async startFixture(bytes) {
      calls.push(['start', bytes.byteLength]);
    },
    async close() {
      calls.push(['close']);
    },
  });
  assert.equal(await controller.acceptRecognizedText('In two short sentences, please introduce Paris.'), true);
  await controller.observeBatch(
    { run_id: config.run_id, profile_id: config.profile_id, input_case_id: config.input_case_id, round_index: 1, terminal_outcome: 'completed' },
    { disposition: 'written' },
  );
  assert.equal(calls.filter(call => call[0] === 'result').length, 0);
  await controller.observePresentationAck();
  assert.equal(calls.filter(call => call[0] === 'result').length, 0);
  await controller.observeBatch(
    { run_id: config.run_id, profile_id: config.profile_id, input_case_id: config.input_case_id, round_index: 0, terminal_outcome: 'completed' },
    { disposition: 'written' },
  );
  assert.deepEqual(calls, [
    ['fetch', config.fixture_url],
    ['start', 8],
    ['digest', 'in two short sentences please introduce paris'],
    [
      'result',
      {
        schema_version: 'live-voice.post-capture-result.v0',
        run_id: config.run_id,
        profile_id: config.profile_id,
        input_case_id: config.input_case_id,
        round_index: 0,
        outcome: 'completed',
      },
    ],
    ['close'],
  ]);
});

test('a completed Browser batch waits for the authoritative P2 presentation ACK', async () => {
  const config = parsePostCaptureBenchmarkConfig(true, {
    search: validSearch,
    origin: 'http://localhost:5173',
    pathname: '/chat/web_benchmark_session',
  });
  const calls = [];
  const controller = createPostCapturePipelineBenchmark(config, {
    async fetchFixture() {
      return fixtureResponse();
    },
    async postResult(result) {
      calls.push(['result', result.outcome]);
    },
    async digestTranscript() {
      return 'a'.repeat(64);
    },
  });
  await controller.start({
    async startFixture() {
      calls.push(['start']);
    },
    async close() {
      calls.push(['close']);
    },
  });
  const batch = {
    run_id: config.run_id,
    profile_id: config.profile_id,
    input_case_id: config.input_case_id,
    round_index: config.round_index,
    terminal_outcome: 'completed',
  };

  await controller.observeBatch(batch, { disposition: 'written' });
  assert.deepEqual(calls, [['start']]);
  await controller.observePresentationAck();

  assert.deepEqual(calls, [['start'], ['result', 'completed'], ['close']]);
});

test('a completed Browser batch without a successful P2 ACK can close only unknown', async () => {
  const config = parsePostCaptureBenchmarkConfig(true, {
    search: validSearch,
    origin: 'http://localhost:5173',
    pathname: '/chat/web_benchmark_session',
  });
  const outcomes = [];
  const controller = createPostCapturePipelineBenchmark(config, {
    async fetchFixture() {
      return fixtureResponse();
    },
    async postResult(result) {
      outcomes.push(result.outcome);
    },
    async digestTranscript() {
      return 'a'.repeat(64);
    },
  });
  await controller.start({
    async startFixture() {},
    async close() {},
  });
  await controller.observeBatch(
    {
      run_id: config.run_id,
      profile_id: config.profile_id,
      input_case_id: config.input_case_id,
      round_index: config.round_index,
      terminal_outcome: 'completed',
    },
    { disposition: 'written' },
  );

  assert.deepEqual(outcomes, []);
  await controller.close();
  assert.deepEqual(outcomes, ['unknown']);
});

test('controller failure and external close emit only unknown and close once', async () => {
  const config = parsePostCaptureBenchmarkConfig(true, { search: validSearch, origin: 'http://localhost:5173', pathname: '/chat/web_benchmark_session' });
  const results = [];
  const controller = createPostCapturePipelineBenchmark(config, {
    async fetchFixture() {
      throw new Error('private wav path');
    },
    async postResult(result) {
      results.push(result);
    },
    async digestTranscript() {
      return 'a'.repeat(64);
    },
  });
  let closes = 0;
  await controller.start({
    async startFixture() {
      throw new Error('must not start');
    },
    async close() {
      closes += 1;
    },
  });
  await controller.close();
  assert.deepEqual(results, [
    {
      schema_version: 'live-voice.post-capture-result.v0',
      run_id: config.run_id,
      profile_id: config.profile_id,
      input_case_id: config.input_case_id,
      round_index: 0,
      outcome: 'unknown',
    },
  ]);
  assert.equal(closes, 1);
});

test('semantic mismatch terminalizes unknown before any completed batch can receive credit', async () => {
  const config = parsePostCaptureBenchmarkConfig(true, {
    search: validSearch,
    origin: 'http://localhost:5173',
    pathname: '/chat/web_benchmark_session',
  });
  const calls = [];
  const controller = createPostCapturePipelineBenchmark(config, {
    async fetchFixture() {
      return fixtureResponse();
    },
    async postResult(result) {
      calls.push(['result', result.outcome]);
    },
    async digestTranscript(value) {
      calls.push(['digest', value]);
      return 'b'.repeat(64);
    },
  });
  await controller.start({
    async startFixture() {
      calls.push(['start']);
    },
    async close() {
      calls.push(['close']);
    },
  });

  assert.equal(await controller.acceptRecognizedText('Wrong transcript.'), false);
  await controller.observeBatch(
    {
      run_id: config.run_id,
      profile_id: config.profile_id,
      input_case_id: config.input_case_id,
      round_index: config.round_index,
      terminal_outcome: 'completed',
    },
    { disposition: 'written' },
  );

  assert.deepEqual(calls, [['start'], ['digest', 'wrong transcript'], ['result', 'unknown'], ['close']]);
});

test('a concurrent close fences a matching transcript digest before product submission', async () => {
  const config = parsePostCaptureBenchmarkConfig(true, {
    search: validSearch,
    origin: 'http://localhost:5173',
    pathname: '/chat/web_benchmark_session',
  });
  const calls = [];
  let releaseDigest;
  const controller = createPostCapturePipelineBenchmark(config, {
    async fetchFixture() {
      return fixtureResponse();
    },
    async postResult(result) {
      calls.push(['result', result.outcome]);
    },
    digestTranscript(value) {
      calls.push(['digest', value]);
      return new Promise(resolve => {
        releaseDigest = resolve;
      });
    },
  });
  await controller.start({
    async startFixture() {
      calls.push(['start']);
    },
    async close() {
      calls.push(['close']);
    },
  });

  const acceptance = controller.acceptRecognizedText('Expected transcript.');
  await Promise.resolve();
  await controller.close();
  releaseDigest('a'.repeat(64));

  assert.equal(await acceptance, false);
  assert.deepEqual(calls, [['start'], ['digest', 'expected transcript'], ['result', 'unknown'], ['close']]);
});

test('an exact unknown export receipt terminalizes once while a foreign receipt is inert', async () => {
  const config = parsePostCaptureBenchmarkConfig(true, {
    search: validSearch,
    origin: 'http://localhost:5173',
    pathname: '/chat/web_benchmark_session',
  });
  const calls = [];
  const controller = createPostCapturePipelineBenchmark(config, {
    async fetchFixture() {
      return fixtureResponse();
    },
    async postResult(result) {
      calls.push(['result', result.outcome]);
    },
    async digestTranscript() {
      return 'a'.repeat(64);
    },
  });
  await controller.start({
    async startFixture() {
      calls.push(['start']);
    },
    async close() {
      calls.push(['close']);
    },
  });
  const exact = {
    run_id: config.run_id,
    profile_id: config.profile_id,
    input_case_id: config.input_case_id,
    round_index: config.round_index,
    terminal_outcome: 'completed',
  };

  await controller.observeBatch({ ...exact, round_index: 1 }, { disposition: 'unknown' });
  assert.deepEqual(calls, [['start']]);
  await controller.observeBatch(exact, { disposition: 'unknown' });
  await controller.observeBatch(exact, { disposition: 'written' });

  assert.deepEqual(calls, [['start'], ['result', 'unknown'], ['close']]);
});
