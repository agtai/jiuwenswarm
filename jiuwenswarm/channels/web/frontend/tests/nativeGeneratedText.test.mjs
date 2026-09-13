import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const output = 'node_modules/.cache/live-voice-native-text/nativeGeneratedText.mjs';
await build({ entryPoints: ['src/features/live-voice/formal/nativeGeneratedText.ts'], bundle: true, platform: 'node', format: 'esm', outfile: output });
const { parseNativeGeneratedText } = await import(pathToFileURL(resolve(output)).href);
const binding = { session_id: 'session', interaction_id: 'interaction', correlation_id: 'correlation', activation_id: 'activation', activation_generation: 1 };
const result = () => ({ status: 'native_text', binding, revision: 2, snapshots: [{ response: {
  interaction_id: 'interaction', response_id: 'response', response_generation: 1 }, turn_id: 'turn', text: 'Hello world', state: 'generating', revision: 2, timestamp: '2026-09-06T12:00:00Z' }] });

test('Native text snapshots are independent of audio and bind every displayed row to the exact activation', () => {
  const parsed = parseNativeGeneratedText(result(), binding, 1);
  assert.equal(parsed.messages[0].content, 'Hello world');
  assert.equal(parsed.messages[0].nativeVoice.state, 'generating');
  assert.equal(parsed.messages[0].id, 'live-voice:interaction:response:1:native-generated');
  assert.deepEqual(parseNativeGeneratedText({ ...result(), snapshots: [] }, binding, 2), { revision: 2, messages: [] });
});

for (const mutate of [
  value => { value.binding = { ...binding, session_id: 'foreign' }; },
  value => { value.binding = { ...binding, activation_generation: 2 }; },
  value => { value.snapshots[0].response.interaction_id = 'foreign'; },
  value => { value.snapshots[0].revision = 3; },
  value => { value.snapshots[0].revision = 1; },
  value => { value.snapshots[0].text = 'x'.repeat(65_537); },
  value => { value.snapshots[0].text = 'private\u0000text'; },
  value => { value.snapshots[0].state = 'heard'; },
  value => { value.snapshots.push(value.snapshots[0]); },
  value => { value.snapshots[0].extra = true; },
]) test(`Native text rejects malformed or stale snapshots: ${String(mutate)}`, () => {
  const value = result(); mutate(value);
  assert.throws(() => parseNativeGeneratedText(value, binding, 1), /MEDIA_NATIVE_TEXT_INVALID/);
});
