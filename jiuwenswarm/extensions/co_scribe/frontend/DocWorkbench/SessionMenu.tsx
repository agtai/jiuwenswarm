/**
 * The workbench's session control: which conversation the strip's composer
 * feeds. It sits in the chat strip, next to the composer it governs, and the
 * menu opens upward since the strip is at the foot of the page.
 */
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronUp, Plus, History } from 'lucide-react';

export type SessionMenuProps = {
  /** The current session's title; empty for the "new conversation" placeholder. */
  title: string;
  /** Other sessions, most recent first, that can take over the focused document. */
  recent: { id: string; title: string }[];
  onNew: () => void;
  onSelect: (id: string) => void;
};

export function SessionMenu({ title, recent, onNew, onSelect }: SessionMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);
  return (
    <div ref={rootRef} className="doc-workbench__session" data-testid="doc-workbench-session">
      <button type="button" className="doc-workbench__session-toggle" onClick={() => setOpen((v) => !v)} title={t('docs.workbench.session')} data-testid="doc-workbench-session-toggle">
        <History size={12} />
        <span className="max-w-[160px] truncate">{title || t('docs.workbench.newSession')}</span>
        <ChevronUp size={12} />
      </button>
      {open && (
        <div className="doc-workbench__session-menu" role="menu" data-testid="doc-workbench-session-menu">
          <button type="button" role="menuitem" className="doc-workbench__session-item" onClick={() => { setOpen(false); onNew(); }} data-testid="doc-workbench-session-new">
            <Plus size={13} /> {t('docs.workbench.newSession')}
          </button>
          <div className="doc-workbench__session-label">{t('docs.workbench.recentSessions')}</div>
          {recent.length === 0 && <div className="doc-workbench__session-empty">{t('docs.workbench.noOtherSessions')}</div>}
          {recent.map((s) => (
            <button key={s.id} type="button" role="menuitem" className="doc-workbench__session-item" onClick={() => { setOpen(false); onSelect(s.id); }} title={s.title} data-testid="doc-workbench-session-pick">
              <span className="truncate">{s.title || s.id}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
