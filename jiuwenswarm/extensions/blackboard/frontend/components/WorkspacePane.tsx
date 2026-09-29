import { Suspense, lazy, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Archive,
  ArchiveRestore,
  BookMarked,
  Download,
  FileCode2,
  FileInput,
  FilePlus2,
  FileText,
  History,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Trash2,
} from 'lucide-react';

import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Tag,
} from '../../../../channels/web/frontend/src/components/ui';
import type { CommentActions, SuggestionActions } from '../editor/DocumentEditor';
import type { VersionActions } from '../editor/VersionView';
import type { DocServiceStatus, DocToken, DocView, VersionView as Version, WorkspaceView } from '../types';

const DocumentEditor = lazy(() => import('../editor/DocumentEditor'));
const VersionView = lazy(() => import('../editor/VersionView'));

export interface DocActions {
  rename: (doc: DocView, title: string) => Promise<void>;
  setPinned: (doc: DocView, pinned: boolean) => void;
  setInstructions: (doc: DocView) => void;
  importMarkdown: (doc: DocView) => void;
  viewMarkdown: (doc: DocView) => void;
  showHistory: (doc: DocView) => void;
  exportDoc: (doc: DocView) => void;
  archive: (doc: DocView) => void;
}

export function WorkspacePane({
  workspace,
  doc,
  hasDocs,
  canEdit,
  docservice,
  me,
  names,
  fetchToken,
  docActions,
  suggestionActions,
  commentActions,
  openVersion,
  versions,
  versionActions,
  onNewDoc,
  onRename,
  onArchive,
  onUnarchive,
  onDelete,
}: {
  workspace: WorkspaceView;
  doc: DocView | null;
  hasDocs: boolean;
  canEdit: boolean;
  docservice: DocServiceStatus | null;
  me: { id: string; name: string } | null;
  names: ReadonlyMap<string, string>;
  fetchToken: (docId: string) => Promise<DocToken>;
  docActions: DocActions;
  suggestionActions: SuggestionActions;
  commentActions: CommentActions;
  // A version shown in place of the editor, and the document's versions to compare it with.
  openVersion: Version | null;
  versions: Version[];
  versionActions: VersionActions;
  onNewDoc: () => void;
  onRename: () => void;
  onArchive: () => void;
  onUnarchive: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const owner = workspace.role === 'owner';
  const serviceDown = docservice !== null && docservice.status !== 'running';
  return (
    <section className="bb-workspace" data-testid="blackboard-workspace">
      <header className="bb-workspace__head">
        <div className="bb-workspace__heading">
          <h2 data-testid="blackboard-workspace-title">{workspace.title}</h2>
          <p className="bb-muted">
            <span data-testid="blackboard-workspace-handle">{t('blackboard.workspace.handle', { name: workspace.name })}</span>
            <Tag variant={owner ? 'info' : 'neutral'} data-testid="blackboard-workspace-role" data-variant={workspace.role}>
              {t(`blackboard.roles.${workspace.role}`)}
            </Tag>
          </p>
        </div>
        {owner ? (
          <div className="bb-workspace__actions">
            <Button size="sm" variant="quiet" icon={<Pencil size={14} />} data-testid="blackboard-workspace-rename-btn" onClick={onRename}>
              {t('blackboard.workspace.rename')}
            </Button>
            {workspace.archived ? (
              <>
                <Button
                  size="sm"
                  variant="quiet"
                  icon={<ArchiveRestore size={14} />}
                  data-testid="blackboard-workspace-unarchive-btn"
                  onClick={onUnarchive}
                >
                  {t('blackboard.workspace.unarchive')}
                </Button>
                <Button size="sm" variant="danger" icon={<Trash2 size={14} />} data-testid="blackboard-workspace-delete-btn" onClick={onDelete}>
                  {t('blackboard.workspace.delete')}
                </Button>
              </>
            ) : (
              <Button size="sm" variant="quiet" icon={<Archive size={14} />} data-testid="blackboard-workspace-archive-btn" onClick={onArchive}>
                {t('blackboard.workspace.archive')}
              </Button>
            )}
          </div>
        ) : null}
      </header>
      {workspace.archived ? (
        <p className="bb-notice" data-testid="blackboard-workspace-archived-notice">
          {t('blackboard.workspace.archivedNotice')}
        </p>
      ) : null}
      {serviceDown ? (
        <p className="bb-notice bb-notice--error" role="alert" data-testid="blackboard-docservice-notice" data-variant={docservice.reason ?? docservice.status}>
          {t(`blackboard.docservice.${docservice.reason ?? docservice.status}`, { defaultValue: t('blackboard.docservice.down') })}
        </p>
      ) : null}
      {doc && me && openVersion ? (
        <Suspense fallback={<div className="bb-doc__loading" data-testid="blackboard-doc-loading" />}>
          <VersionView
            key={doc.id}
            title={doc.title}
            header={<DocHeader doc={doc} canEdit={canEdit} actions={docActions} />}
            version={openVersion}
            versions={versions}
            actions={versionActions}
          />
        </Suspense>
      ) : doc && me ? (
        <Suspense fallback={<div className="bb-doc__loading" data-testid="blackboard-doc-loading" />}>
          <DocumentEditor
            key={doc.id}
            docId={doc.id}
            fetchToken={fetchToken}
            me={me}
            names={names}
            header={<DocHeader doc={doc} canEdit={canEdit} actions={docActions} />}
            title={<DocTitle key={doc.id} doc={doc} canEdit={canEdit} onRename={docActions.rename} />}
            suggestions={suggestionActions}
            comments={commentActions}
          />
        </Suspense>
      ) : (
        <div className="bb-empty" data-testid="blackboard-documents-empty">
          <FileText aria-hidden="true" />
          <p>{hasDocs ? t('blackboard.docs.pick') : t('blackboard.workspace.documentsEmpty')}</p>
          {canEdit && !serviceDown ? (
            <Button size="sm" variant="primary" icon={<FilePlus2 size={14} />} data-testid="blackboard-empty-new-doc-btn" onClick={onNewDoc}>
              {t('blackboard.docs.new')}
            </Button>
          ) : null}
        </div>
      )}
    </section>
  );
}

// The document's name as its first line, as in Obsidian: editing it renames the document.
function DocTitle({
  doc,
  canEdit,
  onRename,
}: {
  doc: DocView;
  canEdit: boolean;
  onRename: (doc: DocView, title: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLTextAreaElement>(null);
  const cancelled = useRef(false);
  const [value, setValue] = useState(doc.title);
  const [focused, setFocused] = useState(false);
  // A rename on its way, so the old name does not flash back before the list reloads.
  const [saving, setSaving] = useState<string | null>(null);

  useEffect(() => {
    if (focused || (saving !== null && doc.title !== saving)) return;
    setSaving(null);
    setValue(doc.title);
  }, [doc.title, focused, saving]);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  if (!canEdit) {
    return (
      <h1 className="bb-doc-title" data-testid="blackboard-doc-title">
        {doc.title}
      </h1>
    );
  }
  const commit = () => {
    const next = value.replace(/\s+/g, ' ').trim();
    if (!next || next === doc.title) {
      setValue(doc.title);
      return;
    }
    setSaving(next);
    onRename(doc, next).catch(() => setSaving(null));
  };
  return (
    <textarea
      ref={ref}
      className="bb-doc-title"
      rows={1}
      maxLength={200}
      value={value}
      aria-label={t('blackboard.docs.titleLabel')}
      data-testid="blackboard-doc-title"
      onChange={(event) => setValue(event.target.value.replace(/\n/g, ' '))}
      onFocus={() => setFocused(true)}
      onBlur={() => {
        setFocused(false);
        if (cancelled.current) {
          cancelled.current = false;
          setValue(doc.title);
        } else {
          commit();
        }
      }}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === 'Escape') {
          event.preventDefault();
          cancelled.current = event.key === 'Escape';
          event.currentTarget.blur();
        }
      }}
    />
  );
}

