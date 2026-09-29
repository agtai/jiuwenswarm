// Comment threads on the open document. The editor's margin shows each open thread beside its
// passage (ThreadCard with variant "margin") and the comment being written (CommentDraft); the
// Comments tab lists them all, with detached threads whose passage is gone and resolved ones.
import { Fragment, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Check, Info, Pencil, Reply, RotateCcw } from 'lucide-react';

import { Button, Switch, Tag } from '../../../../channels/web/frontend/src/components/ui';
import type {
  CommentView,
  DecisionView,
  DocView,
  MandateView,
  MemberView,
  SessionAttachmentView,
  ThreadView,
} from '../types';
import { Composer, type ComposerSubmit } from './Composer';
import { DecisionCard, type DecisionActions } from './Decisions';
import { TaskTag, noticeText } from './tasks';

export interface CommentsActions {
  create: (value: ComposerSubmit) => Promise<void>;
  cancelDraft: () => void;
  reply: (threadId: string, value: ComposerSubmit) => Promise<void>;
  edit: (commentId: string, body: string) => Promise<void>;
  setResolved: (threadId: string, resolved: boolean) => Promise<void>;
  open: (threadId: string | null) => void;
  showResolved: (show: boolean) => void;
}

function when(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export interface ThreadProps {
  members: MemberView[];
  meId: string | null;
  canComment: boolean;
  canTask: boolean;
  sessions: SessionAttachmentView[];
  mandates: ReadonlyMap<string, MandateView>;
  decisions: ReadonlyMap<string, DecisionView>;
  docTitles: ReadonlyMap<string, string>;
  decisionActions: DecisionActions;
  actions: CommentsActions;
}

// A new comment on the selected passage, in the margin beside it.
export function CommentDraft({ members, meId, canTask, sessions, actions }: ThreadProps) {
  const { t } = useTranslation();
  return (
    <section className="bb-thread is-draft" data-testid="blackboard-comment-draft">
      <Composer
        placeholder={t('blackboard.comments.placeholder')}
        members={members}
        meId={meId}
        canTask={canTask}
        sessions={sessions}
        scopeSwitch
        autoFocus
        submitLabel={t('blackboard.comments.post')}
        testId="blackboard-comment-composer"
        onSubmit={actions.create}
        onCancel={actions.cancelDraft}
      />
    </section>
  );
}

export function CommentsPanel({
  doc,
  threads,
  activeThread,
  showResolved,
  members,
  meId,
  canComment,
  canTask,
  sessions,
  mandates,
  decisions,
  docTitles,
  decisionActions,
  actions,
}: {
  doc: DocView | null;
  threads: ThreadView[];
  activeThread: string | null;
  showResolved: boolean;
  members: MemberView[];
  meId: string | null;
  canComment: boolean;
  canTask: boolean;
  sessions: SessionAttachmentView[];
  mandates: ReadonlyMap<string, MandateView>;
  decisions: ReadonlyMap<string, DecisionView>;
  docTitles: ReadonlyMap<string, string>;
  decisionActions: DecisionActions;
  actions: CommentsActions;
}) {
  const { t } = useTranslation();
  if (!doc) {
    return (
      <div className="bb-rail__panel bb-comments" data-testid="blackboard-comments-panel">
        <p className="bb-muted" data-testid="blackboard-comments-no-doc">
          {t('blackboard.comments.noDoc')}
        </p>
      </div>
    );
  }
  const attached = threads.filter((th) => !th.resolved_at && th.anchor.status !== 'orphaned');
  const detached = threads.filter((th) => !th.resolved_at && th.anchor.status === 'orphaned');
  const resolved = threads.filter((th) => th.resolved_at);
  const shared = { members, meId, canComment, canTask, sessions, mandates, decisions, docTitles, decisionActions, actions };

  return (
    <div className="bb-rail__panel bb-comments" data-testid="blackboard-comments-panel">
      {attached.length === 0 && detached.length === 0 ? (
        <p className="bb-muted" data-testid="blackboard-comments-empty">
          {canComment ? t('blackboard.comments.empty') : t('blackboard.comments.emptyReadOnly')}
        </p>
      ) : null}
      {attached.map((th) => (
        <ThreadCard key={th.id} thread={th} active={th.id === activeThread} {...shared} />
      ))}
      {detached.length > 0 ? (
        <section className="bb-rail__section" data-testid="blackboard-comments-detached">
          <h4>{t('blackboard.comments.detached')}</h4>
          <p className="bb-muted">{t('blackboard.comments.detachedHint')}</p>
          {detached.map((th) => (
            <ThreadCard key={th.id} thread={th} active={th.id === activeThread} {...shared} />
          ))}
        </section>
      ) : null}
      <label className="bb-comments__resolved-toggle">
        <Switch checked={showResolved} onChange={actions.showResolved} />
        <span>{t('blackboard.comments.showResolved')}</span>
      </label>
      {showResolved
        ? resolved.map((th) => <ThreadCard key={th.id} thread={th} active={th.id === activeThread} {...shared} />)
        : null}
    </div>
  );
}

export function ThreadCard({
  thread,
  active,
  variant = 'list',
  members,
  meId,
  canComment,
  canTask,
  sessions,
  mandates,
  decisions,
  docTitles,
  decisionActions,
  actions,
}: ThreadProps & {
  thread: ThreadView;
  active: boolean;
  // In the margin the passage is right beside the card, so the quote is left out, and a card that is
  // not active shows only the first and the latest comment.
  variant?: 'list' | 'margin';
}) {
  const { t } = useTranslation();
  const [replying, setReplying] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const resolved = Boolean(thread.resolved_at);
  const status = thread.anchor.status;
  const margin = variant === 'margin';
  const collapsed = margin && !active;
  const shown = collapsed && thread.comments.length > 2 ? [thread.comments[0], thread.comments[thread.comments.length - 1]] : thread.comments;
  const hidden = thread.comments.length - shown.length;
  return (
    <section
      className={`bb-thread${margin ? ' is-margin' : ''}${active ? ' is-active' : ''}${resolved ? ' is-resolved' : ''}`}
      data-testid="blackboard-thread"
      data-variant={thread.id}
      data-anchor={status}
    >
      {margin ? null : (
        <button type="button" className="bb-thread__quote" data-testid="blackboard-thread-quote" onClick={() => actions.open(active ? null : thread.id)}>
          {thread.anchor.quote}
        </button>
      )}
      {status === 'drifted' && !resolved ? (
        <Tag variant="warning" data-testid="blackboard-thread-drifted">
          {t('blackboard.comments.drifted')}
        </Tag>
      ) : null}
      <ul className="bb-thread__comments">
        {shown.map((c, i) => (
          <Fragment key={c.id}>
            {hidden > 0 && i === 1 ? (
              <li className="bb-thread__more bb-muted" data-testid="blackboard-thread-more">
                {t('blackboard.comments.moreReplies', { count: hidden })}
              </li>
            ) : null}
            {editing === c.id ? (
            <li>
              <Composer
                placeholder=""
                members={members}
                meId={meId}
                canTask={false}
                sessions={[]}
                initial={c.body}
                autoFocus
                submitLabel={t('blackboard.comments.save')}
                testId="blackboard-comment-edit"
                onSubmit={async ({ body }) => {
                  await actions.edit(c.id, body);
                  setEditing(null);
                }}
                onCancel={() => setEditing(null)}
              />
            </li>
          ) : (
            <CommentItem
              comment={c}
              meId={meId}
              mandate={c.mandate_id ? mandates.get(c.mandate_id) : undefined}
              decision={c.decision_id ? decisions.get(c.decision_id) : undefined}
              docTitles={docTitles}
              decisionActions={decisionActions}
              onEdit={canComment && !resolved && c.author_kind === 'person' && c.author_id === meId && !c.mandate_id ? () => setEditing(c.id) : null}
            />
            )}
          </Fragment>
        ))}
      </ul>
      {replying && !resolved && !collapsed ? (
        <Composer
          placeholder={t('blackboard.comments.replyPlaceholder')}
          members={members}
          meId={meId}
          canTask={canTask}
          sessions={sessions}
          scopeSwitch
          autoFocus
          submitLabel={t('blackboard.comments.reply')}
          testId="blackboard-reply-composer"
          onSubmit={async (value) => {
            await actions.reply(thread.id, value);
            setReplying(false);
          }}
          onCancel={() => setReplying(false)}
        />
      ) : null}
      {canComment && !collapsed ? (
        <div className="bb-thread__actions">
          {!resolved && !replying ? (
            <Button size="sm" variant="quiet" icon={<Reply size={13} />} data-testid="blackboard-thread-reply-btn" onClick={() => setReplying(true)}>
              {t('blackboard.comments.reply')}
            </Button>
          ) : null}
          <Button
            size="sm"
            variant="quiet"
            icon={resolved ? <RotateCcw size={13} /> : <Check size={13} />}
            data-testid={resolved ? 'blackboard-thread-reopen-btn' : 'blackboard-thread-resolve-btn'}
            onClick={() => void actions.setResolved(thread.id, !resolved)}
          >
            {resolved ? t('blackboard.comments.reopen') : t('blackboard.comments.resolve')}
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function CommentItem({
  comment,
  meId,
  mandate,
  decision,
  docTitles,
  decisionActions,
  onEdit,
}: {
  comment: CommentView;
  meId: string | null;
  mandate: MandateView | undefined;
  decision: DecisionView | undefined;
  docTitles: ReadonlyMap<string, string>;
  decisionActions: DecisionActions;
  onEdit: (() => void) | null;
}) {
  const { t } = useTranslation();
  const name = comment.author_name ?? '';
  if (comment.author_kind === 'system') {
    return (
      <li className="bb-comment-item is-system" data-testid="blackboard-comment" data-author="system">
        <Info size={12} aria-hidden="true" />
        <span>{noticeText(t, comment.body, name)}</span>
      </li>
    );
  }
  const agent = comment.author_kind === 'agent';
  return (
    <li className={`bb-comment-item${agent ? ' is-agent' : ''}`} data-testid="blackboard-comment" data-author={comment.author_kind}>
      <div className="bb-comment-item__meta">
        {agent ? <Bot size={13} aria-hidden="true" /> : null}
        <strong data-testid="blackboard-comment-author">{agent ? t('blackboard.agents.agentOf', { name }) : name}</strong>
        <span className="bb-muted">{when(comment.created_at)}</span>
        {comment.edited_at ? <span className="bb-muted">{t('blackboard.comments.edited')}</span> : null}
        {comment.mandate_id && !agent ? <TaskTag mandate={mandate} status={comment.mandate_status} /> : null}
        {onEdit ? (
          <button type="button" className="bb-icon-button" aria-label={t('blackboard.comments.edit')} title={t('blackboard.comments.edit')} data-testid="blackboard-comment-edit-btn" onClick={onEdit}>
            <Pencil size={12} />
          </button>
        ) : null}
      </div>
      {decision ? (
        <DecisionCard decision={decision} meId={meId} docTitle={decision.doc_id ? (docTitles.get(decision.doc_id) ?? null) : null} actions={decisionActions} />
      ) : (
        <p className="bb-comment-item__body" data-testid="blackboard-comment-body">
          {comment.body}
        </p>
      )}
    </li>
  );
}
