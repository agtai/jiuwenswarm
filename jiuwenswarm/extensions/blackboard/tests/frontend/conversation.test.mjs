// Mentions, coded notices, thread order, margin card places and the base64 of relative positions.
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  coded,
  fromBase64,
  mentionAt,
  mentionsIn,
  namesAgent,
  placeCards,
  sortThreads,
  toBase64,
} from '../../../../channels/web/frontend/node_modules/.cache/blackboard/conversation.js';

const MEMBERS = [
  { user_id: 'u1', display_name: 'Alice' },
  { user_id: 'u2', display_name: 'Bob Stone' },
];

test('the agent is named like the host names it', () => {
  assert.equal(namesAgent('@jiuwen shorten this'), true);
  assert.equal(namesAgent('Please, @Jiuwen: shorten this'), true);
  assert.equal(namesAgent('mail bob@jiuwen.dev'), false);
  assert.equal(namesAgent('@jiuwenish'), false);
});

test('mentions list the agent and members written as @Name', () => {
  assert.deepEqual(mentionsIn('@jiuwen ask @Bob Stone and @alice', MEMBERS), [
    { kind: 'agent' },
    { kind: 'user', id: 'u1' },
    { kind: 'user', id: 'u2' },
  ]);
  assert.deepEqual(mentionsIn('write to alice@example.com', MEMBERS), []);
  assert.deepEqual(mentionsIn('@Alicea is someone else', MEMBERS), []);
});

test('the handle being typed opens the mention list', () => {
  assert.deepEqual(mentionAt('Hi @ali', 7), { start: 3, query: 'ali' });
  assert.deepEqual(mentionAt('@', 1), { start: 0, query: '' });
  assert.equal(mentionAt('mail a@b', 8), null);
  assert.equal(mentionAt('@ali done', 9), null);
});

test('notices carry a code and parameters; anything else is text', () => {
  assert.deepEqual(coded('{"code":"agent_failed","reason":"timeout"}'), { code: 'agent_failed', params: { reason: 'timeout' } });
  assert.equal(coded('plain words'), null);
  assert.equal(coded('{"no":"code"}'), null);
});

test('open threads follow the document, resolved ones come last, newest first', () => {
  const thread = (id, position, resolved_at = null, created_at = '2026-01-01') => ({ id, position, resolved_at, created_at });
  const sorted = sortThreads([
    thread('late', 40),
    thread('gone', null),
    thread('old', null, '2026-01-02'),
    thread('first', 3),
    thread('new', null, '2026-01-05'),
  ]);
  assert.deepEqual(sorted.map((t) => t.id), ['first', 'late', 'gone', 'new', 'old']);
});

test('relative positions survive the trip through base64', () => {
  const bytes = Uint8Array.from([0, 1, 127, 128, 255, 42]);
  assert.deepEqual([...fromBase64(toBase64(bytes))], [...bytes]);
});

test('margin cards sit level with their passage and push later ones down', () => {
  const heights = new Map([['a', 100], ['b', 50], ['c', 50]]);
  const wanted = [{ id: 'a', top: 0 }, { id: 'b', top: 40 }, { id: 'c', top: 400 }];
  assert.deepEqual([...placeCards(wanted, heights, null)], [['a', 0], ['b', 108], ['c', 400]]);
});

test('the active card stays level with its passage and earlier cards move up', () => {
  const heights = new Map([['a', 100], ['b', 50], ['c', 50]]);
  const wanted = [{ id: 'a', top: 0 }, { id: 'b', top: 40 }, { id: 'c', top: 60 }];
  const tops = placeCards(wanted, heights, 'b');
  assert.equal(tops.get('b'), 40);
  assert.equal(tops.get('a'), 40 - 8 - 100);
  assert.equal(tops.get('c'), 40 + 50 + 8);
  // An unknown active card lays out as if none were active.
  assert.deepEqual([...placeCards(wanted, heights, 'gone')], [...placeCards(wanted, heights, null)]);
});

test('versions group by the local day, newest first, and a pushed one joins once', async () => {
  const { groupByDay, withVersion, localDay } = await import('../../../../channels/web/frontend/node_modules/.cache/blackboard/history.js');
  const at = (y, m, d, h) => new Date(y, m - 1, d, h).toISOString();
  const versions = [
    { id: 'c', created_at: at(2026, 9, 29, 15) },
    { id: 'b', created_at: at(2026, 9, 29, 9) },
    { id: 'a', created_at: at(2026, 9, 28, 18) },
  ];
  assert.deepEqual(groupByDay(versions).map((g) => [g.day, g.versions.map((v) => v.id)]), [
    ['2026-09-29', ['c', 'b']],
    ['2026-09-28', ['a']],
  ]);
  assert.equal(localDay('not a time'), '');
  assert.deepEqual(withVersion(versions, { id: 'd', created_at: at(2026, 9, 29, 16) }).map((v) => v.id), ['d', 'c', 'b', 'a']);
  assert.equal(withVersion(versions, versions[1]), versions);
});
