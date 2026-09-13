import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { playTtsText, stopAllTts, webClient, TtsPlaybackQueue, playMessageTts, useChatStore, useSpeechSynthesis } from '../node_modules/.cache/tts-playback/ttsPlayback.mjs';

const tick = () => new Promise(resolve => setImmediate(resolve));

test('full text is synthesized in bounded sequence only after the previous audio ends', async () => {
  const text = `${'甲'.repeat(620)} 官网：https://example.com\n\`\`\`ts\nconst tail = 1;\n\`\`\``;
  const requests = [], audio = [];
  webClient.request = async (method, params) => {
    assert.equal(method, 'tts.synthesize');
    requests.push(params.text);
    return { success: true, audio_base64: 'test' };
  };
  globalThis.Audio = class {
    constructor() { audio.push(this); }
    play() { return Promise.resolve(); }
    pause() {}
  };
  const completed = playTtsText(text, 'session');
  await tick();
  assert.equal(requests.length, 1);
  for (let i = 0; i < audio.length; i += 1) {
    assert.equal(requests.length, i + 1);
    audio[i].onended();
    await tick();
  }
  assert.equal(await completed, true);
  assert.equal(requests.join(''), text);
  assert.ok(requests.every(chunk => chunk.length <= 300));
});

test('stop during synthesis fences late audio and all remaining chunks', async () => {
  let resolve;
  let calls = 0;
  webClient.request = () => { calls += 1; return new Promise(done => { resolve = done; }); };
  globalThis.Audio = class { constructor() { assert.fail('late audio must not play'); } };
  const completed = playTtsText('甲'.repeat(620));
  stopAllTts();
  resolve({ success: true, audio_base64: 'late' });
  assert.equal(await completed, false);
  assert.equal(calls, 1);
});

test('stop during playback settles the queue and a late ended callback cannot continue it', async () => {
  let audio, calls = 0;
  webClient.request = async () => { calls += 1; return { success: true, audio_base64: 'test' }; };
  globalThis.Audio = class {
    constructor() { audio = this; }
    play() { return Promise.resolve(); }
    pause() {}
  };
  const completed = playTtsText('甲'.repeat(620));
  await tick();
  const late = audio.onended;
  stopAllTts();
  late();
  assert.equal(await completed, false);
  assert.equal(calls, 1);
});

test('replacement, changed ownership and synthesis failure never enqueue remaining text', async () => {
  const queue = new TtsPlaybackQueue();
  let release, oldSignal;
  const old = queue.play('A'.repeat(620), (_chunk, signal) => {
    oldSignal = signal;
    return new Promise(resolve => { release = resolve; });
  });
  const seen = [];
  assert.equal(await queue.play('replacement', async chunk => { seen.push(chunk); return true; }), true);
  assert.equal(oldSignal.aborted, true);
  release(true);
  assert.equal(await old, false);
  assert.deepEqual(seen, ['replacement']);
  let current = true, calls = 0;
  assert.equal(await queue.play('A'.repeat(620), async () => { calls += 1; current = false; return true; }, () => current), false);
  assert.equal(calls, 1);
  assert.equal(await queue.play('A'.repeat(620), async () => false), false);
});

test('duplicate message finals during and after playback do not restart; changed text replaces once', async () => {
  const session = 'tts-message-dedupe', id = 'answer';
  const store = useChatStore.getState();
  store.ensureRuntime(session);
  store.addMessage(session, { id, role: 'assistant', content: '甲'.repeat(620), timestamp: new Date().toISOString() });
  const requests = [], audio = [];
  webClient.request = async (_method, params) => { requests.push(params.text); return { success: true, audio_base64: 'test' }; };
  globalThis.Audio = class {
    constructor() { audio.push(this); }
    play() { return Promise.resolve(); }
    pause() {}
  };
  try {
    const content = '甲'.repeat(620);
    const first = playMessageTts(session, id, content, () => true);
    await tick();
    assert.equal(await playMessageTts(session, id, content, () => true), false);
    assert.equal(requests.length, 1);
    for (let i = 0; i < audio.length; i += 1) { audio[i].onended(); await tick(); }
    assert.equal(await first, true);
    assert.equal(await playMessageTts(session, id, content, () => true), false);
    assert.equal(requests.join(''), content);
    const changed = playMessageTts(session, id, '更正后的完整内容。', () => true);
    await tick();
    audio.at(-1).onended();
    assert.equal(await changed, true);
    assert.equal(requests.at(-1), '更正后的完整内容。');
    assert.equal(await playMessageTts(session, id, '过期内容', () => false), false);
    assert.equal(requests.length, 4);
  } finally {
    stopAllTts();
    useChatStore.getState().removeRuntime(session);
  }
});

test('mounted browser speech hook plays complete chunks and fences stop/unmount callbacks', async () => {
  const dom = new JSDOM('<div id="root"></div>');
  const oldEvent = globalThis.Event;
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.Event = dom.window.Event;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const utterances = [];
  let controls, starts = 0, ends = 0;
  window.speechSynthesis = {
    getVoices: () => [], cancel() {}, pause() {}, resume() {},
    speak(utterance) { utterances.push(utterance); utterance.onstart(); },
  };
  globalThis.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
  function Harness() {
    controls = useSpeechSynthesis({ onStart: () => { starts += 1; }, onEnd: () => { ends += 1; } });
    return null;
  }
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () => root.render(React.createElement(Harness)));
    const text = '中'.repeat(620) + '官网：https://example.com';
    await act(async () => controls.speak(text));
    assert.equal(utterances.length, 1);
    for (let i = 0; i < utterances.length; i += 1) {
      await act(async () => utterances[i].onend());
    }
    assert.equal(utterances.map(item => item.text).join(''), text);
    assert.ok(utterances.every(item => item.text.length <= 300));
    assert.equal(starts, 1);
    assert.equal(ends, 1);
    await act(async () => controls.speak('A'.repeat(620)));
    const late = utterances.at(-1).onend;
    const count = utterances.length;
    await act(async () => stopAllTts());
    await act(async () => late());
    assert.equal(utterances.length, count);
    assert.equal(ends, 1);
    await act(async () => controls.speak('B'.repeat(620)));
    const unmounted = utterances.at(-1).onend;
    await act(async () => root.unmount());
    unmounted();
    await tick();
    assert.equal(utterances.length, count + 1);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
    globalThis.Event = oldEvent;
    delete globalThis.window;
    delete globalThis.document;
    delete globalThis.SpeechSynthesisUtterance;
    delete globalThis.IS_REACT_ACT_ENVIRONMENT;
  }
});
