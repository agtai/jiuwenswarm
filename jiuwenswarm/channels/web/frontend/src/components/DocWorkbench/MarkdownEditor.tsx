/**
 * The app's own editor for markdown files: neither platform has one to embed.
 * Whole-file write-back through the panel (`clouddoc.write_doc`), which records
 * the person's save as a receipt. A refresh triggered by a new receipt never
 * overwrites unsaved local edits.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { webRequest } from '../../services/webClient';
import { MarkdownRenderer } from '../MarkdownRenderer';
import type { WorkbenchTab } from '../../stores/docWorkbenchStore';

type View = 'edit' | 'preview' | 'split';

export function MarkdownEditor({ tab, nonce, highlightLines, onSaved }: {
  tab: WorkbenchTab;
  nonce: number;
  /** 1-based inclusive line range to highlight (from a receipt's locate). */
  highlightLines: [number, number] | null;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [view, setView] = useState<View>('split');
  const [base, setBase] = useState<{ text: string; revision: string | null } | null>(null);
  const [text, setText] = useState('');
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dirty = base !== null && text !== base.text;

  const load = useCallback(async () => {
    const out = await webRequest<{ result: string; text?: string; revision_id?: string | null; detail?: string }>('clouddoc.read_doc', { doc_id: tab.docId });
    if (out?.result !== 'ok') {
      setNote(out?.detail || out?.result || t('docs.history.failed'));
      return;
    }
    setBase({ text: out.text ?? '', revision: out.revision_id ?? null });
    setText(out.text ?? '');
    setNote(null);
  }, [tab.docId, t]);

  // Initial load, and reloads on a new receipt -- unless the person is mid-edit.
  useEffect(() => {
    if (dirty) { setNote(t('docs.workbench.mdStaleWhileEditing')); return; }
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab.docId, nonce]);

  const save = useCallback(async () => {
    if (!base || !dirty) return;
    setBusy(true);
    try {
      const out = await webRequest<{ result: string; revision_id?: string | null; receipt_id?: string; detail?: string }>('clouddoc.write_doc', {
        doc_id: tab.docId, text, base_revision_id: base.revision,
      });
      if (out?.result === 'ok' || out?.result === 'unchanged') {
        setBase({ text, revision: out.revision_id ?? base.revision });
        setNote(out.receipt_id ? t('docs.workbench.mdSaved', { id: out.receipt_id.slice(0, 8) }) : null);
        onSaved();
      } else {
        setNote(out?.detail || out?.result || t('docs.history.failed'));
      }
    } finally {
      setBusy(false);
    }
  }, [base, dirty, tab.docId, text, t, onSaved]);

  const lines = useMemo(() => text.split('\n'), [text]);
  const [hl0, hl1] = highlightLines ?? [0, -1];

  return (
    <div className="doc-workbench__body" data-testid="doc-workbench-md">
      <div className="doc-workbench__md-toolbar">
        <span>{t('docs.workbench.mdEditor')}</span>
        <span className="doc-workbench__seg" role="tablist">
          {(['edit', 'preview', 'split'] as View[]).map((v) => (
            <button key={v} type="button" className={view === v ? 'is-on' : ''} onClick={() => setView(v)} data-testid="doc-workbench-md-view" data-variant={v}>
              {t(`docs.workbench.mdView.${v}`)}
            </button>
          ))}
        </span>
        <span className="flex-1" />
        {note && <span data-testid="doc-workbench-md-note" className="truncate">{note}</span>}
        <button type="button" className="inline-flex h-[26px] items-center rounded-md bg-accent px-3 text-xs font-medium text-accent-foreground disabled:opacity-50" disabled={!dirty || busy} onClick={() => void save()} data-testid="doc-workbench-md-save">
          {t('docs.workbench.mdSave')}
        </button>
      </div>
      <div className="doc-workbench__md">
        {view !== 'preview' && (highlightLines ? (
          <div className="doc-workbench__md-lines" data-testid="doc-workbench-md-lines">
            {lines.map((line, i) => (
              <div key={i} className={`doc-workbench__md-line${i + 1 >= hl0 && i + 1 <= hl1 ? ' doc-workbench__md-line--hit' : ''}`}>
                <span className="doc-workbench__md-gutter">{i + 1}</span><span>{line}</span>
              </div>
            ))}
          </div>
        ) : (
          <textarea
            className="doc-workbench__md-editor"
            value={text}
            onChange={(e) => setText(e.target.value)}
            spellCheck={false}
            data-testid="doc-workbench-md-textarea"
          />
        ))}
        {view !== 'edit' && (
          <div className="doc-workbench__md-preview"><MarkdownRenderer content={text} testId="doc-workbench-md-preview" /></div>
        )}
      </div>
    </div>
  );
}
