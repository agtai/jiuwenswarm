import assert from 'node:assert/strict';
import test from 'node:test';
import { BlackboardController } from '../../../../channels/web/frontend/node_modules/.cache/blackboard/controller.js';
import {
  toggleAttachment,
  workspaceChoices,
} from '../../../../channels/web/frontend/node_modules/.cache/blackboard/sessionLink.js';

const HOSTS = {
  hosts: [
    { id: 'h1', name: 'Team', status: 'connected', is_self: false, is_default: true },
    { id: 'h2', name: 'Mine', status: 'connected', is_self: true, is_default: false },
  ],
  default_host: 'h1',
};

function workspace(id, role = 'editor', extra = {}) {
  return { id, name: id, title: id.toUpperCase(), created_at: '', archived: false, role, ...extra };
}

// A fake host world: per host, the caller's workspaces, members and invites.
function fakeWorld() {
  const calls = [];
  const world = {
    hosts: structuredClone(HOSTS),
    me: {
      h1: { user_id: 'u1', display_name: 'Ann', workspaces: [workspace('ws1', 'owner'), workspace('ws2')] },
      h2: { user_id: 'u9', display_name: 'Ann', workspaces: [workspace('ws9', 'owner')] },
    },
    members: { ws1: [{ user_id: 'u1', role: 'owner' }, { user_id: 'u2', role: 'editor' }], ws2: [{ user_id: 'u1' }] },
    invites: { ws1: [{ code: 'c1', state: 'active' }] },
    delay: {},
  };
  const rpc = async (method, params = {}) => {
    calls.push([method, params]);
    const wait = world.delay[method];
    if (wait) await wait;
    switch (method) {
      case 'blackboard.hosts.list':
        return structuredClone(world.hosts);
      case 'blackboard.host.status':
        return { running: false, enabled: false, settings: {}, error: null };
      case 'blackboard.me':
        return structuredClone(world.me[params.host]);
      case 'blackboard.member.list':
        return { members: world.members[params.workspace_id] ?? [] };
      case 'blackboard.invite.list':
        return { invites: world.invites[params.workspace_id] ?? [] };
      case 'blackboard.mandate.list':
        return { mandates: world.mandates ?? [] };
      case 'blackboard.session.list':
        return { sessions: world.attached ?? [] };
      case 'blackboard.suggestion.list':
        return { suggestions: world.suggestions ?? [] };
      case 'blackboard.doc.list':
        return { docs: world.docs?.[params.workspace_id] ?? [], docservice: null };
      case 'blackboard.chat.list':
        return { messages: structuredClone(world.chat ?? []), has_more: false };
      case 'blackboard.chat.post':
        return { message: { id: 'cm_new', workspace_id: params.workspace_id, kind: 'message', author_kind: 'person', body: params.body } };
      case 'blackboard.comment.list':
        return { threads: structuredClone(world.threads?.[params.doc_id] ?? []) };
      case 'blackboard.comment.create':
        return { thread: { id: 't_new', doc_id: params.doc_id } };
      case 'blackboard.decision.list':
        return { decisions: structuredClone(world.decisions ?? []) };
      case 'blackboard.session.attach':
        return { session: { session_id: params.session_id, host: params.host, workspace_id: params.workspace_id, title: 'T' } };
      default:
        return {};
    }
  };
  const handlers = new Map();
  const subscribe = (event, handler) => {
    handlers.set(event, handler);
    return () => handlers.delete(event);
  };
  const emit = (event, payload) => handlers.get(event)?.(payload);
  return { world, calls, rpc, subscribe, emit, handlers };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

test('start loads the hosts, picks the default host and its workspaces', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  const s = c.getState();
  assert.equal(s.loaded, true);
  assert.equal(s.hostId, 'h1');
  assert.deepEqual(s.workspaces.map((w) => w.id), ['ws1', 'ws2']);
  assert.equal(s.workspaceId, null);
  assert.equal(f.handlers.size, 14);
  c.stop();
  assert.equal(f.handlers.size, 0);
});

test('an owner sees members and invites; others see members only', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws1');
  assert.equal(c.getState().members.length, 2);
  assert.equal(c.getState().invites.length, 1);
  await c.selectWorkspace('ws2');
  assert.equal(c.getState().invites.length, 0);
  assert.equal(f.calls.filter(([m, p]) => m === 'blackboard.invite.list' && p.workspace_id === 'ws2').length, 0);
});

