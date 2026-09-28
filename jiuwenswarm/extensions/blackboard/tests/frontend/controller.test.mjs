import assert from 'node:assert/strict';
import test from 'node:test';
import { BlackboardController } from '../../../../channels/web/frontend/node_modules/.cache/blackboard/controller.js';

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
  assert.equal(f.handlers.size, 8);
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
