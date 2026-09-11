import { Activity, RefreshCw, ShieldAlert } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN, type BrowserAudioDeviceSelectionSnapshot } from '../../features/live-voice/formal/browserAudioDeviceSelection';
import { type IntegratedWebRouteManifest } from '../../features/live-voice/formal/integratedWebRouteShell';
import {
  PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON,
  PRODUCT_P1_CAPTURE_MAX_DURATION_MS,
  type ProductP1VoiceStatus,
} from '../../features/live-voice/formal/productP1VoiceRoute';
import { productTextProgressPresentationBinding, type ProductTextProgressEvent } from '../../features/live-voice/formal/productTextProgress';
import { type ProductWebP2ActivationSnapshot, type ProductWebP3ProgressSnapshot } from '../../features/live-voice/formal/productWebActivation';
import { type WebPlatformDiagnosticsSnapshot } from '../../features/live-voice/formal/webPlatformDiagnostics';
import { type ProductP3MutationStatus } from './liveVoiceProductOperations';


function DiagnosticsFact({ label, value }: { label: string; value: string }) {
  return (
    <span className="live-voice-integrated__fact">
      <span>{label}</span>
      <code>{value}</code>
    </span>
  );
}


export interface LiveVoiceIntegratedRoutePanelViewProps {
  manifest: Readonly<IntegratedWebRouteManifest>;
  platform: Readonly<WebPlatformDiagnosticsSnapshot> | null;
  progress?: Readonly<ProductTextProgressEvent> | null;
  progressAck?: 'idle' | 'pending' | 'acknowledged' | 'failed';
  p2Activation?: Readonly<ProductWebP2ActivationSnapshot> | null;
  p3Activation?: Readonly<ProductWebP3ProgressSnapshot> | null;
  productInput?: string;
  productOutput?: string | null;
  productTextStatus?: 'idle' | 'submitting' | 'waiting' | 'presented' | 'acknowledged' | 'failed';
  p1VoiceEnabled?: boolean;
  p1VoiceStatus?: ProductP1VoiceStatus;
  p1VoiceReason?: string | null;
  deviceSelection?: Readonly<BrowserAudioDeviceSelectionSnapshot> | null;
  draftInputDeviceToken?: string;
  draftOutputDeviceToken?: string;
  onLoadAudioDevices?: () => void;
  onDraftInputDevice?: (token: string) => void;
  onDraftOutputDevice?: (token: string) => void;
  onApplyAudioDevices?: () => void;
  onP1VoiceStart?: () => void;
  onP1VoiceStop?: () => void;
  productOperationRetained?: boolean;
  productTextTransportRetained?: boolean;
  onProductInput?: (value: string) => void;
  onProductSubmit?: () => void;
  recognizedSpeechConfirmation?: 'agent' | 'task' | null;
  recognizedSpeechDispatching?: boolean;
  onRecognizedSpeechConfirm?: () => void;
  onRecognizedSpeechCancel?: () => void;
  p3MutationEnabled?: boolean;
  p3MutationOperation?: 'task.create' | 'task.cancel' | 'task.retry';
  p3TaskName?: string;
  p3TaskInstruction?: string;
  p3TargetTaskId?: string;
  p3MutationStatus?: ProductP3MutationStatus;
  p3MutationReason?: string | null;
  p3MutationRetained?: boolean;
  p3RetryEligible?: boolean;
  p3RetryAttemptNumber?: number | null;
  p3RetryInspectionStatus?: 'idle' | 'checking' | 'eligible' | 'ineligible' | 'failed';
  p3RetryInspectionReason?: string | null;
  onP3MutationOperation?: (value: 'task.create' | 'task.cancel' | 'task.retry') => void;
  onP3TaskName?: (value: string) => void;
  onP3TaskInstruction?: (value: string) => void;
  onP3TargetTaskId?: (value: string) => void;
  onP3InspectRetry?: () => void;
  onP3Issue?: () => void;
  onP3Execute?: () => void;
  onRefresh: () => void;
}


