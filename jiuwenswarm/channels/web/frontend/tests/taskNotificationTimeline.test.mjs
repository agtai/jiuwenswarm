import assert from 'node:assert/strict';
import test from 'node:test';
import { buildTimelineItems, buildRenderItems } from '../node_modules/.cache/task-notification-timeline/buildTurnTimeline.mjs';

const at = seconds => new Date(Date.UTC(2026, 8, 3, 18, 17, seconds)).toISOString();
const msg = (id, role, seconds, content = 'text') => ({ id, role, timestamp: at(seconds), content });
const notice = (seconds, suffix = 'a') =>
  msg(`live-voice:interaction-1:response-task-progress-${suffix.repeat(40)}:1:text:0:0:digest`, 'assistant', seconds, '后台任务正在执行。');
const render = (messages, processing = false) => buildRenderItems(buildTimelineItems(messages, [], []), false, processing);

test('each notification keeps its timestamp; foreground metadata and elapsed time end at its reply', () => {
  const input = [msg('user', 'user', 16), msg('reply', 'assistant', 19), notice(34), notice(55, 'b')];
  // JSON round trip exercises the persisted identity without a transient flag.
  const items = render(JSON.parse(JSON.stringify(input)));
  assert.deepEqual(
    items.map(item => item.type),
    ['message', 'message', 'turnSummary', 'message', 'message'],
  );
  assert.deepEqual(
    items.filter(item => item.type === 'message').map(item => item.hideMeta),
    [false, false, false, false],
  );
  assert.equal(items[2].endMs - items[2].startMs, 3000);
  assert.equal(items[3].message.timestamp, at(34));
  assert.equal(items[4].message.timestamp, at(55));
  assert.equal(items[3].showAvatar, true);
});

test('notifications during foreground streaming have metadata and do not hide the final reply', () => {
  const input = [msg('user', 'user', 16), msg('delta', 'assistant', 18), notice(20), msg('final', 'assistant', 22)];
  const running = render(input, true);
  assert.equal(running.find(item => item.message?.id === input[2].id).hideMeta, false);
  const settled = render(input);
  assert.equal(settled.find(item => item.message?.id === 'delta').hideMeta, true);
  assert.equal(settled.find(item => item.message?.id === 'final').hideMeta, false);
  assert.equal(settled.at(-1).endMs - settled.at(-1).startMs, 6000);
});

test('notification-only history has no invented foreground duration', () => {
  assert.deepEqual(render([]), []);
  for (const processing of [false, true]) {
    const items = render([notice(20), notice(30, 'b')], processing);
    assert.equal(items.length, 2);
    assert.ok(items.every(item => item.type === 'message' && item.hideMeta === false));
  }
});

test('ordinary text with notification wording keeps normal foreground grouping', () => {
  const items = render([msg('user', 'user', 16), msg('first', 'assistant', 18), msg('last', 'assistant', 22, '后台任务正在执行。')]);
  assert.equal(items[1].hideMeta, true);
  assert.equal(items[2].hideMeta, false);
  assert.equal(items[3].endMs - items[3].startMs, 6000);
});

test('multiple turns and delayed background completion retain separate foreground summaries', () => {
  const items = render([msg('u1', 'user', 1), msg('a1', 'assistant', 3), notice(10), msg('u2', 'user', 15), msg('a2', 'assistant', 18), notice(40, 'b')]);
  const summaries = items.filter(item => item.type === 'turnSummary');
  assert.deepEqual(
    summaries.map(item => [item.turnId, item.endMs - item.startMs, item.isLastTurn]),
    [
      [1, 2000, false],
      [2, 3000, true],
    ],
  );
  assert.equal(items.at(-1).message.timestamp, at(40));
});
