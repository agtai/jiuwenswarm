// One version of a document in place of the editor: what changed since another version (the one
// before it by default), or the version itself as it read, suggestions and all. Editors can restore
// it; anyone can download it as Markdown. Loaded lazily with the editor.
import { Fragment, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { EditorContent, useEditor } from '@tiptap/react';
import { ArrowLeft, Download, RotateCcw } from 'lucide-react';

import { Button, Select, Tabs, Tag } from '../../../../channels/web/frontend/src/components/ui';
import { blackboardExtensions } from '../../host/docservice/src/schema/extensions.ts';
import { versionAuthors } from '../components/HistoryPanel';
import type { DiffBlockView, DiffView, VersionView as Version } from '../types';

export interface VersionActions {
  content: (versionId: string) => Promise<{ doc: Record<string, unknown> }>;
  diff: (to: string, from: string | null) => Promise<DiffView>;
  markdown: (versionId: string) => Promise<string>;
  // Null for people who cannot restore (viewers, commenters, archived documents).
  restore: ((version: Version) => void) | null;
  close: () => void;
}

type Mode = 'changes' | 'document';

// Runs of more unchanged blocks than this fold into one line.
const FOLD_AT = 3;

const quiet = (block: DiffBlockView) => block.status === 'unchanged' && block.pending === block.was_pending;

function fileName(title: string, version: Version): string {
  const stamp = version.created_at.slice(0, 16).replace('T', ' ').replace(':', '-');
  return `${title} (${stamp}).md`.replace(/[\\/:*?"<>|]+/g, ' ');
}

function save(name: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function VersionView({
  title,
  header,
  version,
  versions,
  actions,
}: {
  title: string;
  header: ReactNode;
  version: Version;
  // The document's versions, newest first, to compare with an older one.
  versions: Version[];
  actions: VersionActions;
}) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>('changes');
  const [from, setFrom] = useState('');
  const [diff, setDiff] = useState<DiffView | null>(null);
  const [doc, setDoc] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const older = useMemo(() => {
    const at = versions.findIndex((v) => v.id === version.id);
    return at < 0 ? [] : versions.slice(at + 1);
  }, [versions, version.id]);

  useEffect(() => {
    setFrom('');
  }, [version.id]);

  useEffect(() => {
    let live = true;
    setError(null);
    if (mode === 'changes') {
      setDiff(null);
      actions.diff(version.id, from || null).then(
        (result) => live && setDiff(result),
        (e) => live && setError(e instanceof Error ? e.message : String(e)),
      );
    } else {
      setDoc(null);
      actions.content(version.id).then(
        (result) => live && setDoc(result.doc),
        (e) => live && setError(e instanceof Error ? e.message : String(e)),
      );
    }
    return () => {
      live = false;
    };
  }, [version.id, mode, from]);

  const download = async () => {
    try {
      save(fileName(title, version), await actions.markdown(version.id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const when = new Date(version.created_at).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  return (
    <section className="bb-doc bb-version" data-testid="blackboard-version-view" data-variant={version.id}>
      <header className="bb-doc__head">{header}</header>
      <div className="bb-version__bar">
        <div className="bb-version__what">
          <strong data-testid="blackboard-version-title">{t('blackboard.history.versionOf', { time: when })}</strong>
          <span className="bb-muted">
            {[t(`blackboard.history.reason.${version.reason}`), versionAuthors(t, version), version.label].filter(Boolean).join(' - ')}
          </span>
        </div>
        <div className="bb-version__actions">
          <Button size="sm" variant="quiet" icon={<ArrowLeft size={14} />} data-testid="blackboard-version-close-btn" onClick={actions.close}>
            {t('blackboard.history.back')}
          </Button>
          <Button size="sm" icon={<Download size={14} />} data-testid="blackboard-version-download-btn" onClick={() => void download()}>
            {t('blackboard.history.download')}
          </Button>
          {actions.restore ? (
            <Button size="sm" variant="primary" icon={<RotateCcw size={14} />} data-testid="blackboard-version-restore-btn" onClick={() => actions.restore!(version)}>
              {t('blackboard.history.restore')}
            </Button>
          ) : null}
        </div>
      </div>
      <div className="bb-version__modes">
        <Tabs<Mode>
          items={[
            { value: 'changes', label: t('blackboard.history.changes'), testId: 'blackboard-version-mode-changes' },
            { value: 'document', label: t('blackboard.history.document'), testId: 'blackboard-version-mode-document' },
          ]}
          value={mode}
          onChange={setMode}
          wrapperTestId="blackboard-version-modes"
        />
        {mode === 'changes' && older.length > 0 ? (
          <Select
            data-testid="blackboard-version-compare-select"
            aria-label={t('blackboard.history.compareWith')}
            value={from}
            options={[
              { value: '', label: t('blackboard.history.previous') },
              ...older.map((v) => ({ value: v.id, label: `${new Date(v.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })} - ${t(`blackboard.history.reason.${v.reason}`)}` })),
            ]}
            onChange={setFrom}
          />
        ) : null}
      </div>
      {error ? (
        <p className="bb-notice bb-notice--error" role="alert" data-testid="blackboard-version-error">
          {error}
        </p>
      ) : null}
      <div className="bb-version__body">
        {mode === 'changes' ? (
          diff ? <Changes diff={diff} /> : <div className="bb-doc__loading" />
        ) : doc ? (
          <ReadOnlyDoc key={version.id} json={doc} />
        ) : (
          <div className="bb-doc__loading" />
        )}
      </div>
    </section>
  );
}

function ReadOnlyDoc({ json }: { json: Record<string, unknown> }) {
  const editor = useEditor({
    editable: false,
    extensions: blackboardExtensions(),
    content: json,
    editorProps: { attributes: { class: 'bb-editor__content', 'data-testid': 'blackboard-version-content' } },
  });
  return (
    <div className="bb-editor bb-editor--readonly">
      <EditorContent editor={editor} />
    </div>
  );
}

function Changes({ diff }: { diff: DiffView }) {
  const { t } = useTranslation();
  const [unfolded, setUnfolded] = useState<Set<number>>(new Set());
  const counts = (['changed', 'added', 'removed', 'moved'] as const).filter((s) => diff.summary[s]);

  // Runs of unchanged blocks, so long ones can fold.
  const runs: Array<{ start: number; blocks: DiffBlockView[] }> = [];
  diff.blocks.forEach((block, i) => {
    const last = runs[runs.length - 1];
    if (quiet(block) && last && quiet(last.blocks[0])) last.blocks.push(block);
    else runs.push({ start: i, blocks: [block] });
  });

  return (
    <div className="bb-diff" data-testid="blackboard-diff">
      <p className="bb-muted" data-testid="blackboard-diff-summary">
        {diff.from === null ? t('blackboard.history.firstVersion') : null}
        {diff.from !== null && counts.length === 0 ? t('blackboard.history.noChanges') : null}
        {counts.map((s) => t(`blackboard.history.count.${s}`, { count: diff.summary[s] })).join(', ')}
      </p>
      {runs.map((run) =>
        run.blocks.length > FOLD_AT && quiet(run.blocks[0]) && !unfolded.has(run.start) ? (
          <button
            key={run.start}
            type="button"
            className="bb-diff__fold"
            data-testid="blackboard-diff-fold"
            onClick={() => setUnfolded(new Set(unfolded).add(run.start))}
          >
            {t('blackboard.history.unchangedBlocks', { count: run.blocks.length })}
          </button>
        ) : (
          <Fragment key={run.start}>
            {run.blocks.map((block, i) => (
              <DiffBlock key={`${run.start}-${i}`} block={block} />
            ))}
          </Fragment>
        ),
      )}
    </div>
  );
}

function DiffBlock({ block }: { block: DiffBlockView }) {
  const { t } = useTranslation();
  const decided = block.was_pending && !block.pending;
  return (
    <div className={`bb-diff__block is-${block.status}`} data-testid="blackboard-diff-block" data-variant={block.status}>
      {block.status !== 'unchanged' || block.pending || decided ? (
        <div className="bb-diff__tags">
          {block.status !== 'unchanged' ? (
            <Tag variant={block.status === 'removed' ? 'danger' : block.status === 'added' ? 'success' : 'info'}>{t(`blackboard.history.status.${block.status}`)}</Tag>
          ) : null}
          {block.pending ? <Tag variant="warning">{t('blackboard.history.pending')}</Tag> : null}
          {decided ? <Tag variant="neutral">{t('blackboard.history.decided')}</Tag> : null}
        </div>
      ) : null}
      <div className="bb-diff__text">
        {block.inline
          ? block.inline.map((part, i) =>
              part.op === 'ins' ? <ins key={i}>{part.text}</ins> : part.op === 'del' ? <del key={i}>{part.text}</del> : <span key={i}>{part.text}</span>,
            )
          : block.markdown || <em className="bb-muted">{t('blackboard.history.emptyBlock')}</em>}
      </div>
    </div>
  );
}
