// A name edited in place: Enter or leaving the field saves, Escape keeps the old name.
import { useEffect, useRef, useState } from 'react';

export function InlineRename({
  value,
  label,
  maxLength,
  testId,
  onSave,
  onDone,
}: {
  value: string;
  label: string;
  maxLength: number;
  testId?: string;
  onSave: (name: string) => Promise<void>;
  onDone: () => void;
}) {
  const [draft, setDraft] = useState(value);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const settled = useRef(false);

  useEffect(() => {
    input.current?.focus();
    input.current?.select();
  }, []);

  const finish = async (save: boolean) => {
    if (settled.current || busy) return;
    const name = draft.replace(/\s+/g, ' ').trim();
    if (!save || !name || name === value) {
      settled.current = true;
      onDone();
      return;
    }
    setBusy(true);
    try {
      await onSave(name);
      settled.current = true;
      onDone();
    } catch {
      // The caller reports the error; the field stays open with what was typed.
      setBusy(false);
      input.current?.focus();
    }
  };

  return (
    <input
      ref={input}
      className="bb-inline-rename"
      value={draft}
      maxLength={maxLength}
      disabled={busy}
      aria-label={label}
      data-testid={testId}
      onChange={(event) => setDraft(event.target.value)}
      onClick={(event) => event.stopPropagation()}
      onBlur={() => void finish(true)}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.preventDefault();
          void finish(true);
        } else if (event.key === 'Escape') {
          event.preventDefault();
          void finish(false);
        }
      }}
    />
  );
}
