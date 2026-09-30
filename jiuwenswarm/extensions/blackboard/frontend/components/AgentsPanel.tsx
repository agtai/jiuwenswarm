import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Ban, Bot, Check, CircleCheck, CircleX, ExternalLink, Link2, MessageSquare, Unlink, X } from 'lucide-react';

import { Button, Select, Tag } from '../../../../channels/web/frontend/src/components/ui';
import type { DocView, MandateView, SessionAttachmentView } from '../types';
import { ACTIVE, TaskTag } from './tasks';

export function AgentsPanel({
  mandates,
  sessions,
  sessionTitles,
  docs,
  meId,
  canEdit,
  onStart,
  onLoadAttachable,
  onAttach,
  onChat,
  onOpen,
  onDetach,
  onCancel,
  onDecide,
  onResolveUnknown,
}: {
  mandates: MandateView[];
  sessions: SessionAttachmentView[];
  // The app's names for the person's chats.
  sessionTitles: Record<string, string>;
  docs: DocView[];
  meId: string | null;
  canEdit: boolean;
  onStart: () => Promise<void>;
  onLoadAttachable: () => Promise<Array<{ session_id: string; title: string }>>;
  onAttach: (sessionId: string) => Promise<void>;
  // Talk to the session in the chat box over the page; onOpen goes to the app's chat instead.
  onChat: (sessionId: string) => void;
  onOpen: (sessionId: string) => void;
  onDetach: (sessionId: string) => void;
  onCancel: (mandate: MandateView) => void;
  onDecide: (mandate: MandateView, docId: string, action: 'accept' | 'reject') => void;
  onResolveUnknown: (mandate: MandateView, status: 'done' | 'failed') => void;
}) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [attachable, setAttachable] = useState<Array<{ session_id: string; title: string }> | null>(null);
  const titles = new Map(docs.map((d) => [d.id, d.title]));

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await action();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bb-rail__panel bb-agents" data-testid="blackboard-agents-panel">
      <section className="bb-agents__start">
        <p className="bb-muted">{t('blackboard.agents.intro')}</p>
        {canEdit ? (
          <div className="bb-agents__actions">
            <Button size="sm" variant="primary" icon={<Bot size={14} />} loading={busy} data-testid="blackboard-agents-start-btn" onClick={() => void run(onStart)}>
              {t('blackboard.agents.start')}
            </Button>
            <Button
              size="sm"
              icon={<Link2 size={14} />}
              data-testid="blackboard-agents-attach-btn"
              onClick={() => void onLoadAttachable().then(setAttachable)}
            >
              {t('blackboard.agents.attach')}
            </Button>
          </div>
        ) : (
          <p className="bb-muted" data-testid="blackboard-agents-read-only">
            {t('blackboard.agents.editorsOnly')}
          </p>
        )}
        {attachable ? (
          attachable.length === 0 ? (
            <p className="bb-muted" data-testid="blackboard-agents-attach-empty">
              {t('blackboard.agents.noSessions')}
            </p>
          ) : (
            <Select
              data-testid="blackboard-agents-attach-select"
              aria-label={t('blackboard.agents.attach')}
              value=""
              options={[{ value: '', label: t('blackboard.agents.pickSession') }, ...attachable.map((s) => ({ value: s.session_id, label: s.title }))]}
              onChange={(sessionId) => {
                if (sessionId) void run(() => onAttach(sessionId)).then(() => setAttachable(null));
              }}
            />
          )
        ) : null}
      </section>

      {sessions.length > 0 ? (
        <section className="bb-rail__section" data-testid="blackboard-agents-sessions">
          <h4>{t('blackboard.agents.sessions')}</h4>
          <ul className="bb-session-list">
            {sessions.map((s) => (
              <li key={s.session_id} className="bb-session" data-testid="blackboard-agents-session" data-variant={s.session_id}>
                <button
                  type="button"
                  className="bb-session__name"
                  title={t('blackboard.agents.chatHint')}
                  data-testid="blackboard-agents-session-chat-btn"
                  onClick={() => onChat(s.session_id)}
                >
                  <MessageSquare size={13} aria-hidden="true" />
                  <span>{sessionTitles[s.session_id] ?? t('blackboard.agents.sessionSince', { time: new Date(s.attached_at).toLocaleString() })}</span>
                  {s.is_default ? (
                    <Tag variant="neutral" title={t('blackboard.agents.tasksSessionHint')} data-testid="blackboard-agents-session-tasks-tag">
                      {t('blackboard.agents.tasksSession')}
                    </Tag>
                  ) : null}
                </button>
                <Button
                  size="sm"
                  variant="quiet"
                  icon={<ExternalLink size={13} />}
                  aria-label={t('blackboard.agents.open')}
                  title={t('blackboard.agents.open')}
                  data-testid="blackboard-agents-session-open-btn"
                  onClick={() => onOpen(s.session_id)}
                />
                <Button
                  size="sm"
                  variant="quiet"
                  icon={<Unlink size={13} />}
                  aria-label={t('blackboard.agents.detach')}
                  title={t('blackboard.agents.detach')}
                  data-testid="blackboard-agents-session-detach-btn"
                  onClick={() => onDetach(s.session_id)}
                />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="bb-rail__section">
        <h4>{t('blackboard.agents.runs')}</h4>
        {mandates.length === 0 ? (
          <p className="bb-muted" data-testid="blackboard-agents-runs-empty">
            {t('blackboard.agents.noRuns')}
          </p>
        ) : null}
        <ul className="bb-mandate-list" data-testid="blackboard-mandate-list">
          {mandates.map((m) => {
            const active = ACTIVE.includes(m.status);
            const applied = m.receipts.filter((r) => r.status === 'applied');
            const docIds = [...new Set(applied.map((r) => r.doc_id))];
            const pendingDocs = Object.keys(m.pending ?? {});
            return (
              <li key={m.id} className="bb-mandate" data-testid="blackboard-mandate-item" data-variant={m.status}>
                <div className="bb-mandate__head">
                  <span className="bb-mandate__who">
                    <Bot size={13} aria-hidden="true" />
                    {t('blackboard.agents.agentOf', { name: m.requester_name ?? m.requester_id })}
                  </span>
                  <span data-testid="blackboard-mandate-status" data-variant={m.status}>
                    <TaskTag mandate={m} />
                  </span>
                </div>
                <p className="bb-mandate__origin bb-muted" data-testid="blackboard-mandate-origin" data-variant={m.origin}>
                  {t(`blackboard.agents.origin.${m.origin}`)}
                </p>
                <p className="bb-mandate__instruction">{m.instruction}</p>
                <p className="bb-muted">
                  {t('blackboard.agents.changes', { count: applied.reduce((n, r) => n + r.suggestion_ids.length, 0) })}
                  {docIds.length ? `: ${docIds.map((id) => titles.get(id) ?? id).join(', ')}` : ''}
                </p>
                <div className="bb-mandate__actions">
                  {canEdit
                    ? pendingDocs.map((docId) => (
                        <span key={docId} className="bb-inline">
                          <Button
                            size="sm"
                            variant="quiet"
                            icon={<Check size={13} />}
                            data-testid="blackboard-mandate-accept-btn"
                            data-variant={docId}
                            onClick={() => onDecide(m, docId, 'accept')}
                          >
                            {t('blackboard.agents.acceptAll')}
                          </Button>
                          <Button
                            size="sm"
                            variant="quiet"
                            icon={<X size={13} />}
                            data-testid="blackboard-mandate-reject-btn"
                            data-variant={docId}
                            onClick={() => onDecide(m, docId, 'reject')}
                          >
                            {t('blackboard.agents.rejectAll')}
                          </Button>
                        </span>
                      ))
                    : null}
                  {m.status === 'unknown' && canEdit ? (
                    <span className="bb-inline">
                      <Button
                        size="sm"
                        variant="quiet"
                        icon={<CircleCheck size={13} />}
                        title={t('blackboard.agents.resolveHint')}
                        data-testid="blackboard-mandate-resolve-done-btn"
                        onClick={() => onResolveUnknown(m, 'done')}
                      >
                        {t('blackboard.agents.resolveDone')}
                      </Button>
                      <Button
                        size="sm"
                        variant="quiet"
                        icon={<CircleX size={13} />}
                        title={t('blackboard.agents.resolveHint')}
                        data-testid="blackboard-mandate-resolve-failed-btn"
                        onClick={() => onResolveUnknown(m, 'failed')}
                      >
                        {t('blackboard.agents.resolveFailed')}
                      </Button>
                    </span>
                  ) : null}
                  {active && (canEdit || m.requester_id === meId) ? (
                    <Button size="sm" variant="quiet" icon={<Ban size={13} />} data-testid="blackboard-mandate-cancel-btn" onClick={() => onCancel(m)}>
                      {t('blackboard.agents.cancel')}
                    </Button>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
