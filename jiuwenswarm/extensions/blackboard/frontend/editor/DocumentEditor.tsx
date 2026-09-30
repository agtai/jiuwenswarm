// The live document view. Loaded lazily, so Tiptap, Yjs and the provider stay out of the app's
// main bundle.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { EditorContent, useEditor, type Editor } from '@tiptap/react';
import { Extension } from '@tiptap/core';
import type { EditorState } from '@tiptap/pm/state';
import Collaboration from '@tiptap/extension-collaboration';
import CollaborationCaret from '@tiptap/extension-collaboration-caret';
import { HocuspocusProvider } from '@hocuspocus/provider';
import * as Y from 'yjs';
import {
  Bold,
  Code,
  Heading1,
  Heading2,
  Heading3,
  Italic,
  List,
  ListChecks,
  ListOrdered,
  Quote,
  Redo2,
  SquareCode,
  Strikethrough,
  Table,
  Undo2,
  Users,
  Check,
  X,
  MessageSquarePlus,
} from 'lucide-react';

import { Button, Tag, type TagVariant } from '../../../../channels/web/frontend/src/components/ui';
import { YJS_FIELD, authorColorIndex, blackboardExtensions } from '../../host/docservice/src/schema/extensions.ts';
import type { AnchorDraft, DocToken, TaskPlace, WorkingPlace } from '../types';
import { authorsOf, type AuthorEntry } from './authors';
import { AuthorStamp } from './authorStamp';
import { CommentMargin } from './CommentMargin';
import { CommentHighlights, anchorForSelection, selectionTooLong, showThreads, threadRange, type ThreadAnchor } from './comments';
import { DocSession, type ProviderFactory, type SessionState, type SessionStatus } from './session';
import { TaskBox } from './TaskBox';
import { TaskMarkers, showTaskMarkers } from './taskMarkers';

export interface DocumentEditorProps {
  docId: string;
  fetchToken: (docId: string) => Promise<DocToken>;
  me: { id: string; name: string };
  // user id -> display name, for the authors legend and suggestion cards.
  names: ReadonlyMap<string, string>;
  // The header's tags and menu, rendered by the page.
  header: ReactNode;
  // The editable name above the content.
  title: ReactNode;
  suggestions: SuggestionActions;
  comments: CommentActions;
  // Ctrl+J: a task for the person's agent from where they are; null for people who cannot give one.
  onTask: ((request: string, place: TaskPlace) => Promise<void>) | null;
  // Where jiuwen is working on tasks given in this document.
  working: WorkingPlace[];
}

export interface CommentActions {
  threads: ThreadAnchor[];
  active: string | null;
  // The passage of the comment being written, shown with a draft card in the margin.
  draft: AnchorDraft | null;
  onOpenThread: (threadId: string | null) => void;
  // Null for people who cannot comment (viewers, archived documents).
  onComment: ((anchor: AnchorDraft) => void) | null;
  // The margin's cards: a thread, and the comment being written.
  renderThread: (threadId: string, active: boolean) => ReactNode;
  renderDraft: () => ReactNode;
}

const DRAFT_ID = '__draft__';

export interface SuggestionActions {
  // Null for people who cannot decide (viewers, archived documents).
  decide: ((ids: string[], action: 'accept' | 'reject') => Promise<void>) | null;
  decideRun: ((mandateId: string, action: 'accept' | 'reject') => Promise<void>) | null;
  // Mandate id -> what the agent was asked to do.
  instructions: ReadonlyMap<string, string>;
}

const STATUS_VARIANT: Record<SessionStatus, TagVariant> = {
  connecting: 'neutral',
  syncing: 'info',
  saved: 'success',
  offline: 'warning',
  unavailable: 'danger',
  closed: 'danger',
};

const CLOSED_STATE: SessionState = { status: 'connecting', readOnly: true, frozen: false, role: null, reason: null };
const noSubscribe = () => () => {};

