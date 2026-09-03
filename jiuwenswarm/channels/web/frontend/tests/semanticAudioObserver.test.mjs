import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../../../../tests/support/live_voice/audio_journey/browser_audio.js', import.meta.url), 'utf8');

test('test-only audio observer records actual PCM and does not credit silent keepalive as speech', () => {
  let starts = 0;
  class Context {
    currentTime = 1;
    state = 'running';
    createBufferSource() {
      return {start(){starts++;}, stop(){}, addEventListener(){}};
    }
  }
  const window = {AudioContext:Context, WebSocket:class {}};
  vm.runInNewContext(source, {
    window, navigator:{mediaDevices:{getUserMedia(){}}},
    crypto:{randomUUID:()=> 'test-observer'}, performance:{now:()=>1},
    setTimeout(){}, URL, btoa:value=>Buffer.from(value, 'binary').toString('base64'),
  });
  const context = new Context();
  const start = data => {
    const bufferSource = context.createBufferSource();
    bufferSource.buffer = {length:data.length, numberOfChannels:1, sampleRate:24000, getChannelData:()=>data};
    bufferSource.start();
  };
  start(new Float32Array(480));
  start(new Float32Array([0.25, -0.25]));
  const events = window.__semanticAudioTest.drain();
  assert.equal(starts, 2); // Instrumentation never suppresses product playback.
  assert.equal(events.filter(row=>row.kind==='silent-output-buffer').length, 1);
  const audio = events.filter(row=>row.kind==='output-buffer');
  assert.equal(audio.length, 1);
  assert.equal(audio[0].rms, 0.25);
  assert.equal(Buffer.from(audio[0].pcm_s16le_base64, 'base64').byteLength, 4);
  assert.equal(events.filter(row=>row.kind==='output-start-scheduled').length, 2);
  assert.equal(events.filter(row=>row.kind==='observation-failed').length, 0);
});