test('events of another host are ignored', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  const before = f.calls.length;
  f.emit('blackboard.workspace.updated', { host: 'h2', workspace_id: 'ws9' });
  await flush();
  assert.equal(f.calls.length, before);
});

test('a deleted or left workspace is deselected', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws2');
  f.world.me.h1.workspaces = [workspace('ws1', 'owner')];
  f.emit('blackboard.workspace.updated', { host: 'h1', workspace_id: 'ws2', removed: true });
  await flush();
  await flush();
  assert.equal(c.getState().workspaceId, null);
  assert.deepEqual(c.getState().workspaces.map((w) => w.id), ['ws1']);
});

test('a role change reloads the workspaces, so the new role shows', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws2');
  f.world.me.h1.workspaces = [workspace('ws1', 'owner'), workspace('ws2', 'viewer')];
  f.emit('blackboard.member.role_changed', { host: 'h1', workspace_id: 'ws2', user_id: 'u1', role: 'viewer' });
  await flush();
  await flush();
  assert.equal(c.getState().workspaces.find((w) => w.id === 'ws2').role, 'viewer');
  assert.equal(c.getState().workspaceId, 'ws2');
});

test('a response for a host the user already left is dropped', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  let release;
  f.world.delay['blackboard.me'] = new Promise((resolve) => {
    release = resolve;
  });
  const slow = c.selectHost('h2');
  // The user switches back before h2 answers.
  f.world.delay['blackboard.me'] = undefined;
  const fast = c.selectHost('h1');
  release();
  await Promise.all([slow, fast]);
  assert.equal(c.getState().hostId, 'h1');
  assert.deepEqual(c.getState().workspaces.map((w) => w.id), ['ws1', 'ws2']);
});

test('removing the selected host falls back to the default host', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectHost('h2');
  f.world.hosts = { hosts: [HOSTS.hosts[0]], default_host: 'h1' };
  f.emit('blackboard.hosts.updated', { host: 'h2', removed: true });
  await flush();
  await flush();
  assert.equal(c.getState().hostId, 'h1');
  assert.deepEqual(c.getState().workspaces.map((w) => w.id), ['ws1', 'ws2']);
});

test('an invite that never expires and has no limit sends nulls', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws1');
  await c.createInvite('viewer', null, null);
  await c.createInvite('editor', 30, 5);
  const sent = f.calls.filter(([method]) => method === 'blackboard.invite.create').map(([, params]) => params);
  assert.deepEqual(sent, [
    { host: 'h1', workspace_id: 'ws1', role: 'viewer', expires_in_minutes: null, max_uses: null },
    { host: 'h1', workspace_id: 'ws1', role: 'editor', expires_in_minutes: 30, max_uses: 5 },
  ]);
});

test('host status pushes replace the status', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  f.emit('blackboard.host.status_changed', { running: true, enabled: true, settings: {}, error: null, base_url: 'http://x' });
  await flush();
  assert.equal(c.getState().hostStatus.running, true);
});

test('an agent session is created, attached to the workspace and opened', async () => {
  const f = fakeWorld();
  const opened = [];
  const port = {
    create: async (title) => `sess-for-${title}`,
    open: (id) => opened.push(id),
    recent: async () => [{ session_id: 'a', title: 'A' }, { session_id: 'b', title: 'B' }],
  };
  const c = new BlackboardController(f.rpc, f.subscribe, port);
  await c.start();
  await c.selectWorkspace('ws1');
  assert.equal(await c.startAgentSession(), 'sess-for-WS1');
  const attach = f.calls.find(([method]) => method === 'blackboard.session.attach')[1];
  assert.deepEqual(attach, { host: 'h1', workspace_id: 'ws1', session_id: 'sess-for-WS1' });
  assert.deepEqual(opened, ['sess-for-WS1']);

  f.world.attached = [{ session_id: 'a' }];
  assert.deepEqual((await c.attachableSessions()).map((s) => s.session_id), ['b']);
});