function useSession(docId: string, fetchToken: DocumentEditorProps['fetchToken']) {
  const [live, setLive] = useState<{ session: DocSession; ydoc: Y.Doc; provider: HocuspocusProvider | null } | null>(null);

  useEffect(() => {
    const ydoc = new Y.Doc();
    let provider: HocuspocusProvider | null = null;
    const factory: ProviderFactory = ({ url, name, token, events }) => {
      provider = new HocuspocusProvider({
        url,
        name,
        document: ydoc,
        token,
        // Updates within this window go out as one; see AuthorStamp for why that matters.
        flushDelay: 100,
        onStatus: ({ status }) => events.onStatus(status),
        onSynced: ({ state }) => events.onSynced(state),
        onUnsyncedChanges: ({ number }) => events.onUnsyncedChanges(number),
        onAuthenticated: ({ scope }) => events.onAuthenticated(scope),
        onAuthenticationFailed: ({ reason }) => events.onAuthenticationFailed(reason),
      });
      return { destroy: () => provider?.destroy() };
    };
    const session = new DocSession(docId, fetchToken, factory);
    setLive({ session, ydoc, provider: null });
    let cancelled = false;
    void session.start().then(() => {
      if (!cancelled && provider) setLive({ session, ydoc, provider });
    });
    return () => {
      cancelled = true;
      session.destroy();
      ydoc.destroy();
    };
  }, [docId, fetchToken]);

  const state = useSyncExternalStore(live?.session.subscribe ?? noSubscribe, live?.session.getState ?? (() => CLOSED_STATE));
  return { live, state };
}

export default function DocumentEditor({ docId, fetchToken, me, names, header, title, suggestions, comments, onTask, working }: DocumentEditorProps) {
  const { t } = useTranslation();
  const { live, state } = useSession(docId, fetchToken);
  const [showAuthors, setShowAuthors] = useState(false);

  const statusLabel = state.readOnly && state.status === 'saved' ? t('blackboard.editor.readOnly') : t(`blackboard.editor.status.${state.status}`);
  return (
    <section className="bb-doc" data-testid="blackboard-doc">
      <header className="bb-doc__head">
        <div className="bb-doc__meta">
          {state.frozen ? (
            <Tag variant="neutral" data-testid="blackboard-doc-frozen">
              {t('blackboard.editor.archived')}
            </Tag>
          ) : null}
          <Tag
            variant={state.readOnly && state.status === 'saved' ? 'neutral' : STATUS_VARIANT[state.status]}
            data-testid="blackboard-doc-status"
            data-variant={state.status}
            data-readonly={state.readOnly ? 'true' : 'false'}
            title={state.reason ? t(`blackboard.editor.reason.${state.reason}`, { defaultValue: state.reason }) : undefined}
          >
            {statusLabel}
          </Tag>
          <Button
            size="sm"
            variant="quiet"
            icon={<Users size={14} />}
            aria-pressed={showAuthors}
            data-testid="blackboard-doc-authors-btn"
            onClick={() => setShowAuthors((on) => !on)}
          >
            {t('blackboard.editor.authors')}
          </Button>
        </div>
      </header>
      {state.status === 'closed' || state.status === 'unavailable' ? (
        <p className="bb-notice bb-notice--error" role="alert" data-testid="blackboard-doc-error">
          {t(`blackboard.editor.reason.${state.reason ?? 'internal'}`, { defaultValue: t('blackboard.errors.generic') })}
        </p>
      ) : null}
      {live?.provider ? (
        <LiveEditor
          key={docId}
          ydoc={live.ydoc}
          provider={live.provider}
          readOnly={state.readOnly}
          me={me}
          names={names}
          showAuthors={showAuthors}
          title={title}
          header={header}
          suggestions={suggestions}
          comments={comments}
          onTask={state.readOnly ? null : onTask}
          working={working}
        />
      ) : (
        <div className="bb-doc__loading" data-testid="blackboard-doc-loading" />
      )}
    </section>
  );
}