function DocHeader({ doc, canEdit, actions }: { doc: DocView; canEdit: boolean; actions: DocActions }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const items: Array<{ key: string; icon: ReactNode; label: string; run: () => void; danger?: boolean; show: boolean }> = [
    {
      key: 'pin',
      icon: doc.is_pinned ? <PinOff size={14} /> : <Pin size={14} />,
      label: doc.is_pinned ? t('blackboard.docs.unpin') : t('blackboard.docs.pin'),
      run: () => actions.setPinned(doc, !doc.is_pinned),
      show: canEdit,
    },
    {
      key: 'instructions',
      icon: <BookMarked size={14} />,
      label: t('blackboard.docs.makeInstructions'),
      run: () => actions.setInstructions(doc),
      show: canEdit && !doc.is_instructions,
    },
    { key: 'import', icon: <FileInput size={14} />, label: t('blackboard.docs.import'), run: () => actions.importMarkdown(doc), show: canEdit },
    { key: 'markdown', icon: <FileCode2 size={14} />, label: t('blackboard.docs.viewMarkdown'), run: () => actions.viewMarkdown(doc), show: true },
    { key: 'history', icon: <History size={14} />, label: t('blackboard.history.open'), run: () => actions.showHistory(doc), show: true },
    { key: 'export', icon: <Download size={14} />, label: t('blackboard.export.open'), run: () => actions.exportDoc(doc), show: true },
    {
      key: 'archive',
      icon: <Archive size={14} />,
      label: t('blackboard.docs.archive'),
      run: () => actions.archive(doc),
      danger: true,
      show: canEdit && !doc.is_instructions,
    },
  ];
  return (
    <div className="bb-doc__title">
      {doc.is_instructions ? (
        <Tag variant="info" data-testid="blackboard-doc-instructions-tag">
          {t('blackboard.docs.instructions')}
        </Tag>
      ) : null}
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button size="sm" variant="quiet" icon={<MoreHorizontal size={16} />} aria-label={t('blackboard.docs.menu')} data-testid="blackboard-doc-menu-btn" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" data-testid="blackboard-doc-menu">
          {items
            .filter((item) => item.show)
            .map((item) => (
              <DropdownMenuItem
                key={item.key}
                icon={item.icon}
                danger={item.danger}
                data-testid="blackboard-doc-menu-item"
                data-variant={item.key}
                onSelect={item.run}
              >
                {item.label}
              </DropdownMenuItem>
            ))}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}
