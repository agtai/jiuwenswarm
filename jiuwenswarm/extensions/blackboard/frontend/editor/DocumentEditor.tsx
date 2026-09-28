// The live document view. Loaded lazily, so Tiptap, Yjs and the provider stay out of the app's
// main bundle.
import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { EditorContent, useEditor, type Editor } from '@tiptap/react';
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
} from 'lucide-react';

import { Button, Tag, type TagVariant } from '../../../../channels/web/frontend/src/components/ui';
import { YJS_FIELD, authorColorIndex, blackboardExtensions } from '../../host/docservice/src/schema/extensions.ts';
import type { DocToken } from '../types';
import { authorsOf, type AuthorEntry } from './authors';
import { AuthorStamp } from './authorStamp';
import { DocSession, type ProviderFactory, type SessionState, type SessionStatus } from './session';

export interface DocumentEditorProps {
  docId: string;
  fetchToken: (docId: string) => Promise<DocToken>;
  me: { id: string; name: string };
  // user id -> display name, for the authors legend and suggestion cards.
  names: ReadonlyMap<string, string>;
  // The header's title and menu, rendered by the page.
  header: ReactNode;
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

export default function DocumentEditor({ docId, fetchToken, me, names, header }: DocumentEditorProps) {
  const { t } = useTranslation();
  const { live, state } = useSession(docId, fetchToken);
  const [showAuthors, setShowAuthors] = useState(false);

  const statusLabel = state.readOnly && state.status === 'saved' ? t('blackboard.editor.readOnly') : t(`blackboard.editor.status.${state.status}`);
  return (
    <section className="bb-doc" data-testid="blackboard-doc">
      <header className="bb-doc__head">
        {header}
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
}: {
  ydoc: Y.Doc;
  provider: HocuspocusProvider;
  readOnly: boolean;
  me: { id: string; name: string };
  names: ReadonlyMap<string, string>;
  showAuthors: boolean;
}) {
  const meRef = useRef(me);
  meRef.current = me;
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

  return (
    <div className={`bb-editor${showAuthors ? ' show-authors' : ''}`} data-testid="blackboard-editor" data-readonly={readOnly}>
      {editor && !readOnly ? <Toolbar editor={editor} /> : null}
      {editor && showAuthors ? <AuthorsLegend editor={editor} names={names} /> : null}
      <SuggestionCards names={names}>
        <EditorContent editor={editor} className="bb-editor__scroll" />
      </SuggestionCards>
    </div>
  );
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
        <span key={author.id} className="bb-authors__item" data-testid="blackboard-doc-author" data-variant={author.id}>
          <span className="bb-authors__swatch" data-author-color={author.color} aria-hidden="true" />
          {author.name}
          {author.kind === 'agent' ? <span className="bb-muted">{t('blackboard.editor.agent')}</span> : null}
        </span>
      ))}
    </div>
  );
}

// A card over pending suggestions: who suggested it. Accepting and rejecting come with agent edits.
function SuggestionCards({ names, children }: { names: ReadonlyMap<string, string>; children: ReactNode }) {
  const { t } = useTranslation();
  const wrapper = useRef<HTMLDivElement | null>(null);
  const [card, setCard] = useState<{ left: number; top: number; kind: string; name: string; agent: boolean } | null>(null);

  const onMouseOver = (event: React.MouseEvent) => {
    const target = (event.target as HTMLElement).closest('ins[data-author], del[data-author]') as HTMLElement | null;
    if (!target || !wrapper.current) {
      setCard(null);
      return;
    }
    let author: { id?: string; kind?: string } = {};
    try {
      author = JSON.parse(target.dataset.author ?? '{}');
    } catch {
      author = {};
    }
    const box = target.getBoundingClientRect();
    const frame = wrapper.current.getBoundingClientRect();
    setCard({
      left: box.left - frame.left,
      top: box.bottom - frame.top + 4,
      kind: target.tagName === 'INS' ? 'insertion' : 'deletion',
      name: (author.id && names.get(author.id)) || author.id || '',
      agent: author.kind === 'agent',
    });
  };

  return (
    <div className="bb-suggestions" ref={wrapper} onMouseOver={onMouseOver} onMouseLeave={() => setCard(null)}>
      {children}
      {card ? (
        <div className="bb-suggestion-card" style={{ left: card.left, top: card.top }} data-testid="blackboard-suggestion-card" data-variant={card.kind}>
          <strong>{card.name}</strong>
          {card.agent ? <span className="bb-muted"> {t('blackboard.editor.agent')}</span> : null}
          <div className="bb-muted">{t(`blackboard.editor.suggested.${card.kind}`)}</div>
        </div>
      ) : null}
    </div>
  );
}
