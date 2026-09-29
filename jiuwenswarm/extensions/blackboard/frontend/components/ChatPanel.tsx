// The workspace chat: people talk, "@jiuwen" gives the sender's agent a task on the workspace, and
// the agent's replies, questions and the host's notices arrive in the same stream.
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Info, MessageSquareText } from 'lucide-react';

import { Button } from '../../../../channels/web/frontend/src/components/ui';
import { coded } from '../conversation';
import type { ChatMessageView, DecisionView, MandateView, MemberView, SessionAttachmentView } from '../types';
import { Composer, type ComposerSubmit } from './Composer';
import { DecisionCard, type DecisionActions } from './Decisions';
import { TaskTag, noticeText } from './tasks';

// Within this many pixels of the end, new messages keep the list scrolled down.
const STICKY_PX = 80;

function time(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function ChatPanel({
  messages,
  hasMore,
  members,
  meId,
  canPost,
  canTask,
  sessions,
  mandates,
  decisions,
  docTitles,
  decisionActions,
  onLoadOlder,
  onPost,
  onOpenThread,
}: {
  messages: ChatMessageView[];
  hasMore: boolean;
  members: MemberView[];
  meId: string | null;
  canPost: boolean;
  canTask: boolean;
  sessions: SessionAttachmentView[];
  mandates: ReadonlyMap<string, MandateView>;
  decisions: ReadonlyMap<string, DecisionView>;
  docTitles: ReadonlyMap<string, string>;
  decisionActions: DecisionActions;
  onLoadOlder: () => Promise<void>;
  onPost: (value: ComposerSubmit) => Promise<void>;
  onOpenThread: (docId: string, threadId: string) => void;
}) {
  const { t } = useTranslation();
  const list = useRef<HTMLDivElement | null>(null);
  const sticky = useRef(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const lastId = messages[messages.length - 1]?.id;

  useLayoutEffect(() => {
    const el = list.current;
    if (el && sticky.current) el.scrollTop = el.scrollHeight;
  }, [lastId]);

  useEffect(() => {
    const el = list.current;
    if (!el) return;
    const onScroll = () => {
      sticky.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICKY_PX;
    };
    el.addEventListener('scroll', onScroll);
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  const older = async () => {
    setLoadingOlder(true);
    try {
      await onLoadOlder();
    } finally {
      setLoadingOlder(false);
    }
  };

  const post = async (value: ComposerSubmit) => {
    sticky.current = true;
    await onPost(value);
  };

  return (
    <div className="bb-rail__panel bb-chat" data-testid="blackboard-chat-panel">
      <div ref={list} className="bb-chat__list" data-testid="blackboard-chat-list">
        {hasMore ? (
          <Button size="sm" variant="quiet" loading={loadingOlder} data-testid="blackboard-chat-older-btn" onClick={() => void older()}>
            {t('blackboard.messages.older')}
          </Button>
        ) : null}
        {messages.length === 0 ? (
          <p className="bb-muted bb-chat__empty" data-testid="blackboard-chat-empty">
            {t('blackboard.messages.empty')}
          </p>
        ) : null}
        {messages.map((m) => (
          <ChatMessage
            key={m.id}
            message={m}
            meId={meId}
            mandate={m.mandate_id ? mandates.get(m.mandate_id) : undefined}
            decision={m.decision_id ? decisions.get(m.decision_id) : undefined}
            docTitles={docTitles}
            decisionActions={decisionActions}
            onOpenThread={onOpenThread}
          />
        ))}
      </div>
      {canPost ? (
        <Composer
          placeholder={t('blackboard.messages.placeholder')}
          members={members}
          meId={meId}
          canTask={canTask}
          sessions={sessions}
          submitLabel={t('blackboard.messages.send')}
          testId="blackboard-chat-composer"
          onSubmit={post}
        />
      ) : (
        <p className="bb-muted" data-testid="blackboard-chat-read-only">
          {t('blackboard.messages.readOnly')}
        </p>
      )}
    </div>
  );
}

function ChatMessage({
  message,
  meId,
  mandate,
  decision,
  docTitles,
  decisionActions,
  onOpenThread,
}: {
  message: ChatMessageView;
  meId: string | null;
  mandate: MandateView | undefined;
  decision: DecisionView | undefined;
  docTitles: ReadonlyMap<string, string>;
  decisionActions: DecisionActions;
  onOpenThread: (docId: string, threadId: string) => void;
}) {
  const { t } = useTranslation();
  const name = message.author_name ?? '';
  const common = { 'data-testid': 'blackboard-chat-message', 'data-variant': message.kind, 'data-author': message.author_kind };

  if (message.kind === 'notice') {
    return (
      <p className="bb-chat__notice" {...common}>
        <Info size={12} aria-hidden="true" />
        <span>{noticeText(t, message.body, name)}</span>
      </p>
    );
  }
  if (message.kind === 'summary') {
    const summary = coded(message.body);
    return (
      <p className="bb-chat__notice is-summary" {...common}>
        <MessageSquareText size={12} aria-hidden="true" />
        <span>{noticeText(t, message.body, name)}</span>
        {summary?.params.doc_id && summary.params.thread_id ? (
          <button type="button" className="bb-link-button" data-testid="blackboard-chat-open-thread-btn" onClick={() => onOpenThread(summary.params.doc_id, summary.params.thread_id)}>
            {t('blackboard.messages.openThread')}
          </button>
        ) : null}
      </p>
    );
  }

  if (message.kind === 'question' && decision) {
    return (
      <div className="bb-chat__question" {...common}>
        <DecisionCard decision={decision} meId={meId} docTitle={decision.doc_id ? (docTitles.get(decision.doc_id) ?? null) : null} actions={decisionActions} />
      </div>
    );
  }

  const agent = message.author_kind === 'agent';
  const mine = message.author_kind === 'person' && message.author_id === meId;
  return (
    <div className={`bb-chat__message${agent ? ' is-agent' : ''}${mine ? ' is-mine' : ''}`} {...common}>
      <div className="bb-chat__meta">
        {agent ? <Bot size={13} aria-hidden="true" /> : null}
        <strong data-testid="blackboard-chat-author">{agent ? t('blackboard.agents.agentOf', { name }) : name}</strong>
        <span className="bb-muted">{time(message.created_at)}</span>
        {message.mandate_id && message.kind === 'message' && !agent ? <TaskTag mandate={mandate} /> : null}
      </div>
      {message.kind === 'answer' ? (
        <p className="bb-chat__body" data-testid="blackboard-chat-body">
          {t(decision && decision.requester_id !== message.author_id ? 'blackboard.messages.proposed' : 'blackboard.messages.answered', { answer: message.body })}
        </p>
      ) : (
        <p className="bb-chat__body" data-testid="blackboard-chat-body">
          {message.body}
        </p>
      )}
    </div>
  );
}
