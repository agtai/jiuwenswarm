import assert from 'node:assert/strict';
import test from 'node:test';
import { DocSession } from '../../../../channels/web/frontend/node_modules/.cache/blackboard/session.js';

// A provider stand-in: records the options and lets the test play its callbacks.
function harness(tokens) {
  let clock = 0;
  const fetched = [];
  const provider = { options: null, destroyed: false };
  const fetchToken = async (docId) => {
    fetched.push(docId);
    const next = tokens.shift();
    if (next instanceof Error) throw next;
    return { url: 'ws://host:19010', expires_in: 3600, frozen: false, ...next };
  };
  const factory = (options) => {
    provider.options = options;
    return { destroy: () => (provider.destroyed = true) };
  };
  const session = new DocSession('d1', fetchToken, factory, () => clock);
  return { session, provider, fetched, tick: (ms) => (clock += ms), events: () => provider.options.events };
}

function codeError(code) {
  return Object.assign(new Error(code), { code });
}

test('the first token opens the provider and is reused once; later connects fetch a new one', async () => {
  const h = harness([{ token: 't1', role: 'editor' }, { token: 't2', role: 'editor' }]);
  await h.session.start();
  assert.equal(h.provider.options.url, 'ws://host:19010');
  assert.equal(await h.provider.options.token(), 't1');
  h.tick(60_000);
  assert.equal(await h.provider.options.token(), 't2');
  assert.deepEqual(h.fetched, ['d1', 'd1']);
});

test('the status follows the socket, the sync and unsaved changes', async () => {
  const h = harness([{ token: 't1', role: 'editor' }]);
  await h.session.start();
  assert.equal(h.session.getState().status, 'connecting');
  h.events().onStatus('connected');
  assert.equal(h.session.getState().status, 'syncing');
  h.events().onSynced(true);
  assert.equal(h.session.getState().status, 'saved');
  h.events().onUnsyncedChanges(2);
  assert.equal(h.session.getState().status, 'syncing');
  h.events().onUnsyncedChanges(0);
  h.events().onStatus('disconnected');
  assert.equal(h.session.getState().status, 'offline');
});

test('read-only comes from the role, an archived document and the provider scope', async () => {
  const h = harness([
    { token: 't1', role: 'editor' },
    { token: 't2', role: 'viewer' },
    { token: 't3', role: 'owner', frozen: true },
  ]);
  await h.session.start();
  assert.equal(h.session.getState().readOnly, false);
  h.events().onAuthenticated('readonly');
  assert.equal(h.session.getState().readOnly, true);

  // A recheck: the service asks for the token again, and the new role applies.
  h.tick(60_000);
  await h.provider.options.token();
  assert.equal(h.session.getState().role, 'viewer');
  assert.equal(h.session.getState().readOnly, true);
  h.tick(60_000);
  await h.provider.options.token();
  assert.equal(h.session.getState().frozen, true);
  assert.equal(h.session.getState().readOnly, true);
});

test('losing access closes the session and destroys the provider', async () => {
  const h = harness([{ token: 't1', role: 'editor' }, codeError('not_member')]);
  await h.session.start();
  h.tick(60_000);
  await assert.rejects(h.provider.options.token());
  assert.equal(h.session.getState().status, 'closed');
  assert.equal(h.session.getState().reason, 'not_member');
  await new Promise((resolve) => setTimeout(resolve, 5));
  assert.equal(h.provider.destroyed, true);
});

test('a host without the document service reports unavailable and opens nothing', async () => {
  const h = harness([codeError('unavailable')]);
  await h.session.start();
  assert.equal(h.provider.options, null);
  assert.equal(h.session.getState().status, 'unavailable');
});
