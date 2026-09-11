import assert from 'node:assert/strict';
import test from 'node:test';
import { HeadlessNativeVoice } from './dist/index.js';

test('missing or wrong Atlas confirmation closes activation before media allocation', async () => {
  const binding = { session_id: 's', correlation_id: 'c', interaction_id: 'i', activation_id: 'a', activation_generation: 1 };
  for (const host of [undefined, { kind: 'atlas', binding_id: 'foreign' }, { kind: 'unavailable' }]) {
    const calls = [];
    const voice = new HeadlessNativeVoice({ expectedOrigin: 'http://127.0.0.1:1234', expectedAtlasBindingId: 'expected',
      captureWorkletModuleUrl: '/worklet.js', onMessage: () => assert.fail('no message before activation'), onStatus: () => {},
      request: async (method, params) => {
        calls.push(method);
        assert.ok(method === 'live_voice.composition.p2.activate' || method === 'live_voice.composition.p2.close');
        return { ok: true, result: { ...params, status: method.endsWith('activate') ? 'active' : 'closed', execution_host: host } };
      } });
    await assert.rejects(voice.start(binding), /ATLAS_EXECUTION_HOST_NOT_CONFIRMED/);
    assert.deepEqual(calls, ['live_voice.composition.p2.activate', 'live_voice.composition.p2.close']);
  }
});
