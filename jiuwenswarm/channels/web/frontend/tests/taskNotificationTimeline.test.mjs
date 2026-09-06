import assert from 'node:assert/strict';
import test from 'node:test';
import { build } from 'esbuild';
const historyBundle = await build({ entryPoints: ['src/features/historyRestore.ts'], bundle: true, platform: 'node', format: 'esm', write: false, define: { 'import.meta.env': '{}' } });
const { parseHistoryJsonFileToTimelinePreview } = await import(`data:text/javascript;base64,${Buffer.from(historyBundle.outputFiles[0].text).toString('base64')}`);
import { buildTimelineItems, buildRenderItems, completedWorkDurationMs, turnElapsedRangeMs } from '../node_modules/.cache/task-notification-timeline/buildTurnTimeline.mjs';

const at = seconds => new Date(Date.UTC(2026, 8, 3, 18, 17, seconds)).toISOString();

test('late Native user transcription orders its generated replies without changing observed timestamps', () => {
  const turn = JSON.stringify(['interaction', 'turn']);
  const preface = { id: 'preface', role: 'assistant', content: 'Checking', timestamp: at(1), nativeTurnKey: turn };
  const answer = { id: 'answer', role: 'assistant', content: 'Three options', timestamp: at(3), nativeTurnKey: turn };
  const user = { id: 'user', role: 'user', content: 'Read the project', timestamp: at(4), nativeTurnKey: turn };
  const foreign = { id: 'other', role: 'assistant', content: 'Other response', timestamp: at(0), nativeTurnKey: '["other","turn"]' };
  const items = buildTimelineItems([foreign, preface, answer, user], [], []);
  assert.deepEqual(items.map(item => item.message.id), ['other', 'user', 'preface', 'answer']);
  assert.equal(items[2].message.timestamp, at(1));
  assert.equal(items[3].timestampMs, Date.parse(at(3)));
});
const msg = (id, role, seconds, content = 'text') => ({ id, role, timestamp: at(seconds), content });
const notice = (seconds, suffix = 'a') =>
  msg(`live-voice:interaction-1:response-task-progress-${suffix.repeat(40)}:1:text:0:0:digest`, 'assistant', seconds, '后台任务正在执行。');
const render = (messages, processing = false) => buildRenderItems(buildTimelineItems(messages, [], []), false, processing);

test('Native recovery with legacy repeated turn counters never moves an answered turn to a later user', () => {
  const turn = '["interaction","native-turn-00000001"]';
  const messages = [
    { ...msg('old-user', 'user', 1), nativeTurnKey: turn },
    { ...msg('old-answer', 'assistant', 4), nativeTurnKey: turn },
    { ...msg('recovered-user', 'user', 10), nativeTurnKey: turn },
    { ...msg('recovered-answer', 'assistant', 15), nativeTurnKey: turn },
  ];
  assert.deepEqual(buildTimelineItems(messages, [], []).map(item => item.message.id), messages.map(item => item.id));
});

test('Native delayed playback acknowledgement keeps the answer with its own user turn', () => {
  const messages = [
    { ...msg('u1', 'user', 1), nativeTurnKey: '["interaction","turn-1"]' },
    { ...msg('u2', 'user', 10), nativeTurnKey: '["interaction","turn-2"]' },
    { ...msg('a1', 'assistant', 12), nativeTurnKey: '["interaction","turn-1"]' },
    { ...msg('a2', 'assistant', 14), nativeTurnKey: '["interaction","turn-2"]' },
  ];
  assert.deepEqual(buildTimelineItems(messages, [], []).map(item => item.message.id), ['u1', 'a1', 'u2', 'a2']);
  assert.equal(messages[2].timestamp, at(12));
});

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

test('replacement request owns the recorded 12.360 seconds, including single-reply waiting', () => {
  const input = [
    { ...msg('old', 'user', 0), timestamp: '1788647997.210' },
    { ...msg('new', 'user', 0), timestamp: '1788648005.003' },
    { ...msg('reply', 'assistant', 0), timestamp: '1788648017.363' },
  ];
  for (const messages of [input, JSON.parse(JSON.stringify(input))]) {
    const summaries = render(messages).filter(item => item.type === 'turnSummary');
    assert.equal(summaries.length, 1);
    assert.equal(completedWorkDurationMs(summaries[0]), 12360);
  }
});

test('consecutive empty requests after cancellation, close or disconnect never carry their clocks', () => {
  const messages = [msg('cancelled', 'user', 1), notice(4), msg('closed', 'user', 10), msg('latest', 'user', 20)];
  const waiting = render(messages, true).find(item => item.type === 'turnSummary');
  assert.equal(waiting.startMs, Date.parse(at(20)));
  assert.deepEqual(turnElapsedRangeMs(waiting), { startMs: Date.parse(at(20)), endMs: Date.parse(at(20)) });
  const final = render([...messages, { ...msg('a', 'assistant', 25), completedAt: at(30) }]).at(-1);
  assert.equal(completedWorkDurationMs(final), 10000);
});