function LiveEditor({
  ydoc,
  provider,
  readOnly,
  me,
  names,
  showAuthors,
  title,
  header,
  suggestions,
  comments,
  onTask,
  working,
}: {
  ydoc: Y.Doc;
  provider: HocuspocusProvider;
  readOnly: boolean;
  me: { id: string; name: string };
  names: ReadonlyMap<string, string>;
  showAuthors: boolean;
  title: ReactNode;
  header: ReactNode;
  suggestions: SuggestionActions;
  comments: CommentActions;
  onTask: DocumentEditorProps['onTask'];
  working: WorkingPlace[];
}) {
  const { t } = useTranslation();
  const meRef = useRef(me);
  meRef.current = me;
  const commentsRef = useRef(comments);
  commentsRef.current = comments;
  const frame = useRef<HTMLDivElement | null>(null);
  const [commentAt, setCommentAt] = useState<{ top: number; left: number; tooLong: boolean } | null>(null);
  const [taskAt, setTaskAt] = useState<{ top: number; left: number; place: TaskPlace } | null>(null);
  // Set below once the editor exists; the shortcut reads it when pressed.
  const openTask = useRef<() => boolean>(() => false);
  const editor = useEditor(
    {
      editable: !readOnly,
      extensions: blackboardExtensions({
        collaboration: [
          Collaboration.configure({ document: ydoc, field: YJS_FIELD }),
          CollaborationCaret.configure({
            provider,
            user: { id: me.id, name: me.name },
            render: (user: Record<string, unknown>) => {
              const caret = document.createElement('span');
              caret.className = 'collaboration-carets__caret';
              caret.dataset.authorColor = String(authorColorIndex(String(user.id ?? user.name ?? '')));
              const label = document.createElement('span');
              label.className = 'collaboration-carets__label';
              label.textContent = String(user.name ?? '');
              if (user.kind === 'agent') {
                caret.classList.add('is-agent');
                label.prepend(botIcon());
              }
              caret.append(label);
              return caret;
            },
            selectionRender: (user: Record<string, unknown>) => ({
              nodeName: 'span',
              class: 'collaboration-carets__selection',
              'data-author-color': String(authorColorIndex(String(user.id ?? user.name ?? ''))),
            }),
          }),
          AuthorStamp.configure({ getAuthor: () => ({ id: meRef.current.id, kind: 'person' }), document: ydoc }),
          Extension.create({ name: 'bbTaskShortcut', addKeyboardShortcuts: () => ({ 'Mod-j': () => openTask.current() }) }),
          TaskMarkers.configure({ label: () => t('blackboard.task.working') }),
          CommentHighlights.configure({
            onOpenThread: (id) => {
              if (id === DRAFT_ID || (id === null && !commentsRef.current.active)) return;
              commentsRef.current.onOpenThread(id);
            },
            onComment: (anchor) => {
              const start = commentsRef.current.onComment;
              if (!start) return false;
              start(anchor);
              setCommentAt(null);
              return true;
            },
          }),
        ],
      }),
      editorProps: { attributes: { class: 'bb-editor__content', 'data-testid': 'blackboard-editor-content' } },
    },
    [ydoc, provider],
  );

  useEffect(() => {
    editor?.setEditable(!readOnly);
  }, [editor, readOnly]);

  useEffect(() => {
    editor?.commands.updateUser?.({ id: me.id, name: me.name });
  }, [editor, me.id, me.name]);

  // The threads' passages and the draft's, highlighted; the one in focus scrolled into view. The
  // margin shows a card for each passage that is still in the document.
  const draft = comments.draft;
  const marginAnchors = useMemo(() => {
    const placed = comments.threads.filter((a) => a.status !== 'orphaned');
    return draft ? [...placed, { id: DRAFT_ID, start: draft.start, end: draft.end, quote: draft.quote, status: 'ok' as const }] : placed;
  }, [comments.threads, draft]);
  const focused = comments.active ?? (draft ? DRAFT_ID : null);

  useEffect(() => {
    if (editor) showThreads(editor, marginAnchors, focused);
  }, [editor, marginAnchors, focused]);

  useEffect(() => {
    if (editor) showTaskMarkers(editor, working);
  }, [editor, working]);

  useEffect(() => {
    if (!editor || !comments.active) return;
    const anchor = comments.threads.find((a) => a.id === comments.active);
    const range = anchor ? threadRange(editor.state, anchor) : null;
    if (!range) return;
    const node = editor.view.domAtPos(range.from).node;
    const element = node instanceof Element ? node : node.parentElement;
    element?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [editor, comments.active, comments.threads]);

  // A Comment button next to a selection.
  useEffect(() => {
    if (!editor) return;
    const place = () => {
      const box = frame.current?.getBoundingClientRect();
      const tooLong = !anchorForSelection(editor.state) && selectionTooLong(editor.state);
      if (!box || !commentsRef.current.onComment || (!tooLong && !anchorForSelection(editor.state))) {
        setCommentAt(null);
        return;
      }
      const coords = editor.view.coordsAtPos(editor.state.selection.to);
      setCommentAt({ top: coords.bottom - box.top + 6, left: Math.max(0, coords.left - box.left - 12), tooLong });
    };
    editor.on('selectionUpdate', place);
    editor.on('update', place);
    return () => {
      editor.off('selectionUpdate', place);
      editor.off('update', place);
    };
  }, [editor]);

  const comment = () => {
    const anchor = editor ? anchorForSelection(editor.state) : null;
    if (anchor && comments.onComment) comments.onComment(anchor);
    setCommentAt(null);
  };

  // The task box opens under the cursor, kept inside the editor's width.
  openTask.current = () => {
    const box = frame.current?.getBoundingClientRect();
    if (!editor || !onTask || !box) return false;
    const coords = editor.view.coordsAtPos(editor.state.selection.head);
    const left = Math.max(0, Math.min(coords.left - box.left - 12, box.width - TASK_BOX_WIDTH));
    setTaskAt({ top: coords.bottom - box.top + 6, left, place: placeOf(editor.state) });
    setCommentAt(null);
    return true;
  };
  const closeTask = () => {
    setTaskAt(null);
    editor?.commands.focus();
  };

  return (
    <div
      ref={frame}
      className={`bb-editor${showAuthors ? ' show-authors' : ''}`}
      data-testid="blackboard-editor"
      data-readonly={readOnly}
    >
      {editor && !readOnly ? <Toolbar editor={editor} /> : null}
      {editor && showAuthors ? <AuthorsLegend editor={editor} names={names} /> : null}
      {/* The document menu sits next to the name it acts on. */}
      <div className="bb-doc-titlebar">
        {title}
        {header}
      </div>
      <div className="bb-editor__body">
        <SuggestionCards names={names} actions={readOnly ? { ...suggestions, decide: null, decideRun: null } : suggestions}>
          <EditorContent editor={editor} className="bb-editor__scroll" />
        </SuggestionCards>
        {editor && marginAnchors.length > 0 ? (
          <CommentMargin
            editor={editor}
            anchors={marginAnchors}
            active={focused}
            render={(id, active) => (id === DRAFT_ID ? comments.renderDraft() : comments.renderThread(id, active))}
            onActivate={(id) => comments.onOpenThread(id === DRAFT_ID ? null : id)}
          />
        ) : null}
      </div>
      {taskAt && onTask ? (
        <TaskBox top={taskAt.top} left={taskAt.left} onSend={(request) => onTask(request, taskAt.place)} onClose={closeTask} />
      ) : null}
      {commentAt && comments.onComment && !taskAt ? (
        <button
          type="button"
          className="bb-comment-button"
          style={{ top: commentAt.top, left: commentAt.left }}
          data-testid="blackboard-editor-comment-btn"
          data-variant={commentAt.tooLong ? 'too-long' : 'ready'}
          disabled={commentAt.tooLong}
          title={commentAt.tooLong ? undefined : t('blackboard.comments.addShortcut')}
          onMouseDown={(event) => event.preventDefault()}
          onClick={comment}
        >
          <MessageSquarePlus size={14} aria-hidden="true" />
          {commentAt.tooLong ? t('blackboard.comments.tooLong') : t('blackboard.comments.add')}
          {commentAt.tooLong ? null : <kbd className="bb-comment-button__key">Ctrl+M</kbd>}
        </button>
      ) : null}
    </div>
  );
}

const TASK_BOX_WIDTH = 380;
const MAX_TASK_QUOTE = 2000;

// The top-level blocks at the selection and the selected words: where a Ctrl+J task was given.
function placeOf(state: EditorState): TaskPlace {
  const { from, to, empty, $from, $to } = state.selection;
  const block = (depth: number, node: () => { attrs: Record<string, unknown> }) => {
    const id = depth >= 1 ? node().attrs.id : null;
    return typeof id === 'string' && id ? id : undefined;
  };
  const quote = empty ? '' : state.doc.textBetween(from, to, ' ').trim();
  return {
    block_from: block($from.depth, () => $from.node(1)),
    block_to: block($to.depth, () => $to.node(1)),
    ...(quote && quote.length <= MAX_TASK_QUOTE ? { quote } : {}),
  };
}

// Lucide's "bot" glyph, for the label of an agent's caret (built by hand: carets are plain DOM).
function botIcon(): SVGSVGElement {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  for (const [key, value] of Object.entries({ viewBox: '0 0 24 24', width: '11', height: '11', fill: 'none', stroke: 'currentColor', 'stroke-width': '2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round' })) {
    svg.setAttribute(key, value);
  }
  svg.setAttribute('class', 'collaboration-carets__bot');
  svg.setAttribute('aria-hidden', 'true');
  const shapes: Array<[string, Record<string, string>]> = [
    ['path', { d: 'M12 8V4H8' }],
    ['rect', { width: '16', height: '12', x: '4', y: '8', rx: '2' }],
    ['path', { d: 'M2 14h2' }],
    ['path', { d: 'M20 14h2' }],
    ['path', { d: 'M15 13v2' }],
    ['path', { d: 'M9 13v2' }],
  ];
  for (const [tag, attrs] of shapes) {
    const el = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    svg.append(el);
  }
  return svg;
}

function useEditorTick(editor: Editor, delayMs = 0): number {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let timer: number | undefined;
    const bump = () => {
      if (delayMs === 0) setTick((n) => n + 1);
      else {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => setTick((n) => n + 1), delayMs);
      }
    };
    editor.on('transaction', bump);
    return () => {
      window.clearTimeout(timer);
      editor.off('transaction', bump);
    };
  }, [editor, delayMs]);
  return tick;
}