test("deciding one run takes only that run's suggestions; mandate pushes refresh the list", async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws1');
  f.world.suggestions = [
    { id: 's1', author: { id: 'u1', kind: 'agent', mandate: 'm1' } },
    { id: 's2', author: { id: 'u2', kind: 'agent', mandate: 'm2' } },
    { id: 's3', author: { id: 'u1', kind: 'agent', mandate: 'm1' } },
  ];
  assert.equal(await c.decideMandate('d1', 'm1', 'accept'), 2);
  const decided = f.calls.find(([method]) => method === 'blackboard.suggestion.decide')[1];
  assert.deepEqual(decided, { host: 'h1', doc_id: 'd1', suggestion_ids: ['s1', 's3'], action: 'accept' });

  f.world.mandates = [{ id: 'm9', status: 'running', receipts: [] }];
  f.emit('blackboard.mandate.updated', { host: 'h1', workspace_id: 'ws1', mandate_id: 'm9' });
  await flush();
  await flush();
  assert.deepEqual(c.getState().mandates.map((m) => m.id), ['m9']);
});

function memoryOf(saved) {
  const memory = { saved, load: () => memory.saved, save: (selection) => (memory.saved = selection) };
  return memory;
}

test('the page opens where it was left, and coming back reloads it', async () => {
  const f = fakeWorld();
  f.world.docs = { ws2: [{ id: 'd1', title: 'One' }, { id: 'd2', title: 'Two' }] };
  const memory = memoryOf({ hostId: 'h1', workspaceId: 'ws2', docId: 'd2', rail: 'agents' });
  const c = new BlackboardController(f.rpc, f.subscribe, undefined, memory);
  await c.start();
  let s = c.getState();
  assert.deepEqual([s.hostId, s.workspaceId, s.docId, s.rail], ['h1', 'ws2', 'd2', 'agents']);

  c.selectDoc('d1');
  c.selectRail('references');
  assert.deepEqual(memory.saved, { hostId: 'h1', workspaceId: 'ws2', docId: 'd1', rail: 'references' });

  // Leaving and coming back keeps the place and asks the host again.
  c.stop();
  const before = f.calls.filter(([method]) => method === 'blackboard.me').length;
  await c.start();
  s = c.getState();
  assert.deepEqual([s.workspaceId, s.docId], ['ws2', 'd1']);
  assert.equal(f.calls.filter(([method]) => method === 'blackboard.me').length, before + 1);

  // A remembered workspace that is gone falls back to none.
  const gone = new BlackboardController(f.rpc, f.subscribe, undefined, memoryOf({ hostId: 'h1', workspaceId: 'ws_gone', rail: 'bogus' }));
  await gone.start();
  assert.deepEqual([gone.getState().workspaceId, gone.getState().rail], [null, 'members']);
});

test("following a chat's tag opens that workspace on the Agents tab", async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  c.openWorkspace('h2', 'ws9');
  await flush();
  await flush();
  const s = c.getState();
  assert.deepEqual([s.hostId, s.workspaceId, s.rail], ['h2', 'ws9', 'agents']);
  assert.deepEqual(s.workspaces.map((w) => w.id), ['ws9']);
});

test('the chat lists workspaces a person can edit and adds or takes them from a session', async () => {
  const f = fakeWorld();
  f.world.me.h1.workspaces.push(workspace('ws3', 'viewer'), workspace('ws4', 'editor', { archived: true }));
  const choices = await workspaceChoices(f.rpc);
  assert.deepEqual(
    choices.map((c) => [c.host, c.workspaceId, c.hostName]),
    [
      ['h1', 'ws1', 'Team'],
      ['h1', 'ws2', 'Team'],
      ['h2', 'ws9', 'Mine'],
    ],
  );

  const added = await toggleAttachment(f.rpc, 's1', choices[1], [{ host: 'h1', workspace_id: 'ws1' }]);
  assert.deepEqual(added.map((a) => a.workspace_id), ['ws1', 'ws2']);
  assert.equal(f.calls.at(-1)[0], 'blackboard.session.attach');
  const left = await toggleAttachment(f.rpc, 's1', choices[0], added);
  assert.deepEqual(left.map((a) => a.workspace_id), ['ws2']);
  assert.deepEqual(f.calls.at(-1), ['blackboard.session.detach', { host: 'h1', workspace_id: 'ws1', session_id: 's1' }]);
});

function thread(id, position, extra = {}) {
  return { id, position, resolved_at: null, created_at: '2026-01-01', anchor: { quote: id, status: 'ok' }, comments: [], ...extra };
}