test('Goal objective badge and same-text ordinary message cannot establish shared timing', () => {
  for (const isGoalObjectiveMessage of [false, true]) {
    const goal = { ...msg('goal', 'user', 10, 'same objective'), isGoalObjectiveMessage };
    const input = [msg('u', 'user', 1, 'same objective'), goal, msg('answer', 'assistant', 15)];
    const items = render(input);
    assert.equal(completedWorkDurationMs(items.at(-1)), 5000);
    assert.equal(items.find(item => item.message?.id === 'goal').message.isGoalObjectiveMessage, isGoalObjectiveMessage);
  }
});

test('work on either side of a new user retains its own request and completion span', () => {
  const messages = [msg('u1', 'user', 1), msg('a1', 'assistant', 5), msg('u2', 'user', 10), msg('a2', 'assistant', 17)];
  const executions = [{ toolCallId: 't', toolCall: { id: 't', name: 'read_file', arguments: {} }, status: 'completed', startedAt: at(12), updatedAt: at(14) }];
  const reasoning = [{ id: 'r', content: 'thinking', startedAt: Date.parse(at(2)), closedAt: Date.parse(at(4)), closed: true }];
  const items = buildRenderItems(buildTimelineItems(messages, executions, reasoning), false, false);
  assert.deepEqual(items.filter(item => item.type === 'turnSummary').map(completedWorkDurationMs), [4000, 7000]);
});

test('an undated replacement stays before its answer without borrowing an older clock', () => {
  for (const timestamp of ['', 'bad', '0']) {
    const input = [msg('u1', 'user', 1), { ...msg('u2', 'user', 10), timestamp }, msg('a', 'assistant', 15)];
    const items = render(input);
    assert.deepEqual(items.filter(item => item.type === 'message').map(item => item.message.id), ['u1', 'u2', 'a']);
    assert.equal(completedWorkDurationMs(items.at(-1)), 0);
    assert.equal(render(input.slice(0, 2), true).filter(item => item.type === 'turnSummary').length, 0);
  }
});

test('actual history/FileViewer restore preserves dated and undated replacement boundaries', () => {
  for (const timestamp of [at(10), '', 'bad', '0']) {
    const records = [msg('old', 'user', 1), { ...msg('new', 'user', 10), timestamp }, msg('answer', 'assistant', 15)];
    const restored = parseHistoryJsonFileToTimelinePreview(records, 'session');
    assert.deepEqual(restored.messages.map(message => message.id), records.map(message => message.id));
    assert.deepEqual(render(restored.messages).filter(item => item.type === 'turnSummary').map(completedWorkDurationMs), [timestamp === at(10) ? 5000 : 0]);
  }
});

test('undated user separates subsequent tools and reasoning from an older request', () => {
  const input = [msg('old', 'user', 1), { ...msg('new', 'user', 10), timestamp: '' }, msg('answer', 'assistant', 15)];
  const executions = [{ toolCallId: 't', toolCall: { id: 't', name: 'read_file', arguments: {} }, status: 'completed', startedAt: at(12), updatedAt: at(14) }];
  const reasoning = [{ id: 'r', text: 'thinking', startedAt: Date.parse(at(11)), closedAt: Date.parse(at(12)), closed: true }];
  const items = buildRenderItems(buildTimelineItems(input, executions, reasoning), false, false);
  assert.ok(items.filter(item => ['toolGroup', 'reasoning', 'turnSummary'].includes(item.type)).every(item => item.turnId === 2));
  assert.equal(completedWorkDurationMs(items.at(-1)), 4000); // Known work only; no invented request time.
});

test('adjacent undated records preserve the replacement boundary in live and restored history', () => {
  const input = [msg('old', 'user', 1), { ...msg('old-answer', 'assistant', 3), timestamp: '' }, { ...msg('new', 'user', 10), timestamp: '' }, msg('new-answer', 'assistant', 15)];
  for (const messages of [input, parseHistoryJsonFileToTimelinePreview(input, 'session').messages]) {
    const items = render(messages);
    assert.deepEqual(items.filter(item => item.type === 'message').map(item => item.message.id), input.map(message => message.id));
    assert.deepEqual(items.filter(item => item.type === 'turnSummary').map(completedWorkDurationMs), [0, 0]);
  }
});


test('history and FileViewer materialize one display per exact Task event without rewriting records', () => {
  const binding = { scope: { subject_id: 'subject', project_id: 'project', session_id: 'session', assurance: 'authenticated' },
    task_id: 'task', attempt_id: 'attempt', event_id: 'event' };
  const records = [0, 1, 2].map(i => ({ ...msg(`notice-${i}`, 'assistant', i + 1, 'Complete'),
    type: 'chat.final', task_event_binding: { ...binding, event_id: i === 2 ? 'other' : 'event' } }));
  const restored = parseHistoryJsonFileToTimelinePreview(records, 'session');
  assert.equal(restored.messages.length, 3);
  assert.ok(restored.messages[0].taskNotification?.eventKey);
  assert.deepEqual(buildTimelineItems(restored.messages, [], []).map(item => item.message.id), ['notice-0', 'notice-2']);
  assert.equal(records.length, 3);
  const foreign = parseHistoryJsonFileToTimelinePreview(records, 'foreign');
  assert.equal(buildTimelineItems(foreign.messages, [], []).length, 3);
});
