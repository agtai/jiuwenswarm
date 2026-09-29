// A comment or chat message: @ opens a list of the agent and the members, and a message that names
// the agent shows where its task runs (and, for a comment, whether it may edit the whole document).
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Send } from 'lucide-react';

import { Button, Select, Switch } from '../../../../channels/web/frontend/src/components/ui';
import { AGENT_HANDLE, mentionAt, namesAgent } from '../conversation';
import type { MemberView, SessionAttachmentView } from '../types';

export interface ComposerSubmit {
  body: string;
  wholeDocument: boolean;
  sessionId: string | null;
}

interface Candidate {
  key: string;
  handle: string;
  label: string;
  agent: boolean;
}

export function Composer({
  placeholder,
  members,
  meId,
  canTask,
  sessions,
  scopeSwitch = false,
  submitLabel,
  testId,
  autoFocus = false,
  initial = '',
  onSubmit,
  onCancel,
}: {
  placeholder: string;
  members: MemberView[];
  meId: string | null;
  // Editors and owners may give the agent a task.
  canTask: boolean;
  // This person's sessions working on the workspace, to run a task in one of them.
  sessions: SessionAttachmentView[];
  scopeSwitch?: boolean;
  submitLabel: string;
  testId: string;
  autoFocus?: boolean;
  initial?: string;
  onSubmit: (value: ComposerSubmit) => Promise<void>;
  onCancel?: () => void;
}) {
  const { t } = useTranslation();
  const [body, setBody] = useState(initial);
  const [caret, setCaret] = useState(initial.length);
  const [picked, setPicked] = useState(0);
  const [busy, setBusy] = useState(false);
  const [wholeDocument, setWholeDocument] = useState(false);
  const [sessionId, setSessionId] = useState('');
  const box = useRef<HTMLTextAreaElement | null>(null);
  // Where the caret goes once a picked mention is in the text. Set in the same commit as the new
  // text, so keys typed right after the pick land after the mention.
  const pendingCaret = useRef<number | null>(null);

  // Focused without scrolling: a composer in the editor's margin is drawn once before it is moved
  // beside its passage, and scrolling to that first place would jump the page.
  useEffect(() => {
    if (autoFocus) box.current?.focus({ preventScroll: true });
  }, [autoFocus]);

  useLayoutEffect(() => {
    const at = pendingCaret.current;
    if (at === null || !box.current) return;
    pendingCaret.current = null;
    box.current.focus();
    box.current.setSelectionRange(at, at);
  }, [body]);

  const typing = mentionAt(body, caret);
  const candidates = useMemo<Candidate[]>(() => {
    if (!typing) return [];
    const query = typing.query.toLowerCase();
    const all: Candidate[] = [
      { key: 'agent', handle: AGENT_HANDLE, label: t('blackboard.composer.agent'), agent: true },
      ...members
        .filter((m) => m.user_id !== meId && !m.disabled)
        .map((m) => ({ key: m.user_id, handle: m.display_name, label: m.display_name, agent: false })),
    ];
    return all.filter((c) => c.handle.toLowerCase().startsWith(query) || c.label.toLowerCase().includes(query)).slice(0, 6);
  }, [typing, members, meId, t]);

  const choose = (candidate: Candidate) => {
    if (!typing) return;
    const next = `${body.slice(0, typing.start)}@${candidate.handle} ${body.slice(caret)}`;
    const at = typing.start + candidate.handle.length + 2;
    pendingCaret.current = at;
    setBody(next);
    setCaret(at);
    setPicked(0);
  };

  const submit = async () => {
    if (!body.trim() || busy) return;
    setBusy(true);
    try {
      await onSubmit({ body: body.trim(), wholeDocument, sessionId: sessionId || null });
      setBody('');
      setCaret(0);
      setWholeDocument(false);
    } catch {
      // The caller showed the error; the text stays for another try.
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (candidates.length > 0) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        setPicked((i) => (i + (event.key === 'ArrowDown' ? 1 : candidates.length - 1)) % candidates.length);
        return;
      }
      if (event.key === 'Enter' || event.key === 'Tab') {
        event.preventDefault();
        choose(candidates[Math.min(picked, candidates.length - 1)]);
        return;
      }
    }
    if (event.key === 'Escape' && onCancel) {
      event.preventDefault();
      onCancel();
      return;
    }
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };

  const asksAgent = namesAgent(body);
  return (
    <div className="bb-composer" data-testid={testId}>
      <div className="bb-composer__box">
        <textarea
          ref={box}
          className="bb-composer__input"
          rows={2}
          value={body}
          placeholder={placeholder}
          maxLength={4000}
          data-testid={`${testId}-input`}
          onChange={(event) => {
            setBody(event.target.value);
            setCaret(event.target.selectionStart ?? event.target.value.length);
            setPicked(0);
          }}
          onSelect={(event) => setCaret(event.currentTarget.selectionStart ?? 0)}
          onKeyDown={onKeyDown}
        />
        {candidates.length > 0 ? (
          <ul className="bb-composer__mentions" role="listbox" data-testid={`${testId}-mentions`}>
            {candidates.map((c, i) => (
              <li key={c.key}>
                <button
                  type="button"
                  role="option"
                  aria-selected={i === picked}
                  className={i === picked ? 'is-picked' : ''}
                  data-testid={`${testId}-mention-option`}
                  data-variant={c.handle}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(c)}
                >
                  {c.agent ? <Bot size={13} aria-hidden="true" /> : null}
                  <span>@{c.handle}</span>
                  {c.agent ? <span className="bb-muted">{c.label}</span> : null}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      {asksAgent && !canTask ? (
        <p className="bb-muted bb-composer__hint" data-testid={`${testId}-agent-hint`}>
          {t('blackboard.composer.editorsOnly')}
        </p>
      ) : null}
      {asksAgent && canTask ? (
        <div className="bb-composer__task" data-testid={`${testId}-task-options`}>
          {scopeSwitch ? (
            <label className="bb-composer__switch">
              <Switch checked={wholeDocument} onChange={setWholeDocument} />
              <span>{t('blackboard.composer.wholeDocument')}</span>
            </label>
          ) : null}
          {sessions.length > 0 ? (
            <Select
              data-testid={`${testId}-session-select`}
              aria-label={t('blackboard.composer.session')}
              value={sessionId}
              options={[
                { value: '', label: t('blackboard.composer.defaultSession') },
                ...sessions.map((s) => ({ value: s.session_id, label: t('blackboard.agents.sessionSince', { time: new Date(s.attached_at).toLocaleString() }) })),
              ]}
              onChange={setSessionId}
            />
          ) : null}
        </div>
      ) : null}
      <div className="bb-composer__actions">
        {onCancel ? (
          <Button size="sm" variant="quiet" data-testid={`${testId}-cancel-btn`} onClick={onCancel}>
            {t('common.cancel')}
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="primary"
          icon={<Send size={13} />}
          loading={busy}
          disabled={!body.trim()}
          data-testid={`${testId}-send-btn`}
          onClick={() => void submit()}
        >
          {submitLabel}
        </Button>
      </div>
    </div>
  );
}
