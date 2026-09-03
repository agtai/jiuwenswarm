import { useTranslation } from 'react-i18next';
import { selectScopedLiveVoiceTasks, type LiveVoiceTaskEntry } from '../../stores/liveVoiceTaskStore';
import type { TodoItem } from '../../types';
import { MarkdownRenderer } from '../MarkdownRenderer';

export function RecentTasksPanel({ entry, todos, sessionId, projectId }: {
  entry: LiveVoiceTaskEntry;
  todos: TodoItem[];
  sessionId: string;
  projectId?: string;
}) {
  const { t } = useTranslation();
  const { snapshot, owner } = entry;
  const tasks = selectScopedLiveVoiceTasks(snapshot, sessionId, projectId);
  const selected = tasks.find(task => task.task_id === snapshot.selected_task_id);
  const busy = snapshot.status !== 'ready';
  const statusLabel = (state: string) => t(`liveVoice.formal.recentTasks.states.${state}`);
  const states = [...tasks.map(task => task.display_state), ...todos.map(todo => todo.status)];
  const counts = [
    ['waiting', states.filter(state => ['accepted', 'queued', 'blocked', 'decision_required', 'pending'].includes(state)).length],
    ['running', states.filter(state => ['running', 'in_progress'].includes(state)).length],
    ['completed', states.filter(state => state === 'completed').length],
    ['cancelled', states.filter(state => state === 'cancelled').length],
    ['failed', states.filter(state => ['failed', 'interrupted', 'unknown'].includes(state)).length],
  ] as const;
  return (
    <section className="flex min-h-0 flex-col gap-3 overflow-y-auto px-3 pb-3 text-sm" aria-label={t('chat.recentTasks')} data-testid="recent-background-tasks">
      <header className="flex items-center justify-between gap-2">
        <strong>{t('chat.recentTasks')}</strong>
        <button type="button" className="text-text-link" disabled={snapshot.status === 'loading'} onClick={() => { void owner.refresh(sessionId).catch(() => undefined); }}>
          {t('liveVoice.formal.recentTasks.refresh')}
        </button>
      </header>
      <div className="flex flex-wrap justify-between gap-2 text-xs">
        {counts.map(([state, count]) => <span key={state}>{statusLabel(state)} {count}</span>)}
      </div>
      {['failed', 'disconnected'].includes(snapshot.status) && <p role="status" className="text-warn">{t('liveVoice.formal.recentTasks.unavailable')}</p>}
      {tasks.map(task => (
        <button type="button" key={task.task_id} disabled={busy} aria-pressed={selected?.task_id === task.task_id}
          className="flex flex-col gap-1 rounded border border-border bg-card p-3 text-left text-text"
          onClick={() => { void owner.select(task.task_id).catch(() => undefined); }}>
          <strong>{task.name}</strong>
          <span>{statusLabel(task.display_state)}</span>
          <span className="break-all text-xs text-text-muted">{task.task_id}</span>
          {task.progress && <span>{task.progress}</span>}
        </button>
      ))}
      {selected && <section className="rounded border border-border p-3" aria-label={t('liveVoice.formal.recentTasks.result')}>
        <strong>{selected.name}</strong>
        {selected.blocking_question && <p>{selected.blocking_question}</p>}
        {selected.result_availability === 'available' && selected.result_text
          ? <MarkdownRenderer content={selected.result_text} />
          : <p>{t('liveVoice.formal.recentTasks.resultPending')}</p>}
      </section>}
      {todos.length > 0 && <strong>{t('liveVoice.formal.recentTasks.steps')}</strong>}
      {todos.map(todo => <div key={`todo:${todo.id}`} className="rounded border border-border p-3">
        <span>{todo.content || todo.activeForm}</span>
        <span className="block text-xs">{statusLabel(todo.status)}</span>
      </div>)}
    </section>
  );
}
