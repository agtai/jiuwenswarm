import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { act, create } from 'react-test-renderer';
import i18next from 'i18next';
import { I18nextProvider } from 'react-i18next';
import { RecentTasksPanel } from '../node_modules/.cache/recent-background-tasks/RecentTasksPanel.mjs';
import { useLiveVoiceTaskStore } from '../node_modules/.cache/recent-background-tasks/liveVoiceTaskStore.mjs';

await i18next.init({ lng: 'zh', resources: { zh: { translation: {
  chat: { recentTasks: '最近任务' }, liveVoice: { formal: { recentTasks: {
    refresh: '刷新', unavailable: '暂不可用', result: '任务结果', resultPending: '结果尚未生成', steps: '当前对话步骤',
    states: { completed: '已完成', running: '进行中', waiting: '等待中' },
  } } },
} } } });

const task = (id, project = 'project-a') => ({ task_id: id, attempt_id: `attempt-${id}`, attempt_number: 1,
  correlation_id: `correlation-${id}`, subject_id: 'subject', session_id: 'session-a', project_id: project,
  name: `后台 ${id}`, canonical_state: 'terminal', display_state: 'completed', outcome: 'completed', queued: false,
  admission_priority: null, admission_reason: null, event_head: 2, revision_number: 0, predecessor_task_id: null,
  successor_task_id: null, blocking_question: null, progress: '100%', result_availability: 'available',
  result_text: `结果 ${id}`, result_attempt_id: `attempt-${id}`, replay_event_count: 2, replay_event_types: [], available_operations: [] });

test('right recent-tasks view uses the exact Registry owner and filters session project authority', async () => {
  const calls = [];
  const snapshot = { status: 'ready', session_id: 'session-a', tasks: [task('task-a'), task('foreign', 'project-b')],
    selected_task_id: 'task-a', collection_operations: [], command: null, reason: null };
  const owner = { snapshot: () => snapshot, refresh: async session => calls.push(['refresh', session]),
    select: async id => calls.push(['select', id]) };
  let renderer;
  await act(async () => { renderer = create(React.createElement(I18nextProvider, { i18n: i18next },
    React.createElement(RecentTasksPanel, { entry: { owner, snapshot }, todos: [], sessionId: 'session-a', projectId: 'project-a' }))); });
  const text = JSON.stringify(renderer.toJSON());
  assert.match(text, /后台 task-a/);
  assert.match(text, /结果 task-a/);
  assert.doesNotMatch(text, /后台 foreign/);
  assert.doesNotMatch(text, /task\.create|签发控制|Registry 后端/);
  await act(async () => { renderer.update(React.createElement(I18nextProvider, { i18n: i18next },
    React.createElement(RecentTasksPanel, { entry: { owner, snapshot }, todos: [], sessionId: 'session-a' }))); });
  assert.doesNotMatch(JSON.stringify(renderer.toJSON()), /后台 task-a|结果 task-a/,
    'mixed project scope without a project binding must fail closed');
  const homogeneous = { ...snapshot, tasks: [task('task-a')] };
  await act(async () => { renderer.update(React.createElement(I18nextProvider, { i18n: i18next },
    React.createElement(RecentTasksPanel, { entry: { owner, snapshot: homogeneous }, todos: [], sessionId: 'session-a' }))); });
  assert.match(JSON.stringify(renderer.toJSON()), /后台 task-a|结果 task-a/,
    'one authoritative project in the owner snapshot should remain visible while App project metadata loads');
  await act(async () => { renderer.update(React.createElement(I18nextProvider, { i18n: i18next },
    React.createElement(RecentTasksPanel, { entry: { owner, snapshot }, todos: [], sessionId: 'session-a', projectId: 'project-a' }))); });
  const buttons = renderer.root.findAllByType('button');
  await act(async () => { buttons.find(button => button.children.includes('刷新')).props.onClick(); await Promise.resolve(); });
  await act(async () => { buttons.find(button => button.props['aria-pressed'] === true).props.onClick(); await Promise.resolve(); });
  assert.deepEqual(calls, [['refresh', 'session-a'], ['select', 'task-a']]);
});

test('shared view release cannot erase a successor owner for the same session', () => {
  const first = { snapshot: () => ({ status: 'idle', session_id: null, tasks: [] }) };
  const successor = { snapshot: () => ({ status: 'idle', session_id: null, tasks: [] }) };
  const store = useLiveVoiceTaskStore.getState();
  store.bind('session-a', first);
  useLiveVoiceTaskStore.getState().bind('session-a', successor);
  useLiveVoiceTaskStore.getState().release('session-a', first);
  assert.equal(useLiveVoiceTaskStore.getState().entries['session-a'].owner, successor);
  useLiveVoiceTaskStore.getState().release('session-a', successor);
  assert.equal(useLiveVoiceTaskStore.getState().entries['session-a'], undefined);
});
