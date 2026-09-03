import { useId } from 'react';
import { AlertCircle, LoaderCircle, Mic, Square, Volume2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { LiveVoiceTaskActivity } from '../../features/live-voice/taskPresentationView';
import type { FormalP3TaskExperienceSnapshot } from '../../features/live-voice/formal/formalP3TaskExperience';
import {
  productTextProgressPresentationBinding,
  type ProductTextProgressEvent,
} from '../../features/live-voice/formal/productTextProgress';
import { productTaskProgressTranslationKey } from './productTaskProgressPresentation';
import type { ProductLiveVoiceSurfaceState } from './LiveVoiceIntegratedRoutePanel';
import './LiveVoiceDemoBar.css';

export type { LiveVoiceTaskActivity } from '../../features/live-voice/taskPresentationView';

export type LiveVoiceVisualState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'interrupted' | 'recovering' | 'error';

export function formalProductVoiceActivity(state: Readonly<ProductLiveVoiceSurfaceState> | null): {
  status: LiveVoiceVisualState; label_key: string;
} {
  let status: LiveVoiceVisualState = 'idle';
  const diagnostic = state?.recovery_diagnostic;
  const processing = state?.text_status === 'submitting' || state?.text_status === 'waiting';
  const preparingAudio = state?.text_status === 'presented' && state?.p1_status === 'recognized';
  if (diagnostic) status = diagnostic.disposition === 'retrying' ? 'recovering' : 'error';
  else if (state?.text_status === 'failed') status = 'error';
  else if (state?.p1_status === 'playing') status = 'speaking';
  else if (processing) status = 'thinking';
  else if (preparingAudio) status = 'thinking';
  else if (state?.p1_status === 'capturing') status = 'listening';
  else if (state?.p1_status === 'starting' || state?.p1_status === 'cleanup_pending') status = 'recovering';
  else if (state?.p1_status === 'recognizing') status = 'thinking';
  else if (state?.p1_status === 'failed') status = 'error';
  else if (state?.terminal_announcement_state === 'recovering') status = 'recovering';
  else if (state?.terminal_announcement_state && state.terminal_announcement_state !== 'idle') status = 'thinking';
  return { status, label_key: status === 'thinking' && preparingAudio ? 'liveVoice.formal.preparingAudio'
    : status === 'thinking' && processing && state?.p1_status === 'capturing'
    ? 'liveVoice.formal.processingListening' : `liveVoice.status.${status}` };
}

export type LiveVoiceCommandRoute = 'agent' | 'task';
export type LiveVoiceTaskOperation = 'task.create' | 'task.status' | 'task.cancel';

export interface LiveVoiceCommandCenterProps {
  route: LiveVoiceCommandRoute;
  taskAvailable: boolean;
  taskOperation: LiveVoiceTaskOperation;
  taskId: string;
  taskStatus: string;
  taskReason?: string | null;
  taskResult?: string | null;
  taskConfirmationForm?: string | null;
  taskProgressTaskId?: string | null;
  taskProgressState?: string | null;
  taskProgressDeliveryMode?: string | null;
  controlsDisabled?: boolean;
  taskControlsLocked?: boolean;
  onRouteChange: (route: LiveVoiceCommandRoute) => void;
  onTaskOperationChange: (operation: LiveVoiceTaskOperation) => void;
  onTaskIdChange: (taskId: string) => void;
  onCancelTaskConfirmation: () => void;
}

export interface LiveVoiceDemoBarProps {
  launchPending?: boolean;
  launchError?: string;
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
  taskProgressPresentation?: Readonly<{
    event: Readonly<ProductTextProgressEvent>;
    nodeRef: (node: HTMLDivElement | null) => void;
  }> | null;
  statusLabel?: string;
  primaryActionLabel?: string;
  primaryActionDisabled?: boolean;
  editableTranscript?: string;
  onTranscriptChange?: (value: string) => void;
  commandCenter?: LiveVoiceCommandCenterProps;
  handsFree?: boolean;
  onEnable: () => void;
  onExit: () => void;
  onPrimaryAction: () => void;
  onRetryListening?: () => void;
  /** Optional bounded controls for the formal hands-free playout state. */
  onInterruptAndSpeak?: () => void;
  onStopPlayback?: () => void;
}

export type FormalProductTaskPresentationState = Readonly<{
  terminal_notification: string | null;
  adjustment_notification: string | null;
  task_progress_state: string | null;
  task_progress_event: Readonly<ProductTextProgressEvent> | null;
  task_progress_node_ref: (node: HTMLDivElement | null) => void;
  task_unread_delivery: Readonly<{
    task_id: string;
    attempt_id: string;
    event_id: string;
    event_seq: number;
    acknowledgement: 'idle' | 'pending' | 'acknowledged' | 'failed';
  }> | null;
  task_experience: FormalP3TaskExperienceSnapshot;
}>;

export interface FormalProductLiveVoiceDemoBarProps extends Omit<LiveVoiceDemoBarProps, 'taskActivity'> {
  surfaceState: FormalProductTaskPresentationState | null;
}

function VoiceStatusIcon({ status }: { status: LiveVoiceVisualState }) {
  switch (status) {
    case 'thinking':
    case 'recovering':
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

function TaskActivityPanel({
  taskSafetyDisclosure,
  taskActivity,
  taskProgressPresentation,
}: {
  taskSafetyDisclosure?: string;
  taskActivity: LiveVoiceTaskActivity | null;
  taskProgressPresentation?: LiveVoiceDemoBarProps['taskProgressPresentation'];
}) {
  const { t } = useTranslation();
  if (!taskSafetyDisclosure && !taskActivity) return null;
  const progress = taskProgressPresentation?.event ?? null;
  return (
    <div
      ref={taskProgressPresentation?.nodeRef}
      className="live-voice-demo__task"
      data-level={taskActivity?.level ?? 'warning'}
      role={taskActivity?.level === 'error' ? 'alert' : 'status'}
      aria-live={taskActivity?.level === 'error' ? 'assertive' : 'polite'}
      aria-atomic="true"
      data-testid={progress ? 'live-voice-product-task-notification' : undefined}
      data-delivery-id={progress?.delivery_id}
      data-presentation-binding={progress?.consumption_mode === 'presentation' ? productTextProgressPresentationBinding(progress) : undefined}
      data-session-id={progress?.session_id}
      data-subject-id={progress?.source_event.scope.subject_id}
      data-project-id={progress?.project_id}
      data-task-id={progress?.task_id}
      data-attempt-id={progress?.attempt_id}
      data-event-id={progress?.source_event.event_id}
      data-event-seq={progress ? String(progress.source_event.seq) : undefined}
      data-generation-id={progress?.generation_id}
      data-generation={progress ? String(progress.generation) : undefined}
      data-presentation-class={progress?.presentation_class ?? undefined}
      data-response-interaction-id={progress?.response_ref?.interaction_id}
      data-response-id={progress?.response_ref?.response_id}
      data-response-generation={progress?.response_ref ? String(progress.response_ref.response_generation) : undefined}
      data-unit-id={progress?.unit_id ?? undefined}
      data-expected-event-head={progress?.expected_event_head == null ? undefined : String(progress.expected_event_head)}
      data-result-source-event-id={progress?.consumption_mode === 'presentation' ? progress.result_source_event_id ?? '' : undefined}
    >
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
              {taskActivity.record.monitorState && (
                <>
                  <span className="live-voice-demo__task-fact">
                    {t('liveVoice.task.monitorState')}: <code>{taskActivity.record.monitorState}</code>
                  </span>
                  <span className="live-voice-demo__task-fact">
                    {t('liveVoice.task.progress')}: <code>{taskActivity.record.progressSummary ?? t('liveVoice.task.unknown')}</code>
                  </span>
                  <span className="live-voice-demo__task-fact">
                    {t('liveVoice.task.lastError')}: <code>{taskActivity.record.lastError ?? t('liveVoice.task.unknown')}</code>
                  </span>
                </>
              )}
              <span className="live-voice-demo__task-fact">
                {t('liveVoice.task.source')}: <code>{taskActivity.record.source}</code>
              </span>
              <span className="live-voice-demo__task-fact">
                {t('liveVoice.task.resultSource')}: <code>{taskActivity.record.resultSource}</code>
              </span>
              <span className="live-voice-demo__task-fact">
                {t('liveVoice.task.recoveryStatus')}: <code>{taskActivity.record.recoveryStatus}</code>
              </span>
              <span className="live-voice-demo__task-fact" title={taskActivity.record.executionTarget.projectDir ?? t('liveVoice.task.unknown')}>
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
  );
}

function CommandCenter({ commandCenter }: { commandCenter: LiveVoiceCommandCenterProps }) {
  const { t } = useTranslation();
  const taskMode = commandCenter.route === 'task';
  const taskTargetRequired = commandCenter.taskOperation !== 'task.create';
  const routeDisabled = commandCenter.controlsDisabled || commandCenter.taskControlsLocked;
  const taskControlsDisabled = commandCenter.controlsDisabled || commandCenter.taskControlsLocked;
  return (
    <div className="live-voice-demo__command-center" data-testid="live-voice-command-center">
      <div className="live-voice-demo__route-switch" role="group" aria-label={t('liveVoice.commandCenter.routeLabel')}>
        <button
          type="button"
          className={commandCenter.route === 'agent' ? 'is-active' : undefined}
          aria-pressed={commandCenter.route === 'agent'}
          disabled={routeDisabled}
          onClick={() => commandCenter.onRouteChange('agent')}
        >
          {t('liveVoice.commandCenter.agent')}
        </button>
        <button
          type="button"
          className={taskMode ? 'is-active' : undefined}
          aria-pressed={taskMode}
          disabled={routeDisabled || !commandCenter.taskAvailable}
          onClick={() => commandCenter.onRouteChange('task')}
        >
          {t('liveVoice.commandCenter.task')}
        </button>
      </div>
      <span className="live-voice-demo__route-summary">
        {taskMode ? t('liveVoice.commandCenter.taskRouteSummary') : t('liveVoice.commandCenter.agentRouteSummary')}
      </span>
      {taskMode && (
        <div className="live-voice-demo__task-command" data-testid="live-voice-task-command">
          <label>
            <span>{t('liveVoice.commandCenter.operation')}</span>
            <select
              aria-label={t('liveVoice.commandCenter.operation')}
              value={commandCenter.taskOperation}
              disabled={taskControlsDisabled}
              onChange={event => commandCenter.onTaskOperationChange(event.target.value as LiveVoiceTaskOperation)}
            >
              <option value="task.create">{t('liveVoice.commandCenter.create')}</option>
              <option value="task.status">{t('liveVoice.commandCenter.status')}</option>
              <option value="task.cancel">{t('liveVoice.commandCenter.cancel')}</option>
            </select>
          </label>
          {taskTargetRequired && (
            <label className="live-voice-demo__task-id">
              <span>{t('liveVoice.commandCenter.taskId')}</span>
              <input
                aria-label={t('liveVoice.commandCenter.taskId')}
                value={commandCenter.taskId}
                disabled={taskControlsDisabled}
                placeholder="task-abc_123"
                maxLength={128}
                onChange={event => commandCenter.onTaskIdChange(event.target.value)}
              />
            </label>
          )}
          <span className="live-voice-demo__task-command-status">
            {t('liveVoice.commandCenter.routeStatus')}: <code>{commandCenter.taskStatus}</code>
          </span>
          {commandCenter.taskResult && <span className="live-voice-demo__task-command-result">{commandCenter.taskResult}</span>}
          {commandCenter.taskReason && <span className="live-voice-demo__task-command-error">{commandCenter.taskReason}</span>}
          {commandCenter.taskProgressTaskId && (
            <span className="live-voice-demo__task-command-progress" data-testid="live-voice-command-progress">
              {t('liveVoice.commandCenter.progress')}: <code>{commandCenter.taskProgressTaskId}</code>
              {commandCenter.taskProgressState ? ` · ${commandCenter.taskProgressState}` : ''}
              {commandCenter.taskProgressDeliveryMode ? ` · ${commandCenter.taskProgressDeliveryMode}` : ''}
            </span>
          )}
        </div>
      )}
      {taskMode && commandCenter.taskConfirmationForm && (
        <div className="live-voice-demo__task-confirmation" data-testid="live-voice-command-task-confirmation" role="note">
          <span>{t('liveVoice.commandCenter.confirmationPrompt')}</span>
          <code>{commandCenter.taskConfirmationForm}</code>
          <button type="button" disabled={commandCenter.controlsDisabled} onClick={commandCenter.onCancelTaskConfirmation}>
            {t('liveVoice.commandCenter.abandon')}
          </button>
        </div>
      )}
    </div>
  );
}

export function LiveVoiceDemoBar({
  active,
  launchPending = false,
  launchError = '',
  available,
  status,
  interimTranscript,
  committedTranscript = '',
  errorMessage = '',
  unavailableMessage,
  routeLabel,
  taskSafetyDisclosure,
  taskActivity = null,
  taskProgressPresentation = null,
  statusLabel: statusLabelOverride,
  primaryActionLabel: primaryActionLabelOverride,
  primaryActionDisabled = false,
  editableTranscript,
  onTranscriptChange,
  commandCenter,
  handsFree = false,
  onEnable,
  onExit,
  onPrimaryAction,
  onRetryListening,
  onInterruptAndSpeak,
  onStopPlayback,
}: LiveVoiceDemoBarProps) {
  const { t } = useTranslation();
  const unavailableHintId = useId();
  const resolvedUnavailableMessage = unavailableMessage || t('liveVoice.unavailable');

  if (!active) {
    return (
      <div className={`live-voice-demo live-voice-demo--inactive${taskActivity ? ' live-voice-demo--with-task' : ''}`} data-testid="live-voice-demo">
        <div className="live-voice-demo__inactive-actions">
          <span className="live-voice-demo__launch-wrap" title={!available && !launchPending && !launchError ? resolvedUnavailableMessage : undefined}>
            <button
              type="button"
              className="live-voice-demo__launch"
              disabled={!available}
              aria-label={t('liveVoice.enable')}
              aria-describedby={!available && !launchPending && !launchError ? unavailableHintId : undefined}
              aria-pressed={false}
              onClick={onEnable}
            >
              <Mic size={17} strokeWidth={2} aria-hidden="true" />
              <span>{t(launchPending ? 'liveVoice.startingSession' : 'liveVoice.label')}</span>
              <span className="live-voice-demo__experimental">{t('liveVoice.experimental')}</span>
            </button>
          </span>
          {launchPending && (
            <button type="button" className="live-voice-demo__exit" onClick={onExit} aria-label={t('liveVoice.exit')}>
              {t('liveVoice.exit')}
            </button>
          )}
        </div>
        {launchError && (
          <div role="alert" className="live-voice-demo__error">
            {launchError}
          </div>
        )}
        {taskActivity && (
          <TaskActivityPanel taskSafetyDisclosure={taskSafetyDisclosure} taskActivity={taskActivity} taskProgressPresentation={taskProgressPresentation} />
        )}
        {!available && !launchPending && !launchError && (
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
  const transcript = interim || committed || t('liveVoice.transcriptPlaceholder');
  const transcriptKind = interim ? 'interim' : committed ? 'committed' : 'placeholder';
  const statusLabel = statusLabelOverride || t(`liveVoice.status.${status}`);
  const primaryActionLabel = primaryActionLabelOverride || t(`liveVoice.actions.${status}`);
  const hasTaskPanel = Boolean(taskSafetyDisclosure || taskActivity);
  const hasEditableTranscript = !handsFree && editableTranscript !== undefined && onTranscriptChange !== undefined;
  const hasCommandCenter = !handsFree && commandCenter !== undefined;

  return (
    <section
      className={`live-voice-demo live-voice-demo--active live-voice-demo--${status}${hasTaskPanel ? ' live-voice-demo--with-task' : ''}${hasCommandCenter ? ' live-voice-demo--with-command-center' : ''}`}
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

        {hasCommandCenter && commandCenter && <CommandCenter commandCenter={commandCenter} />}

        {hasEditableTranscript ? (
          <textarea
            className="live-voice-demo__transcript live-voice-demo__transcript--editor"
            aria-label={t('liveVoice.formal.editorLabel')}
            value={editableTranscript}
            disabled={primaryActionDisabled}
            maxLength={100000}
            onChange={event => onTranscriptChange(event.target.value)}
          />
        ) : (
          <div
            className={`live-voice-demo__transcript live-voice-demo__transcript--${transcriptKind}`}
            aria-live="off"
            title={transcript}
          >
            {transcript}
          </div>
        )}

        {visibleError && (
          <div className="live-voice-demo__error" role="alert" aria-live="assertive">
            <AlertCircle size={15} strokeWidth={2} aria-hidden="true" />
            <span>{visibleError}</span>
          </div>
        )}

        <TaskActivityPanel
          taskSafetyDisclosure={taskSafetyDisclosure}
          taskActivity={taskActivity}
          taskProgressPresentation={taskProgressPresentation}
        />

        <div className="live-voice-demo__actions">
          {!handsFree && (
            <button
              type="button"
              className="live-voice-demo__primary"
              disabled={!available || primaryActionDisabled}
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
          )}
          {handsFree && visibleError && onRetryListening && (
            <button type="button" className="live-voice-demo__primary" onClick={onRetryListening}>
              <Mic size={17} strokeWidth={2} aria-hidden="true" />
              <span className="live-voice-demo__primary-label">{t('liveVoice.retryListening')}</span>
            </button>
          )}
          {handsFree && status === 'speaking' && onInterruptAndSpeak && (
            <button
              type="button"
              className="live-voice-demo__primary"
              disabled={!available}
              aria-label={t('liveVoice.actions.speaking')}
              onClick={onInterruptAndSpeak}
            >
              <Mic size={17} strokeWidth={2} aria-hidden="true" />
              <span className="live-voice-demo__primary-label">{t('liveVoice.actions.speaking')}</span>
            </button>
          )}
          {handsFree && status === 'speaking' && onStopPlayback && (
            <button
              type="button"
              className="live-voice-demo__stop"
              disabled={!available}
              aria-label={t('liveVoice.formal.actions.stopPlayback')}
              title={t('liveVoice.formal.actions.stopPlayback')}
              onClick={onStopPlayback}
            >
              <Square size={15} strokeWidth={2} aria-hidden="true" />
              <span className="live-voice-demo__stop-label">{t('liveVoice.formal.actions.stopPlayback')}</span>
            </button>
          )}
          <button type="button" className="live-voice-demo__exit" aria-label={t('liveVoice.exit')} title={t('liveVoice.exit')} onClick={onExit}>
            <X size={17} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </div>
    </section>
  );
}

/** Production adapter from the formal product surface truth to the shared voice bar. */
export function FormalProductLiveVoiceDemoBar({ surfaceState, ...props }: FormalProductLiveVoiceDemoBarProps) {
  const { t } = useTranslation();
  const progressEvent = surfaceState?.task_progress_event ?? null;
  const progressOutcome = progressEvent && typeof progressEvent.source_event.payload.outcome === 'string'
    ? progressEvent.source_event.payload.outcome
    : null;
  const progressDetail = progressEvent?.state === 'terminal'
    ? progressOutcome === 'completed'
      ? t('liveVoice.formal.taskTerminalCompleted')
      : progressOutcome === 'cancelled'
        ? t('liveVoice.formal.taskTerminalCancelled')
        : t('liveVoice.formal.taskTerminalFailed', { outcome: progressOutcome ?? 'unknown' })
    : surfaceState?.task_progress_state
      ? t(productTaskProgressTranslationKey(surfaceState.task_progress_state), { state: surfaceState.task_progress_state })
      : null;
  const taskDetail = progressEvent?.state === 'terminal'
    ? progressDetail
    : surfaceState?.terminal_notification ??
      surfaceState?.adjustment_notification ??
      progressDetail;
  const taskActivity: LiveVoiceDemoBarProps['taskActivity'] = taskDetail
    ? {
        level: progressEvent?.state === 'terminal' && progressOutcome !== 'completed'
          ? progressOutcome === 'cancelled' ? 'warning' : 'error'
          : props.status === 'error' ? 'error' : 'info',
        title: t('liveVoice.formal.taskTitle'),
        detail: taskDetail,
      }
    : null;
  const taskProgressPresentation = progressEvent && surfaceState
    ? Object.freeze({ event: progressEvent, nodeRef: surfaceState.task_progress_node_ref })
    : null;
  return <LiveVoiceDemoBar {...props} taskActivity={taskActivity} taskProgressPresentation={taskProgressPresentation} />;
}
