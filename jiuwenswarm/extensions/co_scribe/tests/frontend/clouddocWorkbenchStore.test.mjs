import assert from 'node:assert/strict';
import test from 'node:test';

import { CHAT_HEIGHT_RANGE, RAIL_WIDTH_RANGE, useDocWorkbenchStore } from '../../../../channels/web/frontend/node_modules/.cache/clouddoc-workbench-store/docWorkbenchStore.mjs';

const doc = (docId) => ({ docId, title: docId, kind: 'document', url: `https://x/${docId}`, provider: 'p' });

function reset() {
  useDocWorkbenchStore.setState({ open: false, tabs: [], activeDocId: null, sessionId: null, bySession: {} });
}

// The welcome page ("new" conversation) has no session id yet. A document opened
// there and the first message sent from the workbench's own composer promote the
// placeholder to a real session; the tabs must go with it, or the person is
// thrown out of the workbench by the very message they typed into it.
test('the first message keeps the placeholder tabs in the created session', () => {
  reset();
  const s = useDocWorkbenchStore.getState();
  s.setSession(null);
  s.openDoc(doc('a'));
  assert.equal(useDocWorkbenchStore.getState().open, true);

  s.adoptSession('s1');
  // App's session effect follows with the same id and must find nothing to swap.
  s.setSession('s1');
  const after = useDocWorkbenchStore.getState();
  assert.equal(after.sessionId, 's1');
  assert.equal(after.open, true);
  assert.deepEqual(after.tabs.map((t) => t.docId), ['a']);
  assert.equal(after.activeDocId, 'a');
});

test('adoption is only for the placeholder; a real session keeps its own shard', () => {
  reset();
  const s = useDocWorkbenchStore.getState();
  s.setSession('s1');
  s.openDoc(doc('a'));
  s.adoptSession('s2');
  assert.equal(useDocWorkbenchStore.getState().sessionId, 's1');
  assert.deepEqual(useDocWorkbenchStore.getState().tabs.map((t) => t.docId), ['a']);
});

test('switching from the placeholder to an existing session still starts it empty', () => {
  reset();
  const s = useDocWorkbenchStore.getState();
  s.setSession(null);
  s.openDoc(doc('a'));
  s.setSession('old');
  const after = useDocWorkbenchStore.getState();
  assert.equal(after.open, false);
  assert.deepEqual(after.tabs, []);
});

test('showHistory opens the rail on the history tab and bumps the reveal counter', () => {
  reset();
  useDocWorkbenchStore.setState({ railVisible: false, railTab: 'receipts', historyRevealNonce: 0 });
  const s = useDocWorkbenchStore.getState();
  s.showHistory();
  let after = useDocWorkbenchStore.getState();
  assert.equal(after.railVisible, true);
  assert.equal(after.railTab, 'history');
  assert.equal(after.historyRevealNonce, 1);
  // Already showing: still a bump, so a second send scrolls again.
  s.showHistory();
  after = useDocWorkbenchStore.getState();
  assert.equal(after.railVisible, true);
  assert.equal(after.historyRevealNonce, 2);
});

test('dragged sizes are clamped to their bounds and null restores the default', () => {
  reset();
  const s = useDocWorkbenchStore.getState();
  s.setRailWidth(300);
  assert.equal(useDocWorkbenchStore.getState().railWidth, 300);
  s.setRailWidth(RAIL_WIDTH_RANGE.min - 100);
  assert.equal(useDocWorkbenchStore.getState().railWidth, RAIL_WIDTH_RANGE.min);
  s.setRailWidth(RAIL_WIDTH_RANGE.max + 100);
  assert.equal(useDocWorkbenchStore.getState().railWidth, RAIL_WIDTH_RANGE.max);
  s.setRailWidth(null);
  assert.equal(useDocWorkbenchStore.getState().railWidth, null);

  s.setChatHeight(120.6);
  assert.equal(useDocWorkbenchStore.getState().chatHeight, 121);
  s.setChatHeight(CHAT_HEIGHT_RANGE.max + 1);
  assert.equal(useDocWorkbenchStore.getState().chatHeight, CHAT_HEIGHT_RANGE.max);
  s.setChatHeight(Number.NaN);
  assert.equal(useDocWorkbenchStore.getState().chatHeight, null);
});

test('parked sessions come back untouched around a promotion', () => {
  reset();
  const s = useDocWorkbenchStore.getState();
  s.setSession('s1');
  s.openDoc(doc('a'));
  s.setSession(null);
  s.openDoc(doc('b'));
  s.adoptSession('s2');
  s.setSession('s2');
  assert.deepEqual(useDocWorkbenchStore.getState().tabs.map((t) => t.docId), ['b']);
  s.setSession('s1');
  assert.deepEqual(useDocWorkbenchStore.getState().tabs.map((t) => t.docId), ['a']);
  assert.equal(useDocWorkbenchStore.getState().open, true);
  s.setSession('s2');
  assert.deepEqual(useDocWorkbenchStore.getState().tabs.map((t) => t.docId), ['b']);
});