function Toolbar({ editor }: { editor: Editor }) {
  const { t } = useTranslation();
  useEditorTick(editor);
  const chain = () => editor.chain().focus();
  const items: Array<{ key: string; icon: ReactNode; active?: boolean; run: () => void; disabled?: boolean }> = [
    { key: 'undo', icon: <Undo2 size={15} />, run: () => chain().undo().run(), disabled: !editor.can().undo() },
    { key: 'redo', icon: <Redo2 size={15} />, run: () => chain().redo().run(), disabled: !editor.can().redo() },
    { key: 'h1', icon: <Heading1 size={15} />, active: editor.isActive('heading', { level: 1 }), run: () => chain().toggleHeading({ level: 1 }).run() },
    { key: 'h2', icon: <Heading2 size={15} />, active: editor.isActive('heading', { level: 2 }), run: () => chain().toggleHeading({ level: 2 }).run() },
    { key: 'h3', icon: <Heading3 size={15} />, active: editor.isActive('heading', { level: 3 }), run: () => chain().toggleHeading({ level: 3 }).run() },
    { key: 'bold', icon: <Bold size={15} />, active: editor.isActive('bold'), run: () => chain().toggleBold().run() },
    { key: 'italic', icon: <Italic size={15} />, active: editor.isActive('italic'), run: () => chain().toggleItalic().run() },
    { key: 'strike', icon: <Strikethrough size={15} />, active: editor.isActive('strike'), run: () => chain().toggleStrike().run() },
    { key: 'code', icon: <Code size={15} />, active: editor.isActive('code'), run: () => chain().toggleCode().run() },
    { key: 'bulletList', icon: <List size={15} />, active: editor.isActive('bulletList'), run: () => chain().toggleBulletList().run() },
    { key: 'orderedList', icon: <ListOrdered size={15} />, active: editor.isActive('orderedList'), run: () => chain().toggleOrderedList().run() },
    { key: 'taskList', icon: <ListChecks size={15} />, active: editor.isActive('taskList'), run: () => chain().toggleTaskList().run() },
    { key: 'blockquote', icon: <Quote size={15} />, active: editor.isActive('blockquote'), run: () => chain().toggleBlockquote().run() },
    { key: 'codeBlock', icon: <SquareCode size={15} />, active: editor.isActive('codeBlock'), run: () => chain().toggleCodeBlock().run() },
    {
      key: 'table',
      icon: <Table size={15} />,
      active: editor.isActive('table'),
      run: () => chain().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run(),
      disabled: editor.isActive('table'),
    },
  ];
  return (
    <div className="bb-toolbar" role="toolbar" aria-label={t('blackboard.editor.toolbar')} data-testid="blackboard-editor-toolbar">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`bb-toolbar__btn${item.active ? ' is-active' : ''}`}
          aria-pressed={item.active ?? undefined}
          aria-label={t(`blackboard.editor.tools.${item.key}`)}
          title={t(`blackboard.editor.tools.${item.key}`)}
          disabled={item.disabled}
          data-testid="blackboard-editor-tool"
          data-variant={item.key}
          onMouseDown={(event) => event.preventDefault()}
          onClick={item.run}
        >
          {item.icon}
        </button>
      ))}
    </div>
  );
}

