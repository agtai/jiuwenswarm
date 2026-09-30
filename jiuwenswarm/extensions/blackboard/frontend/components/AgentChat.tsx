// A chat box over the Blackboard page, like a game's chat window: the person talks to their agent
// sessions without leaving the documents. It reads the app's own chat store, which receives every
// session's events, and sends and stops turns the way the main chat does.
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, ExternalLink, Minus, Plus, Send, Square, X } from 'lucide-react';

import { Button } from '../../../../channels/web/frontend/src/components/ui';
import { InlineQuestionCard } from '../../../../channels/web/frontend/src/components/ChatPanel/InlineQuestionCard';
import { InteractionSlot } from '../../../../channels/web/frontend/src/components/InteractionSlot';
import { QaSummaryCard } from '../../../../channels/web/frontend/src/components/InteractionSlot/QaSummaryCard';
import { isQaSummaryContent } from '../../../../channels/web/frontend/src/components/InteractionSlot/qaSummary';
import { MarkdownRenderer } from '../../../../channels/web/frontend/src/components/MarkdownRenderer';
import { beginHistoryRestore, HISTORY_GET_METHOD } from '../../../../channels/web/frontend/src/features/historyRestore';
import { answerSessionQuestion } from '../../../../channels/web/frontend/src/features/sessionAnswers';
import { webRequest } from '../../../../channels/web/frontend/src/services/webClient';
import { useChatStore } from '../../../../channels/web/frontend/src/stores/chatStore';
import type { UserAnswer } from '../../../../channels/web/frontend/src/types';
import type { Message } from '../../../../channels/web/frontend/src/types/message';
import { MAX_SESSION_TITLE } from '../controller';
import { clamp, closeChat, LIMITS, openChat, updateLayout, useLayout } from '../layout';
import type { DocView, WorkspaceView } from '../types';
import { InlineRename } from './InlineRename';
import { Resizer } from './Resizer';

// What the person is looking at, told to the model only (ahead of their words), so "the section
// on X" is looked up in the workspace and not on this computer.
export function pageContext(workspace: WorkspaceView, doc: DocView | null): string {
  const open = doc ? `, with the document "${doc.title}" (doc id ${doc.id}) open` : '';
  return (
    `[Blackboard] This message was written in the chat box of the Blackboard workspace "${workspace.title}" ` +
    `(@bb:${workspace.name})${open}. When it mentions a document, section, heading or passage without saying ` +
    'where it is, it means this workspace: find it with blackboard_read and blackboard_list_docs first. These are ' +
    'Blackboard documents, not files on this computer.'
  );
}

// Loads a session's recent history into the chat store, unless the store or the main chat already
// has it (two restores of one session would feed each other).
function useHistory(sessionId: string): boolean {
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    const store = useChatStore.getState();
    const runtime = store.getRuntime(sessionId);
    if (runtime && (runtime.messages.length > 0 || runtime.historyPagerMeta || runtime.isLoadingHistory)) return;
    if (store.activeSessionId === sessionId) return;
    store.ensureRuntime(sessionId);
    setLoading(true);
    const done = () => setLoading(false);
    const handle = beginHistoryRestore({
      sessionId,
      onReady: (messages) => {
        // Live messages that arrived meanwhile win over the older history.
        if (!useChatStore.getState().getRuntime(sessionId)?.messages.length) {
          useChatStore.getState().replaceHistoryMessages(sessionId, messages);
        }
        done();
      },
      onEmpty: done,
      onFailure: done,
      onError: done,
    });
    webRequest(HISTORY_GET_METHOD, { session_id: sessionId, cursor: null, limit: 50 }).catch(() => {
      handle.dispose();
      done();
    });
    return () => handle.dispose();
  }, [sessionId]);
  return loading;
}

// What the box shows: people's and the agent's words, not tool calls or system notes.
function visible(messages: Message[]): Message[] {
  return messages.filter((m) => (m.role === 'user' || m.role === 'assistant') && !m.toolCall && !m.toolResult && m.content.trim());
}

