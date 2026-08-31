import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test, { after, beforeEach } from 'node:test';

import { build } from 'esbuild';
import React from 'react';
import { act, create as createRenderer } from 'react-test-renderer';

// The hook and the TTS output ownership registry must share one module
// instance, so bundle them together instead of importing two compiled copies.
const bundleDirectory = await mkdtemp(fileURLToPath(new URL('../node_modules/.cache/jiuwenswarm-tts-lease-', import.meta.url)));
after(async () => {
  await rm(bundleDirectory, { recursive: true, force: true });
});
const bundleUrl = pathToFileURL(join(bundleDirectory, 'leaseHarness.mjs'));
await build({
  stdin: {
    contents: [
      "export { useProductVoiceBrowserOwnership } from './src/components/ChatPanel/useProductVoiceBrowserOwnership';",
      "export { beginServerTtsOutput, canCompleteServerTtsOutput, isLiveVoiceTtsOutputOwned } from './src/utils/ttsOutputOwnership';",
    ].join('\n'),
    resolveDir: fileURLToPath(new URL('..', import.meta.url)),
    loader: 'ts',
  },
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  outfile: fileURLToPath(bundleUrl),
});
const {
  useProductVoiceBrowserOwnership,
  beginServerTtsOutput,
  canCompleteServerTtsOutput,
  isLiveVoiceTtsOutputOwned,
} = await import(bundleUrl.href);

const MountedOwnership = React.forwardRef((props, ref) => {
  const lifecycle = useProductVoiceBrowserOwnership(props);
  React.useImperativeHandle(ref, () => lifecycle, [lifecycle]);
  return null;
});

const speechCancelEvents = [];
beforeEach(() => {
  speechCancelEvents.length = 0;
  const windowTarget = new EventTarget();
  windowTarget.speechSynthesis = {
    cancel() {
      speechCancelEvents.push('speech-cancel');
    },
  };
  globalThis.window = windowTarget;
});
after(() => {
  delete globalThis.window;
});

function createHarness({ startError = null, closeError = null } = {}) {
  const events = [];
  let takeover = null;
  const ownership = {
    async acquire(onTakeover) {
      takeover = onTakeover;
      events.push('ownership-acquire');
    },
    async release() {
      events.push('ownership-release');
    },
    async dispose() {
      events.push('ownership-dispose');
    },
    disposeAfterRelease() {
      events.push('ownership-dispose-after-release');
    },
  };
  const control = {
    async start() {
      events.push('control-start');
      if (startError !== null) throw startError;
    },
    async close() {
      events.push('control-close');
      if (closeError !== null) throw closeError;
    },
    async closeSession(sessionId) {
      events.push(`control-close-session-${sessionId}`);
    },
  };
  const controlRef = { current: control };
  let activeSessionId = 'session-a';
  const ref = React.createRef();
  let renderer = null;
  const render = async () => {
    await act(async () => {
      const element = React.createElement(MountedOwnership, {
        ref,
        activeSessionId,
        controlRef,
        getActiveSessionId: () => activeSessionId,
        createOwnership: () => ownership,
      });
      if (renderer === null) {
        renderer = createRenderer(element);
      } else {
        renderer.update(element);
      }
    });
  };
  return {
    events,
    control,
    ref,
    render,
    getTakeover: () => takeover,
    async switchSession(nextSessionId) {
      activeSessionId = nextSessionId;
      await render();
    },
    async unmount() {
      await act(async () => {
        renderer.unmount();
      });
    },
  };
}

test('formal start owns every audible TTS: lease held, in-flight fenced, playback stopped first', async () => {
  assert.equal(isLiveVoiceTtsOutputOwned(), false);
  const inFlightTicket = beginServerTtsOutput();
  assert.notEqual(inFlightTicket, null);

  const harness = createHarness();
  await harness.render();
  await act(async () => {
    await harness.ref.current.start();
  });

  assert.equal(isLiveVoiceTtsOutputOwned(), true, 'formal start must hold the global TTS lease');
  assert.equal(beginServerTtsOutput(), null, 'ordinary server TTS must not start while formal is active');
  assert.equal(canCompleteServerTtsOutput(inFlightTicket), false, 'in-flight ordinary TTS must not complete');
  assert.deepEqual(speechCancelEvents, ['speech-cancel'], 'pre-existing SpeechSynthesis must stop at formal start');
  assert.equal(
    harness.events.indexOf('ownership-acquire') < harness.events.indexOf('control-start'),
    true,
  );

  await act(async () => {
    await harness.ref.current.stop();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), false, 'stop must release the exact lease');
  assert.notEqual(beginServerTtsOutput(), null);
  assert.equal(canCompleteServerTtsOutput(inFlightTicket), false, 'the fenced in-flight response stays fenced');
  await harness.unmount();
});

test('failed formal start retains the lease until explicit cleanup completes', async () => {
  const harness = createHarness({ startError: new Error('FORMAL_START_FAILED') });
  await harness.render();
  await act(async () => {
    await harness.ref.current.start();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), true, 'a failed start keeps fencing ordinary TTS');

  await act(async () => {
    await harness.ref.current.stop();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), false);
  await harness.unmount();
});

test('restart after failed start holds exactly one token so one stop fully releases', async () => {
  const harness = createHarness({ startError: new Error('FORMAL_START_FAILED') });
  await harness.render();
  await act(async () => {
    await harness.ref.current.start();
  });
  await act(async () => {
    await harness.ref.current.start();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), true);

  await act(async () => {
    await harness.ref.current.stop();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), false, 'a restart must not leak a second lease token');
  await harness.unmount();
});

test('session switch releases the lease through the shared cleanup sequence', async () => {
  const harness = createHarness();
  await harness.render();
  await act(async () => {
    await harness.ref.current.start();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), true);

  await harness.switchSession('session-b');
  await act(async () => {});
  assert.equal(isLiveVoiceTtsOutputOwned(), false, 'switching Sessions must release the retiring lease');
  await harness.unmount();
});

test('takeover releases the lease after formal cleanup', async () => {
  const harness = createHarness();
  await harness.render();
  await act(async () => {
    await harness.ref.current.start();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), true);

  await act(async () => {
    await harness.getTakeover()();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), false, 'takeover by another tab must release this lease');
  await harness.unmount();
});

test('unmount releases the lease only after cleanup succeeds', async () => {
  const harness = createHarness();
  await harness.render();
  await act(async () => {
    await harness.ref.current.start();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), true);

  await harness.unmount();
  await act(async () => {});
  assert.equal(isLiveVoiceTtsOutputOwned(), false);
});

// Deliberately last: this case leaves the lease held on purpose (cleanup never
// proves complete), which is the fail-safe direction for a surface that may
// still be capturing.
test('unmount with failing cleanup retains the lease instead of freeing output blind', async () => {
  const harness = createHarness({ closeError: new Error('FORMAL_CLEANUP_FAILED') });
  await harness.render();
  await act(async () => {
    await harness.ref.current.start();
  });
  assert.equal(isLiveVoiceTtsOutputOwned(), true);

  await harness.unmount();
  await act(async () => {});
  assert.equal(isLiveVoiceTtsOutputOwned(), true, 'an unproven cleanup must not release audible output');
});