function AuthorsLegend({ editor, names }: { editor: Editor; names: ReadonlyMap<string, string> }) {
  const { t } = useTranslation();
  const tick = useEditorTick(editor, 300);
  const authors: AuthorEntry[] = useMemo(() => authorsOf(editor.getJSON(), names), [editor, names, tick]);
  return (
    <div className="bb-authors" data-testid="blackboard-doc-authors">
      {authors.length === 0 ? <span className="bb-muted">{t('blackboard.editor.noAuthors')}</span> : null}
      {authors.map((author) => (
        <span key={author.key} className="bb-authors__item" data-testid="blackboard-doc-author" data-variant={author.key}>
          <span className="bb-authors__swatch" data-author-color={author.color} data-author-kind={author.kind} aria-hidden="true" />
          {author.kind === 'agent' ? t('blackboard.editor.agentOf', { name: author.name }) : author.name}
        </span>
      ))}
    </div>
  );
}

// A card for a pending suggestion, opened by clicking it: who suggested what, and for editors Accept
// and Reject, plus accepting or rejecting everything one agent run suggested in the document.
function SuggestionCards({
  names,
  actions,
  children,
}: {
  names: ReadonlyMap<string, string>;
  actions: SuggestionActions;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const wrapper = useRef<HTMLDivElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<{
    left: number;
    top: number;
    id: string;
    kind: string;
    name: string;
    agent: boolean;
    mandate: string | null;
  } | null>(null);

  useEffect(() => {
    if (!card) return;
    const close = (event: Event) => {
      if (event instanceof KeyboardEvent ? event.key === 'Escape' : !wrapper.current?.querySelector('.bb-suggestion-card')?.contains(event.target as Node)) {
        setCard(null);
      }
    };
    document.addEventListener('keydown', close);
    document.addEventListener('mousedown', close);
    return () => {
      document.removeEventListener('keydown', close);
      document.removeEventListener('mousedown', close);
    };
  }, [card]);

  const onClick = (event: React.MouseEvent) => {
    const target = (event.target as HTMLElement).closest('ins[data-author], del[data-author]') as HTMLElement | null;
    if (!target || !wrapper.current) return;
    let author: { id?: string; kind?: string; mandate?: string | null } = {};
    let id = '';
    try {
      author = JSON.parse(target.dataset.author ?? '{}');
      id = JSON.parse(target.dataset.id ?? '""');
    } catch {
      return;
    }
    const box = target.getBoundingClientRect();
    const frame = wrapper.current.getBoundingClientRect();
    const name = (author.id && names.get(author.id)) || author.id || '';
    // A replacement is one suggestion id on both an ins and a del.
    const tags = new Set(
      [...wrapper.current.querySelectorAll<HTMLElement>('ins[data-id], del[data-id]')]
        .filter((el) => el.dataset.id === target.dataset.id)
        .map((el) => el.tagName),
    );
    setCard({
      left: Math.max(0, box.left - frame.left),
      top: box.bottom - frame.top + 4,
      id: String(id),
      kind: tags.size > 1 ? 'replacement' : target.tagName === 'INS' ? 'insertion' : 'deletion',
      name: author.kind === 'agent' ? t('blackboard.editor.agentOf', { name }) : name,
      agent: author.kind === 'agent',
      mandate: author.kind === 'agent' ? (author.mandate ?? null) : null,
    });
  };

  const act = async (run: () => Promise<void>) => {
    setBusy(true);
    try {
      await run();
      setCard(null);
    } finally {
      setBusy(false);
    }
  };

  const instruction = card?.mandate ? actions.instructions.get(card.mandate) : undefined;
  return (
    <div className="bb-suggestions" ref={wrapper} onClick={onClick}>
      {children}
      {card ? (
        <div className="bb-suggestion-card" style={{ left: card.left, top: card.top }} data-testid="blackboard-suggestion-card" data-variant={card.kind}>
          <strong data-testid="blackboard-suggestion-author">{card.name}</strong>
          <div className="bb-muted">{t(`blackboard.editor.suggested.${card.kind}`)}</div>
          {instruction ? <div className="bb-suggestion-card__why">{instruction}</div> : null}
          {actions.decide ? (
            <div className="bb-suggestion-card__actions">
              <Button size="sm" variant="primary" icon={<Check size={13} />} loading={busy} data-testid="blackboard-suggestion-accept-btn" onClick={() => void act(() => actions.decide!([card.id], 'accept'))}>
                {t('blackboard.editor.accept')}
              </Button>
              <Button size="sm" icon={<X size={13} />} disabled={busy} data-testid="blackboard-suggestion-reject-btn" onClick={() => void act(() => actions.decide!([card.id], 'reject'))}>
                {t('blackboard.editor.reject')}
              </Button>
              {card.mandate && actions.decideRun ? (
                <Button
                  size="sm"
                  variant="quiet"
                  disabled={busy}
                  data-testid="blackboard-suggestion-accept-run-btn"
                  onClick={() => void act(() => actions.decideRun!(card.mandate!, 'accept'))}
                >
                  {t('blackboard.editor.acceptRun')}
                </Button>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