export function LiveVoiceIntegratedRoutePanelView({
  manifest,
  platform,
  progress = null,
  progressAck = 'idle',
  p2Activation = null,
  p3Activation = null,
  productInput = '',
  productOutput = null,
  productTextStatus = 'idle',
  p1VoiceEnabled = false,
  p1VoiceStatus = 'closed',
  p1VoiceReason = null,
  deviceSelection = null,
  draftInputDeviceToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  draftOutputDeviceToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN,
  onLoadAudioDevices,
  onDraftInputDevice,
  onDraftOutputDevice,
  onApplyAudioDevices,
  onP1VoiceStart,
  onP1VoiceStop,
  productOperationRetained = false,
  productTextTransportRetained,
  onProductInput,
  onProductSubmit,
  recognizedSpeechConfirmation = null,
  recognizedSpeechDispatching = false,
  onRecognizedSpeechConfirm,
  onRecognizedSpeechCancel,
  p3MutationEnabled = false,
  p3MutationOperation = 'task.create',
  p3TaskName = '',
  p3TaskInstruction = '',
  p3TargetTaskId = '',
  p3MutationStatus = 'idle',
  p3MutationReason = null,
  p3MutationRetained = false,
  p3RetryEligible = false,
  p3RetryAttemptNumber = null,
  p3RetryInspectionStatus = 'idle',
  p3RetryInspectionReason = null,
  onP3MutationOperation,
  onP3TaskName,
  onP3TaskInstruction,
  onP3TargetTaskId,
  onP3InspectRetry,
  onP3Issue,
  onP3Execute,
  onRefresh,
}: LiveVoiceIntegratedRoutePanelViewProps) {
  const { t } = useTranslation();

  const compositionLabel = t(`liveVoice.integrated.composition.${manifest.composition_state}`);
  const browserEvidence = platform?.browser_version
    ? `${platform.browser_family} ${platform.browser_version}`
    : (platform?.browser_family ?? t('liveVoice.integrated.diagnostics.pending'));
  const structuredP3MutationLocked =
    productOperationRetained ||
    recognizedSpeechConfirmation !== null ||
    ['issuing', 'confirmed', 'mutating'].includes(p3MutationStatus) ||
    p3RetryInspectionStatus === 'checking' ||
    (p3MutationStatus === 'failed' && p3MutationRetained);
  const p3MutationLocked = structuredP3MutationLocked;
  const resolvedProductTextTransportRetained = productTextTransportRetained ?? (productOperationRetained && recognizedSpeechConfirmation === null);
  const productTextLocked =
    recognizedSpeechDispatching ||
    ['submitting', 'waiting', 'presented'].includes(productTextStatus) ||
    resolvedProductTextTransportRetained ||
    ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus);
  const deviceSelectionLocked =
    productOperationRetained ||
    ['loading', 'refreshing'].includes(deviceSelection?.status ?? '') ||
    ['starting', 'capturing', 'recognizing', 'playing', 'cleanup_pending'].includes(p1VoiceStatus);
  // Retain the established diagnostic harness behind the hidden/aria-hidden
  // owner surface so lifecycle regressions stay testable. The product bar is
  // the only visible Live Voice UI and never exposes these controls.
  const legacyManualControls = true;

  return (
    <details
      className="live-voice-integrated"
      data-composition={manifest.composition_state}
      data-testid="live-voice-integrated-route"
      aria-hidden="true"
      hidden
    >
      <summary className="live-voice-integrated__summary">
        <Activity size={16} strokeWidth={2} aria-hidden="true" />
        <span>{t('liveVoice.integrated.title')}</span>
        <code>{compositionLabel}</code>
      </summary>
      <div className="live-voice-integrated__body">
        <div className="live-voice-integrated__warning" role="note">
          <ShieldAlert size={16} strokeWidth={2} aria-hidden="true" />
          <span>{t('liveVoice.integrated.shellOnly')}</span>
        </div>

        <div className="live-voice-integrated__section" aria-label={t('liveVoice.integrated.routes')}>
          <strong>{t('liveVoice.integrated.routes')}</strong>
          <div className="live-voice-integrated__facts">
            <DiagnosticsFact label={t('liveVoice.integrated.session')} value={manifest.session_id ?? 'null'} />
            <DiagnosticsFact label={t('liveVoice.integrated.correlation')} value={manifest.correlation_id} />
            <DiagnosticsFact label={t('liveVoice.integrated.observedAt')} value={manifest.observed_at} />
            {p2Activation?.agent_model_selection && <DiagnosticsFact
              label={t('chat.modelSelector.activeVoiceModel')}
              value={p2Activation.agent_model_selection.model_name} />}
          </div>
          <div className="live-voice-integrated__routes">
            {manifest.segments.map(route => (
              <div
                className="live-voice-integrated__route"
                data-implementation-class={route.implementation_class}
                data-testid={`live-voice-integrated-${route.segment_id}`}
                key={route.segment_id}
              >
                <span className="live-voice-integrated__route-heading">
                  <code>{route.segment_id}</code>
                  <span className="live-voice-integrated__class">{route.implementation_class}</span>
                </span>
                <DiagnosticsFact label={t('liveVoice.integrated.requested')} value={route.requested_class} />
                <DiagnosticsFact label={t('liveVoice.integrated.owner')} value={route.owner_module ?? 'unknown'} />
                <DiagnosticsFact label={t('liveVoice.integrated.adapter')} value={route.adapter_id ?? 'null'} />
                <DiagnosticsFact label={t('liveVoice.integrated.provider')} value={route.capability_provider ?? 'null'} />
                <DiagnosticsFact label={t('liveVoice.integrated.contract')} value={route.contract_version ?? 'null'} />
                <DiagnosticsFact label={t('liveVoice.integrated.wiring')} value={route.wiring_state} />
                {route.safe_reason && <DiagnosticsFact label={t('liveVoice.integrated.reason')} value={route.safe_reason} />}
              </div>
            ))}
          </div>
          {p2Activation && (
            <div className="live-voice-integrated__facts" data-testid="live-voice-integrated-p2-activation">
              <DiagnosticsFact label={t('liveVoice.integrated.activation.status')} value={p2Activation.status} />
              <DiagnosticsFact
                label={t('liveVoice.integrated.activation.scope')}
                value={p2Activation.binding ? `${p2Activation.binding.interaction_id}:${p2Activation.binding.activation_generation}` : 'null'}
              />
            </div>
          )}
          {p3Activation && (
            <div className="live-voice-integrated__facts" data-testid="live-voice-integrated-p3-activation">
              <DiagnosticsFact label={t('liveVoice.integrated.activation.status')} value={`p3:${p3Activation.status}`} />
              <DiagnosticsFact
                label={t('liveVoice.integrated.activation.scope')}
                value={p3Activation.binding ? `${p3Activation.binding.task_id}:${p3Activation.binding.generation}` : 'null'}
              />
              {p3Activation.requested_origin_kind && p3Activation.effective_origin_kind && (
                <DiagnosticsFact
                  label="Task progress activation origin"
                  value={`${p3Activation.requested_origin_kind}->${p3Activation.effective_origin_kind}`}
                />
              )}
              {p3Activation.voice_progress && <DiagnosticsFact label="Task progress voice status" value={p3Activation.voice_progress} />}
              {p3Activation.fallback_reason && <DiagnosticsFact label="Task progress activation fallback" value={p3Activation.fallback_reason} />}
            </div>
          )}
          {legacyManualControls && p1VoiceEnabled && onP1VoiceStart && onP1VoiceStop && (
            <div className="live-voice-integrated__text-route" data-testid="live-voice-integrated-product-voice">
              <strong>Formal P1 voice</strong>
              {deviceSelection && onLoadAudioDevices && onDraftInputDevice && onDraftOutputDevice && onApplyAudioDevices && (
                <fieldset className="live-voice-integrated__device-selection" data-testid="live-voice-integrated-device-selection">
                  <legend>{t('liveVoice.integrated.audioDevices.title')}</legend>
                  <span className="live-voice-integrated__progress-note">{t('liveVoice.integrated.audioDevices.memoryOnly')}</span>
                  <button type="button" onClick={onLoadAudioDevices} disabled={deviceSelectionLocked || deviceSelection.status === 'loading'}>
                    {deviceSelection.status === 'loading'
                      ? t('liveVoice.integrated.audioDevices.loading')
                      : deviceSelection.status === 'refreshing'
                        ? t('liveVoice.integrated.audioDevices.refreshing')
                        : t('liveVoice.integrated.audioDevices.load')}
                  </button>
                  <label>
                    {t('liveVoice.integrated.audioDevices.input')}
                    <select value={draftInputDeviceToken} onChange={event => onDraftInputDevice(event.target.value)} disabled={deviceSelectionLocked}>
                      <option value={BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN}>{t('liveVoice.integrated.audioDevices.systemDefault')}</option>
                      {deviceSelection.inputs.map(option => (
                        <option value={option.token} key={option.token}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    {t('liveVoice.integrated.audioDevices.output')}
                    <select value={draftOutputDeviceToken} onChange={event => onDraftOutputDevice(event.target.value)} disabled={deviceSelectionLocked}>
                      <option value={BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN}>{t('liveVoice.integrated.audioDevices.systemDefault')}</option>
                      {deviceSelection.outputs.map(option => (
                        <option value={option.token} key={option.token}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <button type="button" onClick={onApplyAudioDevices} disabled={deviceSelectionLocked || deviceSelection.status !== 'ready'}>
                    {t('liveVoice.integrated.audioDevices.apply')}
                  </button>
                  <DiagnosticsFact label={t('liveVoice.integrated.audioDevices.status')} value={deviceSelection.status} />
                  {deviceSelection.reason !== null && <DiagnosticsFact label={t('liveVoice.integrated.audioDevices.reason')} value={deviceSelection.reason} />}
                </fieldset>
              )}
              <span className="live-voice-integrated__progress-note">
                Dedicated same-origin PCM route → Gateway batch Speech → committed Agent text → Gateway synthesis.
              </span>
              <span className="live-voice-integrated__progress-note">
                One spoken utterance retains at most {PRODUCT_P1_CAPTURE_MAX_DURATION_MS / 1000} seconds of captured audio, measured from the recognized start
                of speech. Silent listening and overlapping playback rotate the capture automatically and do not count toward the limit. Speak and press Stop
                and recognize before the limit.
              </span>
              {p1VoiceStatus === 'capturing' || p1VoiceStatus === 'playing' ? (
                <button type="button" onClick={onP1VoiceStop}>
                  {p1VoiceStatus === 'playing' ? 'Stop playback' : 'Stop and recognize'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onP1VoiceStart}
                  disabled={
                    productOperationRetained ||
                    ['loading', 'refreshing'].includes(deviceSelection?.status ?? '') ||
                    !['idle', 'recognized'].includes(p1VoiceStatus)
                  }
                >
                  Start formal voice turn
                </button>
              )}
              <DiagnosticsFact label="P1 status" value={p1VoiceStatus} />
              {p1VoiceReason !== null && <DiagnosticsFact label="P1 reason" value={p1VoiceReason} />}
              {p1VoiceReason === PRODUCT_P1_CAPTURE_DURATION_EXCEEDED_REASON && (
                <span className="live-voice-integrated__progress-note">
                  The utterance exceeded its 30-second budget; the expired capture was discarded without a new Speech or Agent submission. Refresh to start
                  again.
                </span>
              )}
            </div>
          )}
          {legacyManualControls && p2Activation?.status === 'active' && onProductInput && onProductSubmit && (
            <form
              className="live-voice-integrated__text-route"
              data-testid="live-voice-integrated-product-text"
              onSubmit={event => {
                event.preventDefault();
                onProductSubmit();
              }}
            >
              <label htmlFor="live-voice-product-text">{t('liveVoice.integrated.textRoute.label')}</label>
              <textarea
                id="live-voice-product-text"
                value={productInput}
                disabled={productTextLocked}
                onChange={event => onProductInput(event.target.value)}
                placeholder={t('liveVoice.integrated.textRoute.placeholder')}
                maxLength={100000}
              />
              <button type="submit" disabled={!productInput.trim() || productTextLocked || recognizedSpeechConfirmation !== null}>
                {t('liveVoice.integrated.textRoute.submit')}
              </button>
              <DiagnosticsFact label={t('liveVoice.integrated.textRoute.status')} value={productTextStatus} />
              {productOutput !== null && <output aria-live="polite">{productOutput}</output>}
            </form>
          )}
          {legacyManualControls && recognizedSpeechConfirmation !== null && onRecognizedSpeechConfirm && onRecognizedSpeechCancel && (
            <div className="live-voice-integrated__text-route" data-testid="live-voice-integrated-recognized-confirmation" role="note">
              <strong>{t('liveVoice.integrated.recognizedConfirmation.title')}</strong>
              <span className="live-voice-integrated__progress-note">{t(`liveVoice.integrated.recognizedConfirmation.${recognizedSpeechConfirmation}`)}</span>
              <button type="button" onClick={onRecognizedSpeechConfirm}>
                {t('liveVoice.integrated.recognizedConfirmation.confirm')}
              </button>
              <button type="button" onClick={onRecognizedSpeechCancel}>
                {t('liveVoice.integrated.recognizedConfirmation.cancel')}
              </button>
            </div>
          )}
          {legacyManualControls && p3MutationEnabled && onP3MutationOperation && onP3TaskName && onP3TaskInstruction && onP3TargetTaskId && onP3Issue && onP3Execute && (
            <div className="live-voice-integrated__text-route" data-testid="live-voice-integrated-p3-mutation">
              <strong>{t('liveVoice.integrated.taskControl.title')}</strong>
              <span className="live-voice-integrated__progress-note">{t('liveVoice.integrated.taskControl.disclosure')}</span>
              <select
                value={p3MutationOperation}
                disabled={p3MutationLocked}
                onChange={event => {
                  const operation = event.target.value;
                  onP3MutationOperation(operation === 'task.cancel' || operation === 'task.retry' ? operation : 'task.create');
                }}
              >
                <option value="task.create">{t('liveVoice.integrated.taskControl.create')}</option>
                <option value="task.cancel">{t('liveVoice.integrated.taskControl.cancel')}</option>
                {p3RetryEligible && <option value="task.retry">{t('liveVoice.integrated.taskControl.retry')}</option>}
              </select>
              {p3MutationOperation === 'task.create' ? (
                <>
                  <input
                    value={p3TaskName}
                    disabled={p3MutationLocked}
                    onChange={event => onP3TaskName(event.target.value)}
                    placeholder={t('liveVoice.integrated.taskControl.name')}
                  />
                  <textarea
                    value={p3TaskInstruction}
                    disabled={p3MutationLocked}
                    onChange={event => onP3TaskInstruction(event.target.value)}
                    placeholder={t('liveVoice.integrated.taskControl.instruction')}
                    maxLength={100000}
                  />
                </>
              ) : (
                <input
                  value={p3TargetTaskId}
                  disabled={p3MutationLocked}
                  onChange={event => onP3TargetTaskId(event.target.value)}
                  placeholder={t('liveVoice.integrated.taskControl.taskId')}
                />
              )}
              {p3MutationOperation !== 'task.create' && onP3InspectRetry && (
                <button type="button" onClick={onP3InspectRetry} disabled={!p3TargetTaskId.trim() || p3MutationLocked}>
                  {t('liveVoice.integrated.taskControl.inspectRetry')}
                </button>
              )}
              <DiagnosticsFact
                label={t('liveVoice.integrated.taskControl.retryStatus')}
                value={p3RetryEligible && p3RetryAttemptNumber !== null ? `eligible:${p3RetryAttemptNumber}/3` : p3RetryInspectionStatus}
              />
              {p3RetryInspectionReason !== null && (
                <DiagnosticsFact label={t('liveVoice.integrated.taskControl.retryReason')} value={p3RetryInspectionReason} />
              )}
              {p3MutationStatus === 'confirmed' ? (
                <button type="button" onClick={onP3Execute}>
                  {t('liveVoice.integrated.taskControl.execute')}
                </button>
              ) : (
                <button type="button" onClick={onP3Issue} disabled={p3MutationLocked || (p3MutationOperation === 'task.retry' && !p3RetryEligible)}>
                  {t('liveVoice.integrated.taskControl.confirm')}
                </button>
              )}
              <DiagnosticsFact label={t('liveVoice.integrated.taskControl.status')} value={p3MutationStatus} />
              {p3MutationReason !== null && <DiagnosticsFact label={t('liveVoice.integrated.taskControl.reason')} value={p3MutationReason} />}
            </div>
          )}
        </div>

        {progress && (
          <div
            key={progress.delivery_id}
            className="live-voice-integrated__section"
            aria-label={t('liveVoice.integrated.progress.title')}
            data-testid="live-voice-integrated-product-progress"
            data-delivery-id={progress.delivery_id}
            data-presentation-binding={
              progress.consumption_mode === 'presentation' ? productTextProgressPresentationBinding(progress) : undefined
            }
            data-session-id={progress.session_id}
            data-subject-id={progress.source_event.scope.subject_id}
            data-project-id={progress.project_id}
            data-task-id={progress.task_id}
            data-attempt-id={progress.attempt_id}
            data-event-id={progress.source_event.event_id}
            data-event-seq={String(progress.source_event.seq)}
            data-generation-id={progress.generation_id}
            data-generation={String(progress.generation)}
            data-presentation-class={progress.presentation_class ?? undefined}
            data-response-interaction-id={progress.response_ref?.interaction_id}
            data-response-id={progress.response_ref?.response_id}
            data-response-generation={progress.response_ref ? String(progress.response_ref.response_generation) : undefined}
            data-unit-id={progress.unit_id ?? undefined}
            data-expected-event-head={progress.expected_event_head === null ? undefined : String(progress.expected_event_head)}
            data-result-source-event-id={progress.consumption_mode === 'presentation' ? progress.result_source_event_id ?? '' : undefined}
          >
            <strong>{t('liveVoice.integrated.progress.title')}</strong>
            <span className="live-voice-integrated__progress-note">{t('liveVoice.integrated.progress.disclosure')}</span>
            <div className="live-voice-integrated__facts" aria-live="polite">
              <DiagnosticsFact label={t('liveVoice.integrated.progress.task')} value={progress.task_id} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.state')} value={progress.state} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.correlation')} value={progress.correlation_id} />
              <DiagnosticsFact
                label={t('liveVoice.integrated.progress.generation')}
                value={`${progress.generation_kind}:${progress.generation_id}:${progress.generation}`}
              />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.sequence')} value={String(progress.source_event.seq)} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.evidence')} value={progress.evidence_id} />
              <DiagnosticsFact label={t('liveVoice.integrated.progress.delivery')} value={progress.delivery_id} />
              <DiagnosticsFact label="Task progress origin" value={`${progress.requested_origin_kind}->${progress.effective_origin_kind}`} />
              <DiagnosticsFact label="Task progress delivery mode" value={progress.delivery_mode} />
              {progress.fallback_reason && <DiagnosticsFact label="Task progress fallback" value={progress.fallback_reason} />}
              <DiagnosticsFact label={t('liveVoice.integrated.progress.ack')} value={progressAck} />
            </div>
          </div>
        )}

        <div className="live-voice-integrated__section" aria-label={t('liveVoice.integrated.platform')}>
          <span className="live-voice-integrated__section-heading">
            <strong>{t('liveVoice.integrated.platform')}</strong>
            <button
              type="button"
              className="live-voice-integrated__refresh"
              onClick={onRefresh}
              aria-label={t('liveVoice.integrated.refresh')}
              title={t('liveVoice.integrated.refresh')}
            >
              <RefreshCw size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </span>
          <div className="live-voice-integrated__facts" aria-live="polite">
            <DiagnosticsFact label={t('liveVoice.integrated.diagnostics.browser')} value={browserEvidence} />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.browserScope')}
              value={platform?.alpha_browser_scope ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.platform')}
              value={platform?.reported_platform ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.origin')}
              value={
                platform
                  ? `scope:${platform.origin_scope}; transport:${platform.transport_security}; secure_context:${platform.secure_context}`
                  : t('liveVoice.integrated.diagnostics.pending')
              }
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.permission')}
              value={platform?.microphone_permission ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.devices')}
              value={platform ? `input:${platform.audio_input}; output:${platform.audio_output}` : t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.activation')}
              value={platform?.user_activation ?? t('liveVoice.integrated.diagnostics.pending')}
            />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.page')}
              value={
                platform
                  ? `visibility:${platform.page_visibility}; discarded:${platform.page_was_discarded ?? 'unknown'}`
                  : t('liveVoice.integrated.diagnostics.pending')
              }
            />
            <DiagnosticsFact label={t('liveVoice.integrated.diagnostics.network')} value={platform?.network ?? t('liveVoice.integrated.diagnostics.pending')} />
            <DiagnosticsFact
              label={t('liveVoice.integrated.diagnostics.aio')}
              value={
                platform
                  ? `capture:${platform.aio_capability.capture_pcm_f32}; playout:${platform.aio_capability.playout_pcm_f32}; output_selection:${platform.aio_capability.output_device_selection}; wired:false`
                  : t('liveVoice.integrated.diagnostics.pending')
              }
            />
          </div>
          {platform && platform.diagnostic_errors.length > 0 && (
            <span className="live-voice-integrated__diagnostic-error" role="status">
              {t('liveVoice.integrated.diagnostics.errors')}: <code>{platform.diagnostic_errors.join(', ')}</code>
            </span>
          )}
        </div>
      </div>
    </details>
  );
}