function Conversation({ sessionId, title, context }: { sessionId: string; title: string; context: string }) {
  const { t } = useTranslation();
  const loading = useHistory(sessionId);
  const messages = useChatStore((s) => s.runtimes[sessionId]?.messages);
  const processing = useChatStore((s) => Boolean(s.runtimes[sessionId]?.isProcessing));
  const waiting = useChatStore((s) => (s.runtimes[sessionId]?.pendingQuestions.length ?? 0) > 0);
  const tool = useChatStore((s) => {
    const runtime = s.runtimes[sessionId];
    const last = runtime?.toolExecutionOrder[runtime.toolExecutionOrder.length - 1];
    const execution = last ? runtime?.toolExecutions.get(last) : undefined;
    return execution && execution.status === 'pending' ? execution.toolCall.name : null;
  });
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const shown = visible(messages ?? []);

  useLayoutEffect(() => {
    const el = list.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [shown.length, shown[shown.length - 1]?.content, processing]);

  const send = async () => {
    const content = draft.trim();
    if (!content || processing) return;
    setError(null);
    const store = useChatStore.getState();
    store.ensureRuntime(sessionId);
    // The main chat adds the person's message itself before sending; so does the box.
    store.addMessage(sessionId, { id: `user-bb-${Date.now()}`, role: 'user', content, timestamp: new Date().toISOString() });
    store.setProcessing(sessionId, true);
    store.setThinking(sessionId, true);
    setDraft('');
    try {
      await webRequest('chat.send', { session_id: sessionId, content, mode: 'agent', metadata: { interaction_context: context } });
    } catch (e) {
      store.setProcessing(sessionId, false);
      store.setThinking(sessionId, false);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const answer = (requestId: string, answers: UserAnswer[], source?: string) =>
    answerSessionQuestion(sessionId, requestId, answers, source);

  const stop = () =>
    void webRequest('chat.interrupt', { session_id: sessionId, intent: 'cancel', mode: 'agent' }).catch((e) =>
      setError(e instanceof Error ? e.message : String(e)),
    );

  const keys = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };

  return (
    <>
      <div ref={list} className="bb-agent-chat__list" data-testid="blackboard-agent-chat-list" aria-live="polite">
        {loading ? <p className="bb-muted">{t('blackboard.agentChat.loading')}</p> : null}
        {!loading && shown.length === 0 ? <p className="bb-muted">{t('blackboard.agentChat.empty', { title })}</p> : null}
        {shown.map((m) =>
          isQaSummaryContent(m.content) ? (
            // How the person answered a question, as the chat page shows it.
            <div key={m.renderKey ?? m.id} className="bb-agent-chat__qa" data-testid="blackboard-agent-chat-message" data-role="answers">
              <QaSummaryCard content={m.content} />
            </div>
          ) : (
            <div
              key={m.renderKey ?? m.id}
              className={`bb-agent-chat__msg is-${m.role}`}
              data-testid="blackboard-agent-chat-message"
              data-role={m.role}
            >
              {m.role === 'assistant' ? (
                <MarkdownRenderer content={m.content} isStreaming={m.isStreaming} className="chat-text chat-markdown" />
              ) : (
                m.content
              )}
            </div>
          ),
        )}
        {processing && !waiting ? (
          <p className="bb-agent-chat__working bb-muted" data-testid="blackboard-agent-chat-working">
            {tool ? t('blackboard.agentChat.usingTool', { tool: tool.replace(/_/g, ' ') }) : t('blackboard.agentChat.working')}
          </p>
        ) : null}
      </div>
      {/* Permission prompts and the agent's questions, answered here the way the chat page does. */}
      {waiting ? (
        <div className="bb-agent-chat__question" data-testid="blackboard-agent-chat-question">
          <InteractionSlot sessionId={sessionId} onSubmit={answer} />
          <InlineQuestionCard sessionId={sessionId} onSubmit={answer} />
        </div>
      ) : null}
      {error ? (
        <p className="bb-dialog-error bb-agent-chat__error" role="alert">
          {error}
        </p>
      ) : null}
      <div className="bb-agent-chat__composer">
        <textarea
          value={draft}
          rows={2}
          placeholder={t('blackboard.agentChat.placeholder')}
          aria-label={t('blackboard.agentChat.placeholder')}
          data-testid="blackboard-agent-chat-input"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={keys}
        />
        {processing ? (
          <Button size="sm" icon={<Square size={14} />} data-testid="blackboard-agent-chat-stop-btn" onClick={stop}>
            {t('blackboard.agentChat.stop')}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="primary"
            icon={<Send size={14} />}
            disabled={!draft.trim()}
            title={`${t('blackboard.agentChat.send')} (Enter)`}
            data-testid="blackboard-agent-chat-send-btn"
            onClick={() => void send()}
          >
            {t('blackboard.agentChat.send')}
          </Button>
        )}
      </div>
    </>
  );
}

export function AgentChat({
  workspace,
  doc,
  titles,
  onOpenFull,
  onRename,
  onNew,
}: {
  workspace: WorkspaceView;
  doc: DocView | null;
  // Session id to the name shown on its tab.
  titles: (sessionId: string) => string;
  onOpenFull: (sessionId: string) => void;
  // Rejects (after reporting) when the name was not kept, so the field stays open.
  onRename: (sessionId: string, title: string) => Promise<void>;
  // A new session on this workspace, opened as a tab; null for people who cannot start one.
  onNew: (() => Promise<void>) | null;
}) {
  const { t } = useTranslation();
  const layout = useLayout();
  const [renaming, setRenaming] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const box = useRef<HTMLElement>(null);
  // The size shown when a resize began (the stored one may be larger than the page allows).
  const size = useRef({ width: 0, height: 0 });
  const current = layout.chat && layout.chats.includes(layout.chat) ? layout.chat : layout.chats[layout.chats.length - 1];
  // Over the document, left of the panels on the right, so it never hides a panel's buttons.
  const right = { right: 44 + (layout.dockHidden ? 0 : layout.dockWidth) + 16 };
  const busy = useChatStore((s) => layout.chats.filter((id) => s.runtimes[id]?.isProcessing).length);
  if (!current) return null;

  // The box is pinned at the bottom right, so it grows up and to the left.
  const measure = () => {
    const rect = box.current?.getBoundingClientRect();
    if (rect) size.current = { width: rect.width, height: rect.height };
  };
  const resize = (dx: number, dy: number) =>
    updateLayout({
      chatWidth: clamp(size.current.width - dx, LIMITS.chatWidth),
      chatHeight: clamp(size.current.height - dy, LIMITS.chatHeight),
    });
  const dragCorner = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    measure();
    const [x, y] = [event.clientX, event.clientY];
    const move = (e: globalThis.PointerEvent) => resize(e.clientX - x, e.clientY - y);
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      document.body.classList.remove('bb-resizing');
    };
    document.body.classList.add('bb-resizing');
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  if (layout.chatMinimized) {
    return (
      <button
        type="button"
        className="bb-agent-chat-pill"
        style={right}
        data-testid="blackboard-agent-chat-pill"
        onClick={() => updateLayout({ chatMinimized: false })}
      >
        <Bot size={14} aria-hidden="true" />
        {t('blackboard.agentChat.title')}
        {busy ? <span className="bb-agent-chat-pill__dot" aria-label={t('blackboard.agentChat.working')} /> : null}
      </button>
    );
  }

  return (
    <section
      ref={box}
      className="bb-agent-chat"
      style={{ ...right, width: layout.chatWidth, height: layout.chatHeight }}
      aria-label={t('blackboard.agentChat.title')}
      data-testid="blackboard-agent-chat"
    >
      <Resizer
        orientation="vertical"
        label={t('blackboard.agentChat.resize')}
        testId="blackboard-agent-chat-resizer-left"
        onStart={measure}
        onResize={(delta) => resize(delta, 0)}
      />
      <Resizer
        orientation="horizontal"
        label={t('blackboard.agentChat.resize')}
        testId="blackboard-agent-chat-resizer-top"
        onStart={measure}
        onResize={(delta) => resize(0, delta)}
      />
      <div className="bb-agent-chat__corner" aria-hidden="true" data-testid="blackboard-agent-chat-resizer-corner" onPointerDown={dragCorner} />
      <header className="bb-agent-chat__head">
        <div className="bb-agent-chat__tabs" role="tablist">
          {layout.chats.map((id) => (
            <span key={id} className={`bb-agent-chat__tab${id === current ? ' is-active' : ''}`}>
              {renaming === id ? (
                <InlineRename
                  value={titles(id)}
                  label={t('blackboard.agents.renameLabel')}
                  maxLength={MAX_SESSION_TITLE}
                  testId="blackboard-agent-chat-rename-input"
                  onSave={(name) => onRename(id, name)}
                  onDone={() => setRenaming(null)}
                />
              ) : (
                <button
                  type="button"
                  role="tab"
                  aria-selected={id === current}
                  title={`${titles(id)} (${t('blackboard.agentChat.renameHint')})`}
                  data-testid="blackboard-agent-chat-tab"
                  data-variant={id}
                  onClick={() => openChat(id)}
                  onDoubleClick={() => setRenaming(id)}
                >
                  <Bot size={13} aria-hidden="true" />
                  <span>{titles(id)}</span>
                </button>
              )}
              <button
                type="button"
                className="bb-icon-button"
                aria-label={t('blackboard.agentChat.close', { title: titles(id) })}
                data-testid="blackboard-agent-chat-close-btn"
                onClick={() => closeChat(id)}
              >
                <X size={12} />
              </button>
            </span>
          ))}
          {onNew ? (
            <button
              type="button"
              className="bb-icon-button bb-agent-chat__new"
              disabled={starting}
              aria-label={t('blackboard.agentChat.newSession')}
              title={t('blackboard.agentChat.newSession')}
              data-testid="blackboard-agent-chat-new-btn"
              onClick={() => {
                setStarting(true);
                void onNew().finally(() => setStarting(false));
              }}
            >
              <Plus size={14} />
            </button>
          ) : null}
        </div>
        <button
          type="button"
          className="bb-icon-button"
          aria-label={t('blackboard.agentChat.openFull')}
          title={t('blackboard.agentChat.openFull')}
          data-testid="blackboard-agent-chat-full-btn"
          onClick={() => onOpenFull(current)}
        >
          <ExternalLink size={14} />
        </button>
        <button
          type="button"
          className="bb-icon-button"
          aria-label={t('blackboard.agentChat.minimize')}
          title={`${t('blackboard.agentChat.minimize')} (Ctrl+Alt+J)`}
          data-testid="blackboard-agent-chat-minimize-btn"
          onClick={() => updateLayout({ chatMinimized: true })}
        >
          <Minus size={14} />
        </button>
      </header>
      <Conversation key={current} sessionId={current} title={titles(current)} context={pageContext(workspace, doc)} />
    </section>
  );
}
