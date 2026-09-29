import { useRef, useState, type DragEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { ExternalLink, FileText, Image as ImageIcon, Pencil, Trash2, Upload } from 'lucide-react';

import { Button, Input } from '../../../../channels/web/frontend/src/components/ui';
import type { ReferenceView } from '../types';

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ReferencesPanel({
  references,
  canEdit,
  maxUploadMb,
  onUpload,
  onOpen,
  onRemove,
  onSetNote,
}: {
  references: ReferenceView[];
  canEdit: boolean;
  maxUploadMb: number;
  onUpload: (files: File[]) => Promise<void>;
  onOpen: (reference: ReferenceView) => void;
  onRemove: (reference: ReferenceView) => void;
  onSetNote: (reference: ReferenceView, note: string) => Promise<void>;
}) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [editing, setEditing] = useState<{ id: string; note: string } | null>(null);

  const upload = async (files: File[]) => {
    if (files.length === 0) return;
    setUploading(true);
    try {
      await onUpload(files);
    } finally {
      setUploading(false);
    }
  };

  const dropProps = canEdit
    ? {
        onDragOver: (event: DragEvent) => {
          if (!event.dataTransfer.types.includes('Files')) return;
          event.preventDefault();
          setDragging(true);
        },
        onDragLeave: (event: DragEvent) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        },
        onDrop: (event: DragEvent) => {
          event.preventDefault();
          setDragging(false);
          void upload(Array.from(event.dataTransfer.files));
        },
      }
    : {};

  return (
    <div className={`bb-rail__panel bb-references${dragging ? ' is-dragging' : ''}`} data-testid="blackboard-references-panel" {...dropProps}>
      <div className="bb-rail__head">
        <span className="bb-muted">{t('blackboard.references.limit', { mb: maxUploadMb })}</span>
        {canEdit ? (
          <>
            <input
              ref={input}
              type="file"
              multiple
              hidden
              data-testid="blackboard-references-file-input"
              onChange={(event) => {
                const files = Array.from(event.target.files ?? []);
                event.target.value = '';
                void upload(files);
              }}
            />
            <Button
              size="sm"
              icon={<Upload size={14} />}
              loading={uploading}
              data-testid="blackboard-references-upload-btn"
              onClick={() => input.current?.click()}
            >
              {t('blackboard.references.upload')}
            </Button>
          </>
        ) : null}
      </div>
      {canEdit ? (
        <p className="bb-references__drop" data-testid="blackboard-references-drop">
          {t('blackboard.references.drop')}
        </p>
      ) : null}
      {references.length === 0 ? (
        <p className="bb-muted" data-testid="blackboard-references-empty">
          {t('blackboard.references.empty')}
        </p>
      ) : null}
      <ul className="bb-reference-list" data-testid="blackboard-reference-list">
        {references.map((ref) => (
          <li key={ref.id} className="bb-reference" data-testid="blackboard-reference-item" data-variant={ref.name}>
            <button type="button" className="bb-reference__open" data-testid="blackboard-reference-open-btn" onClick={() => onOpen(ref)}>
              {ref.kind === 'image' ? <ImageIcon size={16} aria-hidden="true" /> : <FileText size={16} aria-hidden="true" />}
              <span className="bb-reference__name">{ref.name}</span>
              <ExternalLink size={12} aria-hidden="true" className="bb-reference__open-icon" />
            </button>
            <p className="bb-reference__meta">
              {formatSize(ref.size)}
              {ref.uploaded_by_name ? `, ${ref.uploaded_by_name}` : ''}
            </p>
            {editing?.id === ref.id ? (
              <div className="bb-inline">
                <Input
                  value={editing.note}
                  maxLength={500}
                  autoFocus
                  aria-label={t('blackboard.references.note')}
                  data-testid="blackboard-reference-note-input"
                  onChange={(note) => setEditing({ id: ref.id, note })}
                />
                <Button
                  size="sm"
                  variant="primary"
                  data-testid="blackboard-reference-note-save-btn"
                  onClick={() => void onSetNote(ref, editing.note.trim()).then(() => setEditing(null))}
                >
                  {t('blackboard.rename.submit')}
                </Button>
              </div>
            ) : ref.note ? (
              <p className="bb-reference__note" data-testid="blackboard-reference-note">
                {ref.note}
              </p>
            ) : null}
            {canEdit && editing?.id !== ref.id ? (
              <div className="bb-reference__actions">
                <Button
                  size="sm"
                  variant="quiet"
                  icon={<Pencil size={13} />}
                  data-testid="blackboard-reference-note-btn"
                  onClick={() => setEditing({ id: ref.id, note: ref.note })}
                >
                  {ref.note ? t('blackboard.references.editNote') : t('blackboard.references.addNote')}
                </Button>
                <Button
                  size="sm"
                  variant="quiet"
                  icon={<Trash2 size={13} />}
                  data-testid="blackboard-reference-remove-btn"
                  onClick={() => onRemove(ref)}
                >
                  {t('blackboard.references.remove')}
                </Button>
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

// Images and PDFs open in a preview; other files in a new tab.
export function ReferencePreview({ reference, url }: { reference: ReferenceView; url: string }) {
  if (reference.kind === 'image') {
    return <img className="bb-preview__image" src={url} alt={reference.name} data-testid="blackboard-reference-preview-image" />;
  }
  return <iframe className="bb-preview__frame" src={url} title={reference.name} data-testid="blackboard-reference-preview-frame" />;
}
