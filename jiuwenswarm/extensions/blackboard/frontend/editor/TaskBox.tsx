// The Ctrl+J box next to the cursor: a task for the person's agent, given from where they are in
// the document. Enter sends, Shift+Enter adds a line, Escape (or a click elsewhere with nothing
// typed) closes it. Once sent it closes; the place then shows that jiuwen is working.
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Send } from 'lucide-react';

export function TaskBox({
  top,
  left,
  onSend,
  onClose,
}: {
  top: number;
  left: number;
  onSend: (request: string) => Promise<void>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const empty = useRef(true);
  empty.current = !draft.trim();

  useEffect(() => input.current?.focus(), []);

  useEffect(() => {
    const outside = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node) && empty.current) onClose();
    };
    document.addEventListener('mousedown', outside);
    return () => document.removeEventListener('mousedown', outside);
  }, []);

  const send = async () => {
    const request = draft.trim();
    if (!request || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSend(request);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
      input.current?.focus();
    }
  };

  const keys = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
    } else if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  };

  return (
    <div
      ref={box}
      className="bb-task-box"
      style={{ top, left }}
      role="dialog"
      aria-label={t('blackboard.task.title')}
      data-testid="blackboard-task-box"
    >
      <div className="bb-task-box__row">
        <Bot size={16} className="bb-task-box__icon" aria-hidden="true" />
        <textarea
          ref={input}
          rows={1}
          value={draft}
          disabled={busy}
          placeholder={t('blackboard.task.placeholder')}
          aria-label={t('blackboard.task.title')}
          data-testid="blackboard-task-box-input"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={keys}
        />
        <button
          type="button"
          className="bb-icon-button"
          aria-label={t('blackboard.task.send')}
          disabled={busy || !draft.trim()}
          data-testid="blackboard-task-box-send-btn"
          onClick={() => void send()}
        >
          <Send size={14} />
        </button>
      </div>
      {error ? (
        <p className="bb-dialog-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
