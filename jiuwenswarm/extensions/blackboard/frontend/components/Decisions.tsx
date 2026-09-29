// The agent's questions: one card per decision, in the Decisions tab, under the question in the chat,
// and in the thread of a comment task.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Check, FileText, Send, X } from 'lucide-react';

import { Button, Tag, type TagVariant } from '../../../../channels/web/frontend/src/components/ui';
import type { DecisionStatus, DecisionView } from '../types';

const STATUS_VARIANT: Record<DecisionStatus, TagVariant> = {
  open: 'warning',
  proposed: 'info',
  answered: 'success',
  cancelled: 'neutral',
};

const ORDER: Record<DecisionStatus, number> = { open: 0, proposed: 0, answered: 1, cancelled: 2 };

export interface DecisionActions {
  // Null for people who cannot answer (below editor).
  answer: ((id: string, answer: { option: number } | { text: string }) => Promise<void>) | null;
  accept: (id: string) => Promise<void>;
  cancel: (id: string) => Promise<void>;
  openDoc: (docId: string) => void;
}

export function DecisionCard({
  decision,
  meId,
  docTitle,
  actions,
}: {
  decision: DecisionView;
  meId: string | null;
  docTitle: string | null;
  actions: DecisionActions;
}) {
  const { t } = useTranslation();
  const [option, setOption] = useState<number | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const requester = decision.requester_id === meId;
  const open = decision.status === 'open' || decision.status === 'proposed';
  const canAnswer = open && actions.answer !== null;
  const canCancel = open && (requester || actions.answer !== null);

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
      setOption(null);
      setText('');
    } finally {
      setBusy(false);
    }
  };

  const answer = () =>
    run(() => actions.answer!(decision.id, text.trim() ? { text: text.trim() } : { option: option! }));

  return (
    <article className={`bb-decision is-${decision.status}`} data-testid="blackboard-decision-card" data-variant={decision.status}>
      <header className="bb-decision__head">
        <span className="bb-decision__who">
          <Bot size={13} aria-hidden="true" />
          {t('blackboard.decisions.askedBy', { name: decision.requester_name ?? '' })}
        </span>
        <Tag variant={STATUS_VARIANT[decision.status]} data-testid="blackboard-decision-status" data-variant={decision.status}>
          {t(`blackboard.decisions.status.${decision.status}`)}
        </Tag>
      </header>
      <p className="bb-decision__question" data-testid="blackboard-decision-question">
        {decision.question}
      </p>
      {decision.doc_id ? (
        <button type="button" className="bb-decision__passage" data-testid="blackboard-decision-passage" onClick={() => actions.openDoc(decision.doc_id!)}>
          <FileText size={13} aria-hidden="true" />
          <span>{docTitle ?? decision.doc_id}</span>
          {decision.quote ? <q>{decision.quote}</q> : null}
          {decision.passage_changed ? <em className="bb-decision__changed">{t('blackboard.decisions.changed')}</em> : null}
        </button>
      ) : null}
      <ul className="bb-decision__options" role={canAnswer ? 'radiogroup' : undefined}>
        {decision.options.map((o, i) => {
          const chosen = decision.answer?.option === i;
          return (
            <li key={i} className={chosen ? 'is-chosen' : ''} data-testid="blackboard-decision-option" data-variant={o.label}>
              {canAnswer ? (
                <label>
                  <input
                    type="radio"
                    name={`decision-${decision.id}`}
                    checked={option === i}
                    onChange={() => {
                      setOption(i);
                      setText('');
                    }}
                  />
                  <span className="bb-decision__label">{o.label}</span>
                </label>
              ) : (
                <span className="bb-decision__label">{o.label}</span>
              )}
              {decision.recommended === i ? (
                <Tag variant="info" data-testid="blackboard-decision-recommended">
                  {t('blackboard.decisions.recommended')}
                </Tag>
              ) : null}
              {o.description ? <span className="bb-muted bb-decision__description">{o.description}</span> : null}
            </li>
          );
        })}
      </ul>
      {decision.status === 'proposed' ? (
        <p className="bb-decision__proposal" data-testid="blackboard-decision-proposal">
          {t('blackboard.decisions.proposed', { name: decision.answered_by_name ?? '', answer: decision.answer_label })}
        </p>
      ) : null}
      {decision.status === 'answered' ? (
        <p className="bb-decision__proposal" data-testid="blackboard-decision-answer">
          {decision.accepted_by && decision.accepted_by !== decision.answered_by
            ? t('blackboard.decisions.answeredAccepted', {
                answer: decision.answer_label,
                name: decision.answered_by_name ?? '',
                accepted: decision.accepted_by_name ?? '',
              })
            : t('blackboard.decisions.answered', { answer: decision.answer_label, name: decision.answered_by_name ?? '' })}
        </p>
      ) : null}
      {canAnswer ? (
        <input
          className="bb-decision__text"
          value={text}
          maxLength={2000}
          placeholder={t('blackboard.decisions.freeText')}
          data-testid="blackboard-decision-text"
          onChange={(event) => {
            setText(event.target.value);
            if (event.target.value) setOption(null);
          }}
        />
      ) : null}
      {canAnswer || canCancel ? (
        <div className="bb-decision__actions">
          {canAnswer ? (
            <Button
              size="sm"
              variant="primary"
              icon={<Send size={13} />}
              loading={busy}
              disabled={option === null && !text.trim()}
              data-testid="blackboard-decision-answer-btn"
              onClick={() => void answer()}
            >
              {requester ? t('blackboard.decisions.answer') : t('blackboard.decisions.propose')}
            </Button>
          ) : null}
          {decision.status === 'proposed' && requester ? (
            <Button
              size="sm"
              icon={<Check size={13} />}
              loading={busy}
              data-testid="blackboard-decision-accept-btn"
              onClick={() => void run(() => actions.accept(decision.id))}
            >
              {t('blackboard.decisions.accept')}
            </Button>
          ) : null}
          {canCancel ? (
            <Button
              size="sm"
              variant="quiet"
              icon={<X size={13} />}
              data-testid="blackboard-decision-cancel-btn"
              onClick={() => void run(() => actions.cancel(decision.id))}
            >
              {t('blackboard.decisions.cancel')}
            </Button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export function DecisionsPanel({
  decisions,
  meId,
  docTitles,
  actions,
}: {
  decisions: DecisionView[];
  meId: string | null;
  docTitles: ReadonlyMap<string, string>;
  actions: DecisionActions;
}) {
  const { t } = useTranslation();
  const ordered = [...decisions].sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.created_at.localeCompare(a.created_at));
  return (
    <div className="bb-rail__panel bb-decisions" data-testid="blackboard-decisions-panel">
      <p className="bb-muted">{t('blackboard.decisions.intro')}</p>
      {ordered.length === 0 ? (
        <p className="bb-muted" data-testid="blackboard-decisions-empty">
          {t('blackboard.decisions.empty')}
        </p>
      ) : null}
      {ordered.map((d) => (
        <DecisionCard key={d.id} decision={d} meId={meId} docTitle={d.doc_id ? (docTitles.get(d.doc_id) ?? null) : null} actions={actions} />
      ))}
    </div>
  );
}
