import { useId } from 'react';
import { AlertCircle, LoaderCircle, Mic, Square, Volume2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { LiveVoiceTaskActivity } from '../../features/live-voice/liveVoiceTaskAdapter';
import './LiveVoiceDemoBar.css';

export type { LiveVoiceTaskActivity } from '../../features/live-voice/liveVoiceTaskAdapter';

export type LiveVoiceVisualState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'error';

export interface LiveVoiceDemoBarProps {
  active: boolean;
  available: boolean;
  status: LiveVoiceVisualState;
  interimTranscript: string;
  committedTranscript?: string;
  errorMessage?: string;
  unavailableMessage?: string;
  routeLabel?: string;
  /** Always-visible warning shown before any task command can dispatch. */
  taskSafetyDisclosure?: string;
  taskActivity?: LiveVoiceTaskActivity | null;
  onEnable: () => void;
  onExit: () => void;
  onPrimaryAction: () => void;
}

function VoiceStatusIcon({ status }: { status: LiveVoiceVisualState }) {
  switch (status) {
    case 'thinking':
      return <LoaderCircle className="live-voice-demo__status-spinner" size={16} strokeWidth={2} />;
    case 'speaking':
      return <Volume2 size={16} strokeWidth={2} />;
    case 'error':
      return <AlertCircle size={16} strokeWidth={2} />;
    default:
      return <Mic size={16} strokeWidth={2} />;
  }
}

function PrimaryActionIcon({ status }: { status: LiveVoiceVisualState }) {
  if (status === 'listening') {
    return <Square size={15} strokeWidth={2} fill="currentColor" />;
  }
  return <Mic size={17} strokeWidth={2} />;
}

export function LiveVoiceDemoBar({
  active,
  available,
  status,
  interimTranscript,
  committedTranscript = '',
  errorMessage = '',
  unavailableMessage,
  routeLabel,
  taskSafetyDisclosure,
  taskActivity = null,
  onEnable,
  onExit,
  onPrimaryAction,
}: LiveVoiceDemoBarProps) {
  const { t } = useTranslation();
  const unavailableHintId = useId();
  const resolvedUnavailableMessage = unavailableMessage || t('liveVoice.unavailable');

  if (!active) {
    return (
      <div className="live-voice-demo live-voice-demo--inactive" data-testid="live-voice-demo">
        <span className="live-voice-demo__launch-wrap" title={!available ? resolvedUnavailableMessage : undefined}>
          <button
            type="button"
            className="live-voice-demo__launch"
            disabled={!available}
            aria-label={t('liveVoice.enable')}
            aria-describedby={!available ? unavailableHintId : undefined}
            aria-pressed={false}
            onClick={onEnable}
          >
            <Mic size={17} strokeWidth={2} aria-hidden="true" />
            <span>{t('liveVoice.label')}</span>
            <span className="live-voice-demo__experimental">{t('liveVoice.experimental')}</span>
          </button>
        </span>
        {!available && (
          <span id={unavailableHintId} className="live-voice-demo__sr-only">
            {resolvedUnavailableMessage}
          </span>
        )}
      </div>
    );
  }

  const interim = interimTranscript.trim();
  const committed = committedTranscript.trim();
  const visibleError = errorMessage.trim() || (!available ? resolvedUnavailableMessage : '');
  const transcript = interim || committed || visibleError || t('liveVoice.transcriptPlaceholder');
  const transcriptKind = visibleError ? 'error' : interim ? 'interim' : committed ? 'committed' : 'placeholder';
  const statusLabel = t(`liveVoice.status.${status}`);
  const primaryActionLabel = t(`liveVoice.actions.${status}`);
  const hasTaskPanel = Boolean(taskSafetyDisclosure || taskActivity);

  return (
    <section
      className={`live-voice-demo live-voice-demo--active live-voice-demo--${status}${hasTaskPanel ? ' live-voice-demo--with-task' : ''}`}
      aria-label={t('liveVoice.label')}
      data-state={status}
      data-testid="live-voice-demo"
    >
      <div className="live-voice-demo__panel">
        <div className="live-voice-demo__meta">
          <span className="live-voice-demo__status-icon" aria-hidden="true">
            <VoiceStatusIcon status={status} />
          </span>
          <span className="live-voice-demo__product-label">{t('liveVoice.label')}</span>
          <span className="live-voice-demo__status-label" role="status" aria-live="polite" aria-atomic="true">
            {statusLabel}
          </span>
          <span className="live-voice-demo__experimental">{t('liveVoice.experimental')}</span>
          {routeLabel && (
            <span className="live-voice-demo__experimental" data-testid="live-voice-route-label">
              {routeLabel}
            </span>
          )}
        </div>

        <div
          className={`live-voice-demo__transcript live-voice-demo__transcript--${transcriptKind}`}
          aria-live={visibleError ? undefined : 'off'}
          role={visibleError ? 'alert' : undefined}
          title={transcript}
        >
          {transcript}
        </div>

        {(taskSafetyDisclosure || taskActivity) && (
          <div className="live-voice-demo__task" data-level={taskActivity?.level ?? 'warning'} role={taskActivity?.level === 'error' ? 'alert' : 'status'}>
            {taskSafetyDisclosure && (
              <span className="live-voice-demo__task-safety" role="note">
                <strong>{t('liveVoice.task.safetyTitle')}</strong>
                {taskSafetyDisclosure}
              </span>
            )}
            {taskActivity && (
              <>
                <span className="live-voice-demo__task-title">{taskActivity.title}</span>
                <span className="live-voice-demo__task-detail">{taskActivity.detail}</span>
                {taskActivity.commandId && (
                  <span className="live-voice-demo__task-fact">
                    {t('liveVoice.task.commandId')}: <code>{taskActivity.commandId}</code>
                  </span>
                )}
                {taskActivity.predecessorTaskId && (
                  <span className="live-voice-demo__task-fact">
                    {t('liveVoice.task.predecessorTaskId')}: <code>{taskActivity.predecessorTaskId}</code>
                  </span>
                )}
                {taskActivity.successorTaskId && (
                  <span className="live-voice-demo__task-fact">
                    {t('liveVoice.task.successorTaskId')}: <code>{taskActivity.successorTaskId}</code>
                  </span>
                )}
                {taskActivity.conflictingTaskId && (
                  <span className="live-voice-demo__task-fact">
                    {t('liveVoice.task.conflictingTaskId')}: <code>{taskActivity.conflictingTaskId}</code>
                  </span>
                )}
                {taskActivity.record && (
                  <>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.recordRole')}: <code>{t(`liveVoice.task.roles.${taskActivity.record.role}`)}</code>
                    </span>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.taskId')}: <code>{taskActivity.record.taskId}</code>
                    </span>
                    {taskActivity.record.commandId && taskActivity.record.commandId !== taskActivity.commandId && (
                      <span className="live-voice-demo__task-fact">
                        {t('liveVoice.task.taskCommandId')}: <code>{taskActivity.record.commandId}</code>
                      </span>
                    )}
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.status')}: <code>{taskActivity.record.status}</code>
                    </span>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.source')}: <code>{taskActivity.record.source}</code>
                    </span>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.resultSource')}: <code>{taskActivity.record.resultSource}</code>
                    </span>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.recoveryStatus')}: <code>{taskActivity.record.recoveryStatus}</code>
                    </span>
                    <span
                      className="live-voice-demo__task-fact"
                      title={taskActivity.record.executionTarget.projectDir ?? t('liveVoice.task.unknown')}
                    >
                      {t('liveVoice.task.projectDir')}: <code>{taskActivity.record.executionTarget.projectDir ?? t('liveVoice.task.unknown')}</code>
                    </span>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.projectId')}: <code>{taskActivity.record.executionTarget.projectId ?? t('liveVoice.task.unknown')}</code>
                    </span>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.originSessionId')}: <code>{taskActivity.record.executionTarget.originSessionId ?? t('liveVoice.task.unknown')}</code>
                    </span>
                    <span className="live-voice-demo__task-fact">
                      {t('liveVoice.task.originChannelId')}: <code>{taskActivity.record.executionTarget.originChannelId ?? t('liveVoice.task.unknown')}</code>
                    </span>
                  </>
                )}
                {taskActivity.disclosure && <span className="live-voice-demo__task-disclosure">{taskActivity.disclosure}</span>}
              </>
            )}
          </div>
        )}

        <div className="live-voice-demo__actions">
          <button
            type="button"
            className="live-voice-demo__primary"
            disabled={!available}
            aria-label={primaryActionLabel}
            aria-pressed={status === 'listening'}
            title={!available ? resolvedUnavailableMessage : primaryActionLabel}
            onClick={onPrimaryAction}
          >
            <span aria-hidden="true">
              <PrimaryActionIcon status={status} />
            </span>
            <span className="live-voice-demo__primary-label">{primaryActionLabel}</span>
          </button>
          <button type="button" className="live-voice-demo__exit" aria-label={t('liveVoice.exit')} title={t('liveVoice.exit')} onClick={onExit}>
            <X size={17} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </div>
    </section>
  );
}
