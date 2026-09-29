// What the chat, the comments and the Agents tab share: a task's status tag and the host's notices.
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';

import { Tag, type TagVariant } from '../../../../channels/web/frontend/src/components/ui';
import { coded } from '../conversation';
import type { MandateStatus, MandateView } from '../types';

export const STATUS_VARIANT: Record<MandateStatus, TagVariant> = {
  queued: 'neutral',
  running: 'info',
  waiting_for_answer: 'warning',
  done: 'success',
  failed: 'danger',
  cancelled: 'neutral',
  refused: 'danger',
  unknown: 'warning',
};

export const ACTIVE: MandateStatus[] = ['queued', 'running', 'waiting_for_answer'];

// The status of the task a message or comment gave the agent.
export function TaskTag({ mandate, status }: { mandate?: MandateView; status?: MandateStatus | null }) {
  const { t } = useTranslation();
  const current = mandate?.status ?? status;
  if (!current) return null;
  const position = mandate?.status === 'queued' ? mandate.queue_position : null;
  return (
    <Tag variant={STATUS_VARIANT[current]} data-testid="blackboard-task-status" data-variant={current}>
      {position ? t('blackboard.agents.queuedAt', { position }) : t(`blackboard.agents.status.${current}`)}
    </Tag>
  );
}

const REASONS = ['not_picked_up', 'no_result', 'not_an_editor', 'timeout', 'already_handled'];

function reasonText(t: TFunction, reason: string): string {
  return REASONS.includes(reason) ? t(`blackboard.notices.reason.${reason}`) : reason;
}

// A notice or summary the host wrote, in this browser's language; `name` is the person it is about.
export function noticeText(t: TFunction, body: string, name: string): string {
  const notice = coded(body);
  if (!notice) return body;
  const { code, params } = notice;
  const values = {
    name,
    doc: params.doc_title || '',
    reason: params.reason ? reasonText(t, params.reason) : '',
    by: params.by || '',
    answeredBy: params.answered_by || '',
    answer: params.answer || '',
    excerpt: params.excerpt || '',
  };
  if (code === 'agent_cancelled' && !values.by) return t('blackboard.notices.agent_stopped', values);
  if (code === 'agent_failed' && !values.reason) return t('blackboard.notices.agent_failed_plain', values);
  return t(`blackboard.notices.${code}`, { ...values, defaultValue: body });
}
