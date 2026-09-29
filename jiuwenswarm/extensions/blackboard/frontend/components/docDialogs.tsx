import { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, FileUp } from 'lucide-react';

import { FormDialog } from '../../../../channels/web/frontend/src/components/form';
import { Button, Input, RadioGroup, Switch, Textarea, toast } from '../../../../channels/web/frontend/src/components/ui';
import type { ExportFormat } from '../types';
import { Field } from './Field';
import { Status, useSubmit } from './dialogs';

const MARKDOWN_FILES = '.md,.markdown,.txt,text/markdown,text/plain';

// A button that reads a Markdown file into `onText`.
function MarkdownFileButton({ onText, testId }: { onText: (text: string, name: string) => void; testId: string }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement | null>(null);
  return (
    <>
      <input
        ref={input}
        type="file"
        accept={MARKDOWN_FILES}
        hidden
        data-testid={`${testId}-input`}
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = '';
          if (file) void file.text().then((text) => onText(text, file.name));
        }}
      />
      <Button size="sm" icon={<FileUp size={14} />} data-testid={testId} onClick={() => input.current?.click()}>
        {t('blackboard.docs.chooseFile')}
      </Button>
    </>
  );
}

export function NewDocumentDialog({
  open,
  onCreate,
  onClose,
}: {
  open: boolean;
  onCreate: (title: string, markdown?: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const [title, setTitle] = useState('');
  const [markdown, setMarkdown] = useState<{ text: string; name: string } | null>(null);
  const { busy, error, setError, run } = useSubmit(onClose);
  useEffect(() => {
    if (open) {
      setTitle('');
      setMarkdown(null);
      setError(null);
    }
  }, [open]);
  return (
    <FormDialog
      open={open}
      title={t('blackboard.docs.newTitle')}
      confirmLabel={t('blackboard.docs.create')}
      cancelLabel={t('common.cancel')}
      confirmLoading={busy}
      submitting={busy}
      confirmDisabled={!title.trim()}
      status={<Status error={error} />}
      testIdPrefix="blackboard-new-doc-dialog"
      onConfirm={() => void run(() => onCreate(title.trim(), markdown?.text))}
      onCancel={onClose}
    >
      <Field label={t('blackboard.docs.titleLabel')} htmlFor={titleId}>
        <Input id={titleId} value={title} maxLength={120} autoFocus data-testid="blackboard-new-doc-title" onChange={setTitle} />
      </Field>
      <Field label={t('blackboard.docs.startFrom')} hint={t('blackboard.docs.startFromHint')}>
        <div className="bb-inline">
          <span className="bb-muted" data-testid="blackboard-new-doc-file">
            {markdown ? markdown.name : t('blackboard.docs.emptyDocument')}
          </span>
          <MarkdownFileButton
            testId="blackboard-new-doc-file-btn"
            onText={(text, name) => {
              setMarkdown({ text, name });
              if (!title.trim()) setTitle(name.replace(/\.(md|markdown|txt)$/i, ''));
            }}
          />
        </div>
      </Field>
    </FormDialog>
  );
}

export function ImportMarkdownDialog({
  open,
  docTitle,
  onImport,
  onClose,
}: {
  open: boolean;
  docTitle: string;
  onImport: (markdown: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const textId = useId();
  const [text, setText] = useState('');
  const { busy, error, setError, run } = useSubmit(onClose);
  useEffect(() => {
    if (open) {
      setText('');
      setError(null);
    }
  }, [open]);
  return (
    <FormDialog
      open={open}
      title={t('blackboard.docs.importTitle', { title: docTitle })}
      confirmLabel={t('blackboard.docs.importSubmit')}
      cancelLabel={t('common.cancel')}
      confirmLoading={busy}
      submitting={busy}
      confirmDisabled={!text.trim()}
      status={<Status error={error} />}
      testIdPrefix="blackboard-import-dialog"
      onConfirm={() => void run(() => onImport(text))}
      onCancel={onClose}
    >
      <p className="bb-notice" data-testid="blackboard-import-warning">
        {t('blackboard.docs.importWarning')}
      </p>
      <Field label={t('blackboard.docs.markdownLabel')} htmlFor={textId}>
        <Textarea id={textId} value={text} rows={10} className="bb-markdown-input" data-testid="blackboard-import-text" onChange={setText} />
      </Field>
      <MarkdownFileButton testId="blackboard-import-file-btn" onText={(value) => setText(value)} />
    </FormDialog>
  );
}

// The document as agents read it: Markdown with a block id before every top-level block.
export function MarkdownDialog({
  open,
  docTitle,
  load,
  onClose,
}: {
  open: boolean;
  docTitle: string;
  load: () => Promise<string>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    let current = true;
    setText(null);
    setError(null);
    load().then(
      (value) => current && setText(value),
      (err) => current && setError(err instanceof Error ? err.message : String(err)),
    );
    return () => {
      current = false;
    };
  }, [open, load]);
  const copy = async () => {
    if (text === null) return;
    await navigator.clipboard.writeText(text);
    toast.open({ content: t('blackboard.docs.copied'), variant: 'success' });
  };
  return (
    <FormDialog
      open={open}
      title={t('blackboard.docs.markdownTitle', { title: docTitle })}
      confirmLabel={t('common.close')}
      cancelLabel={t('common.cancel')}
      dialogClassName="bb-dialog--close-only"
      status={<Status error={error} />}
      testIdPrefix="blackboard-markdown-dialog"
      onConfirm={onClose}
      onCancel={onClose}
    >
      <p className="bb-muted">{t('blackboard.docs.markdownHint')}</p>
      <pre className="bb-markdown-view" data-testid="blackboard-markdown-text">
        {text ?? ''}
      </pre>
      <Button size="sm" icon={<Copy size={14} />} disabled={text === null} data-testid="blackboard-markdown-copy-btn" onClick={() => void copy()}>
        {t('blackboard.docs.copy')}
      </Button>
    </FormDialog>
  );
}

// The document as a file: Markdown, Word or PDF of the accepted text, and optionally the decisions
// about it. The file downloads when it is ready.
export function ExportDialog({
  open,
  docTitle,
  onExport,
  onClose,
}: {
  open: boolean;
  docTitle: string;
  onExport: (format: ExportFormat, includeDecisions: boolean) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [format, setFormat] = useState<ExportFormat>('docx');
  const [decisions, setDecisions] = useState(false);
  const { busy, error, setError, run } = useSubmit(onClose);
  useEffect(() => {
    if (open) setError(null);
  }, [open]);
  return (
    <FormDialog
      open={open}
      title={t('blackboard.export.title', { title: docTitle })}
      confirmLabel={t('blackboard.export.confirm')}
      cancelLabel={t('common.cancel')}
      confirmLoading={busy}
      submitting={busy}
      status={<Status error={error} />}
      testIdPrefix="blackboard-export-dialog"
      onConfirm={() => void run(() => onExport(format, decisions))}
      onCancel={onClose}
    >
      <Field label={t('blackboard.export.format')} hint={t('blackboard.export.hint')}>
        <RadioGroup
          aria-label={t('blackboard.export.format')}
          value={format}
          options={[
            { value: 'docx', label: t('blackboard.export.docx') },
            { value: 'pdf', label: t('blackboard.export.pdf') },
            { value: 'md', label: t('blackboard.export.md') },
          ]}
          onChange={(value) => setFormat(value as ExportFormat)}
        />
      </Field>
      <label className="bb-export__option">
        <Switch checked={decisions} data-testid="blackboard-export-decisions" onChange={setDecisions} />
        <span>{t('blackboard.export.decisions')}</span>
      </label>
    </FormDialog>
  );
}