test('the chat loads with the workspace, and pushed messages join it once', async () => {
  const f = fakeWorld();
  f.world.chat = [{ id: 'cm1', workspace_id: 'ws1', kind: 'message', body: 'hello' }];
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws1');
  assert.deepEqual(c.getState().chat.map((m) => m.id), ['cm1']);

  const pushed = { id: 'cm2', workspace_id: 'ws1', kind: 'message', body: 'second' };
  f.emit('blackboard.chat.message', { host: 'h1', workspace_id: 'ws1', message: pushed });
  f.emit('blackboard.chat.message', { host: 'h1', workspace_id: 'ws1', message: { ...pushed, mandate_id: 'm1' } });
  f.emit('blackboard.chat.message', { host: 'h1', workspace_id: 'ws2', message: { ...pushed, id: 'cm9', workspace_id: 'ws2' } });
  await flush();
  assert.deepEqual(c.getState().chat.map((m) => [m.id, m.mandate_id ?? null]), [['cm1', null], ['cm2', 'm1']]);

  f.world.members.ws1 = [{ user_id: 'u2', display_name: 'Bob' }];
  await c.refreshMembers();
  await c.postChat('@jiuwen ask @Bob', 'sess-9');
  const posted = f.calls.find(([method]) => method === 'blackboard.chat.post')[1];
  assert.deepEqual(posted, {
    host: 'h1',
    workspace_id: 'ws1',
    body: '@jiuwen ask @Bob',
    mentions: [{ kind: 'agent' }, { kind: 'user', id: 'u2' }],
    session_id: 'sess-9',
  });
});

test('comments follow the open document; a selection starts a comment in the margin', async () => {
  const f = fakeWorld();
  f.world.docs = { ws1: [{ id: 'd1', title: 'One' }, { id: 'd2', title: 'Two' }] };
  f.world.threads = { d1: [thread('late', 50), thread('early', 2)], d2: [thread('other', 1)] };
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws1');
  await flush();
  assert.deepEqual(c.getState().threads.map((t) => t.id), ['early', 'late']);

  c.selectDoc('d2');
  await flush();
  assert.deepEqual(c.getState().threads.map((t) => t.id), ['other']);

  const anchor = { block_id: 'b1', block_to: 'b1', digest: null, start: 'AQ==', end: 'Ag==', quote: 'words', offset: 0, length: 5 };
  c.startComment(anchor);
  assert.deepEqual([c.getState().rail, c.getState().draftAnchor], ['members', anchor]);
  await c.createComment('@jiuwen tighten', { wholeDocument: true });
  const created = f.calls.find(([method]) => method === 'blackboard.comment.create')[1];
  assert.deepEqual(created, {
    host: 'h1',
    doc_id: 'd2',
    anchor,
    body: '@jiuwen tighten',
    mentions: [{ kind: 'agent' }],
    scope_switch: true,
  });
  assert.deepEqual([c.getState().draftAnchor, c.getState().activeThread], [null, 't_new']);

  // Another document's thread changes leave this list alone; this document's reload it.
  const before = f.calls.filter(([method]) => method === 'blackboard.comment.list').length;
  f.emit('blackboard.thread.updated', { host: 'h1', workspace_id: 'ws1', doc_id: 'd1', thread_id: 'late' });
  await flush();
  assert.equal(f.calls.filter(([method]) => method === 'blackboard.comment.list').length, before);
  f.world.threads.d2.push(thread('added', 5));
  f.emit('blackboard.thread.updated', { host: 'h1', workspace_id: 'ws1', doc_id: 'd2', thread_id: 'added' });
  await flush();
  await flush();
  assert.deepEqual(c.getState().threads.map((t) => t.id), ['other', 'added']);
});

test('decision pushes reload the decisions', async () => {
  const f = fakeWorld();
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws1');
  f.world.decisions = [{ id: 'dc1', status: 'open' }];
  f.emit('blackboard.decision.updated', { host: 'h1', workspace_id: 'ws1', decision_id: 'dc1', status: 'open' });
  await flush();
  await flush();
  assert.deepEqual(c.getState().decisions.map((d) => d.id), ['dc1']);
});

test('opening a thread keeps the rail, unless the margin cannot show that thread', async () => {
  const f = fakeWorld();
  f.world.docs = { ws1: [{ id: 'd1', title: 'One' }] };
  f.world.threads = { d1: [thread('here', 1), thread('gone', 2, { anchor: { quote: 'gone', status: 'orphaned' } })] };
  const c = new BlackboardController(f.rpc, f.subscribe);
  await c.start();
  await c.selectWorkspace('ws1');
  await flush();
  c.openThread('here');
  assert.deepEqual([c.getState().activeThread, c.getState().rail], ['here', 'members']);
  c.openThread('gone');
  assert.deepEqual([c.getState().activeThread, c.getState().rail], ['gone', 'comments']);
});
