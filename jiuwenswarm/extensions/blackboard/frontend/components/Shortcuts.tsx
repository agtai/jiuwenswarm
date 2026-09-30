// Keyboard shortcuts of the Blackboard page, the list that "?" opens, and the document switcher.
// Page shortcuts are Ctrl+Alt with a letter or digit, matched by the physical key so keyboard
// layouts do not matter; AltGr (which some layouts need for typing) never triggers them.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { FileText } from 'lucide-react';

import { FormDialog } from '../../../../channels/web/frontend/src/components/form';
import type { DocView } from '../types';

export interface ShortcutActions {
  togglePanel: (index: number) => void;
  toggleSidebar: () => void;
  toggleDock: () => void;
  toggleChat: () => void;
  newDoc: () => void;
  goToDoc: () => void;
  help: () => void;
}

// What the "?" list shows, in order: [keys, label key].
export const SHORTCUTS: Array<[string, string]> = [
  ['Ctrl+Alt+1 ... 7', 'blackboard.shortcuts.panel'],
  ['Ctrl+Alt+S', 'blackboard.shortcuts.sidebar'],
  ['Ctrl+Alt+B', 'blackboard.shortcuts.dock'],
  ['Ctrl+Alt+J', 'blackboard.shortcuts.chat'],
  ['Ctrl+Alt+O', 'blackboard.shortcuts.goToDoc'],
  ['Ctrl+Alt+N', 'blackboard.shortcuts.newDoc'],
  ['Ctrl+M', 'blackboard.shortcuts.comment'],
  ['Ctrl+B, Ctrl+I, Ctrl+Z, Ctrl+Shift+Z', 'blackboard.shortcuts.editing'],
  ['Alt+Up, Alt+Down', 'blackboard.shortcuts.movePanel'],
  ['Enter, Shift+Enter', 'blackboard.shortcuts.chatSend'],
  ['?', 'blackboard.shortcuts.help'],
];

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return Boolean(el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName)));
}

export function useShortcuts(actions: ShortcutActions, enabled: boolean): void {
  const latest = useRef(actions);
  latest.current = actions;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (event: KeyboardEvent) => {
      const a = latest.current;
      if (event.defaultPrevented || event.metaKey) return;
      if (event.ctrlKey && event.altKey && !event.shiftKey && !event.getModifierState?.('AltGraph')) {
        const digit = /^Digit([1-9])$/.exec(event.code);
        const run: (() => void) | undefined = digit
          ? () => a.togglePanel(Number(digit[1]) - 1)
          : { KeyS: a.toggleSidebar, KeyB: a.toggleDock, KeyJ: a.toggleChat, KeyN: a.newDoc, KeyO: a.goToDoc }[event.code];
        if (run) {
          event.preventDefault();
          run();
        }
        return;
      }
      if (event.key === '?' && !event.ctrlKey && !event.altKey && !typing(event.target)) {
        event.preventDefault();
        a.help();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [enabled]);
}

export function ShortcutsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <FormDialog
      open={open}
      title={t('blackboard.shortcuts.title')}
      confirmLabel={t('common.close')}
      cancelLabel={t('common.cancel')}
      dialogClassName="bb-dialog--close-only"
      testIdPrefix="blackboard-shortcuts-dialog"
      onConfirm={onClose}
      onCancel={onClose}
    >
      <table className="bb-shortcuts">
        <tbody>
          {SHORTCUTS.map(([keys, label]) => (
            <tr key={label}>
              <td>
                {keys.split(', ').map((combo) => (
                  <kbd key={combo}>{combo}</kbd>
                ))}
              </td>
              <td>{t(label)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </FormDialog>
  );
}

// Type part of a document's name, then Enter: quicker than the sidebar in a long workspace.
export function DocSwitcher({
  open,
  docs,
  onPick,
  onClose,
}: {
  open: boolean;
  docs: DocView[];
  onPick: (docId: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const live = docs.filter((d) => !d.archived);
    return q ? live.filter((d) => d.title.toLowerCase().includes(q)) : live;
  }, [docs, query]);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setIndex(0);
    requestAnimationFrame(() => input.current?.focus());
  }, [open]);
  useEffect(() => setIndex(0), [query]);

  if (!open) return null;
  const pick = (doc: DocView | undefined) => {
    if (!doc) return;
    onPick(doc.id);
    onClose();
  };
  const keys = (event: ReactKeyboardEvent) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setIndex((i) => (matches.length ? (i + step + matches.length) % matches.length : 0));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      pick(matches[index]);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
    }
  };

  return (
    <div className="bb-switcher__backdrop" role="presentation" onMouseDown={onClose}>
      <div
        className="bb-switcher"
        role="dialog"
        aria-label={t('blackboard.shortcuts.goToDoc')}
        data-testid="blackboard-doc-switcher"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={keys}
      >
        <input
          ref={input}
          value={query}
          placeholder={t('blackboard.switcher.placeholder')}
          aria-label={t('blackboard.switcher.placeholder')}
          data-testid="blackboard-doc-switcher-input"
          onChange={(event) => setQuery(event.target.value)}
        />
        <ul role="listbox">
          {matches.length === 0 ? <li className="bb-muted">{t('blackboard.switcher.none')}</li> : null}
          {matches.map((doc, i) => (
            <li
              key={doc.id}
              role="option"
              aria-selected={i === index}
              className={i === index ? 'is-active' : undefined}
              data-testid="blackboard-doc-switcher-item"
              data-variant={doc.title}
              onMouseEnter={() => setIndex(i)}
              onClick={() => pick(doc)}
            >
              <FileText size={14} aria-hidden="true" />
              {doc.title}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
