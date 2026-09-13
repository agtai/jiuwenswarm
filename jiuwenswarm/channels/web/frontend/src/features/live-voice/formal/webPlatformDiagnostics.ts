import { inspectBrowserAudioPlatform, type BrowserAudioPlatformCapability } from './adapters/browserAudioIOAdapter.js';

export type MicrophonePermissionFact = 'granted' | 'denied' | 'prompt' | 'unsupported' | 'unknown';
export type DeviceAvailabilityFact = 'enumerated' | 'not_enumerated' | 'unsupported' | 'unknown';
export type UserActivationFact = 'observed' | 'required' | 'unknown';
export type BrowserEvidenceFamily = 'google_chrome' | 'other_chromium' | 'other' | 'unknown';

type DiagnosticsListener = () => void;

export interface DiagnosticsEventTargetLike {
  addEventListener(type: string, listener: DiagnosticsListener): void;
  removeEventListener(type: string, listener: DiagnosticsListener): void;
}

export interface MicrophonePermissionStatusLike extends DiagnosticsEventTargetLike {
  readonly state: string;
}

export interface DiagnosticsMediaDeviceLike {
  readonly kind: string;
  readonly deviceId?: string;
  readonly label?: string;
}

export interface DiagnosticsMediaDevicesLike extends DiagnosticsEventTargetLike {
  enumerateDevices(): Promise<readonly DiagnosticsMediaDeviceLike[]>;
}

export interface DiagnosticsDocumentLike extends DiagnosticsEventTargetLike {
  readonly visibilityState: string;
  readonly wasDiscarded?: boolean;
}

export interface WebPlatformDiagnosticsEnvironment {
  readonly is_secure_context: boolean;
  readonly protocol: string;
  readonly hostname: string;
  readonly user_agent: string;
  readonly reported_platform: string;
  readonly online: boolean | null;
  readonly user_activation_observed: boolean | null;
  readonly document: DiagnosticsDocumentLike | null;
  readonly window_events: DiagnosticsEventTargetLike | null;
  readonly media_devices: DiagnosticsMediaDevicesLike | null;
  readonly query_microphone_permission: (() => Promise<MicrophonePermissionStatusLike>) | null;
  readonly audio_capability?: Readonly<BrowserAudioPlatformCapability>;
}

export interface WebPlatformDiagnosticsSnapshot {
  readonly secure_context: boolean;
  readonly origin_scope: 'localhost_controlled' | 'deployed' | 'unknown';
  readonly transport_security: 'secure' | 'localhost_controlled_exception' | 'insecure' | 'unknown';
  readonly browser_family: BrowserEvidenceFamily;
  readonly browser_version: string | null;
  readonly alpha_browser_scope: 'desktop_google_chrome_candidate' | 'outside_declared_scope' | 'unknown';
  readonly reported_platform: string | null;
  readonly microphone_permission: MicrophonePermissionFact;
  readonly audio_input: DeviceAvailabilityFact;
  readonly audio_output: DeviceAvailabilityFact;
  readonly user_activation: UserActivationFact;
  readonly page_visibility: 'visible' | 'hidden' | 'prerender' | 'unknown';
  readonly page_was_discarded: boolean | null;
  readonly network: 'online' | 'offline' | 'unknown';
  readonly aio_capability: Readonly<BrowserAudioPlatformCapability>;
  readonly diagnostic_errors: readonly string[];
}

function defaultEnvironment(): WebPlatformDiagnosticsEnvironment {
  const browserWindow = typeof window === 'undefined' ? null : window;
  const browserNavigator = typeof navigator === 'undefined' ? null : navigator;
  const browserDocument = typeof document === 'undefined' ? null : document;
  const permissions = browserNavigator?.permissions as
    | {
        query(descriptor: Readonly<{ name: string }>): Promise<MicrophonePermissionStatusLike>;
      }
    | undefined;
  return Object.freeze({
    is_secure_context: browserWindow?.isSecureContext ?? false,
    protocol: browserWindow?.location.protocol ?? '',
    hostname: browserWindow?.location.hostname ?? '',
    user_agent: browserNavigator?.userAgent ?? '',
    reported_platform: browserNavigator?.platform ?? '',
    get online() {
      return typeof browserNavigator?.onLine === 'boolean' ? browserNavigator.onLine : null;
    },
    get user_activation_observed() {
      return typeof browserNavigator?.userActivation?.hasBeenActive === 'boolean' ? browserNavigator.userActivation.hasBeenActive : null;
    },
    document: browserDocument as unknown as DiagnosticsDocumentLike | null,
    window_events: browserWindow as unknown as DiagnosticsEventTargetLike | null,
    media_devices: (browserNavigator?.mediaDevices as unknown as DiagnosticsMediaDevicesLike | undefined) ?? null,
    query_microphone_permission: permissions ? () => permissions.query({ name: 'microphone' }) : null,
    audio_capability: inspectBrowserAudioPlatform(true),
  });
}

function browserEvidence(userAgent: string): Readonly<{
  family: BrowserEvidenceFamily;
  version: string | null;
  alphaScope: WebPlatformDiagnosticsSnapshot['alpha_browser_scope'];
}> {
  if (!userAgent.trim()) return Object.freeze({ family: 'unknown', version: null, alphaScope: 'unknown' });
  const edge = /Edg\/([0-9.]+)/.exec(userAgent);
  if (edge !== null) return Object.freeze({ family: 'other_chromium', version: edge[1], alphaScope: 'outside_declared_scope' });
  const opera = /OPR\/([0-9.]+)/.exec(userAgent);
  if (opera !== null) return Object.freeze({ family: 'other_chromium', version: opera[1], alphaScope: 'outside_declared_scope' });
  const chrome = /Chrome\/([0-9.]+)/.exec(userAgent);
  if (chrome !== null) {
    const desktop = !/(?:Android|Mobile|CriOS)\b/.test(userAgent);
    return Object.freeze({
      family: 'google_chrome',
      version: chrome[1],
      alphaScope: desktop ? 'desktop_google_chrome_candidate' : 'outside_declared_scope',
    });
  }
  if (/Chromium\//.test(userAgent)) {
    return Object.freeze({
      family: 'other_chromium',
      version: /Chromium\/([0-9.]+)/.exec(userAgent)?.[1] ?? null,
      alphaScope: 'outside_declared_scope',
    });
  }
  return Object.freeze({ family: 'other', version: null, alphaScope: 'outside_declared_scope' });
}

function isLocalhost(hostname: string): boolean {
  const normalized = hostname
    .trim()
    .toLowerCase()
    .replace(/^\[|\]$/g, '');
  return normalized === 'localhost' || normalized === '127.0.0.1' || normalized === '::1';
}

function permissionFact(value: string): MicrophonePermissionFact {
  if (value === 'granted' || value === 'denied' || value === 'prompt') return value;
  return 'unknown';
}

function pageVisibility(value: string | undefined): WebPlatformDiagnosticsSnapshot['page_visibility'] {
  if (value === 'visible' || value === 'hidden' || value === 'prerender') return value;
  return 'unknown';
}

function transportSecurity(environment: Readonly<WebPlatformDiagnosticsEnvironment>): WebPlatformDiagnosticsSnapshot['transport_security'] {
  if (environment.is_secure_context) return 'secure';
  if (isLocalhost(environment.hostname)) return 'localhost_controlled_exception';
  if (environment.protocol.trim()) return 'insecure';
  return 'unknown';
}

export async function collectWebPlatformDiagnostics(
  environment: Readonly<WebPlatformDiagnosticsEnvironment> = defaultEnvironment()
): Promise<Readonly<WebPlatformDiagnosticsSnapshot>> {
  const errors: string[] = [];
  let microphonePermission: MicrophonePermissionFact = environment.query_microphone_permission === null ? 'unsupported' : 'unknown';
  if (environment.query_microphone_permission !== null) {
    try {
      microphonePermission = permissionFact((await environment.query_microphone_permission()).state);
    } catch {
      errors.push('MICROPHONE_PERMISSION_QUERY_FAILED');
    }
  }

  let audioInput: DeviceAvailabilityFact = environment.media_devices === null ? 'unsupported' : 'not_enumerated';
  let audioOutput: DeviceAvailabilityFact = environment.media_devices === null ? 'unsupported' : 'not_enumerated';
  // Device enumeration may expose stable identifiers and labels. The coarse
  // diagnostics plane does not read it until microphone permission is already
  // granted; the explicit device-selection owner owns any permission prompt.
  if (environment.media_devices !== null && microphonePermission === 'granted') {
    audioInput = 'unknown';
    audioOutput = 'unknown';
    try {
      const devices = await environment.media_devices.enumerateDevices();
      audioInput = devices.some(device => device.kind === 'audioinput') ? 'enumerated' : 'not_enumerated';
      audioOutput = devices.some(device => device.kind === 'audiooutput') ? 'enumerated' : 'not_enumerated';
    } catch {
      errors.push('MEDIA_DEVICE_ENUMERATION_FAILED');
    }
  }

  const browser = browserEvidence(environment.user_agent);
  const local = isLocalhost(environment.hostname);
  const audioCapability = environment.audio_capability ?? inspectBrowserAudioPlatform(true);
  return Object.freeze({
    secure_context: environment.is_secure_context,
    origin_scope: environment.hostname.trim() ? (local ? 'localhost_controlled' : 'deployed') : 'unknown',
    transport_security: transportSecurity(environment),
    browser_family: browser.family,
    browser_version: browser.version,
    alpha_browser_scope: browser.alphaScope,
    reported_platform: environment.reported_platform.trim() || null,
    microphone_permission: microphonePermission,
    audio_input: audioInput,
    audio_output: audioOutput,
    user_activation: environment.user_activation_observed === null ? 'unknown' : environment.user_activation_observed ? 'observed' : 'required',
    page_visibility: pageVisibility(environment.document?.visibilityState),
    page_was_discarded: typeof environment.document?.wasDiscarded === 'boolean' ? environment.document.wasDiscarded : null,
    network: environment.online === null ? 'unknown' : environment.online ? 'online' : 'offline',
    aio_capability: audioCapability,
    diagnostic_errors: Object.freeze(errors),
  });
}

export class WebPlatformDiagnosticsMonitor {
  readonly #enabled: boolean;
  readonly #environment: Readonly<WebPlatformDiagnosticsEnvironment>;
  readonly #onSnapshot: (snapshot: Readonly<WebPlatformDiagnosticsSnapshot>) => void;
  readonly #refreshListener: DiagnosticsListener;
  #permissionStatus: MicrophonePermissionStatusLike | null = null;
  readonly #diagnosticErrors = new Set<string>();
  #started = false;
  #generation = 0;
  #lifecycleGeneration = 0;

  constructor(
    options: Readonly<{
      enabled: boolean;
      environment?: WebPlatformDiagnosticsEnvironment;
      on_snapshot: (snapshot: Readonly<WebPlatformDiagnosticsSnapshot>) => void;
    }>
  ) {
    if (typeof options.enabled !== 'boolean') throw new TypeError('enabled must be boolean');
    this.#enabled = options.enabled;
    this.#environment = options.environment ?? defaultEnvironment();
    this.#onSnapshot = options.on_snapshot;
    this.#refreshListener = () => {
      void this.refresh();
    };
  }

  start(): boolean {
    if (!this.#enabled || this.#started) return false;
    this.#started = true;
    this.#diagnosticErrors.clear();
    const lifecycleGeneration = ++this.#lifecycleGeneration;
    try {
      this.#environment.document?.addEventListener('visibilitychange', this.#refreshListener);
      this.#environment.media_devices?.addEventListener('devicechange', this.#refreshListener);
      this.#environment.window_events?.addEventListener('online', this.#refreshListener);
      this.#environment.window_events?.addEventListener('offline', this.#refreshListener);
    } catch {
      this.stop();
      return false;
    }
    void this.#attachPermissionListener(lifecycleGeneration);
    void this.refresh();
    return true;
  }

  async refresh(): Promise<boolean> {
    if (!this.#enabled || !this.#started) return false;
    const generation = ++this.#generation;
    const snapshot = await collectWebPlatformDiagnostics(this.#environment);
    if (!this.#started || generation !== this.#generation) return false;
    const observableSnapshot = Object.freeze({
      ...snapshot,
      diagnostic_errors: Object.freeze([...new Set([...snapshot.diagnostic_errors, ...this.#diagnosticErrors])]),
    });
    try {
      this.#onSnapshot(observableSnapshot);
    } catch {
      return false;
    }
    return true;
  }

  stop(): boolean {
    if (!this.#started) return false;
    this.#started = false;
    this.#lifecycleGeneration += 1;
    this.#generation += 1;
    const removals: readonly [DiagnosticsEventTargetLike | null, string][] = [
      [this.#environment.document, 'visibilitychange'],
      [this.#environment.media_devices, 'devicechange'],
      [this.#environment.window_events, 'online'],
      [this.#environment.window_events, 'offline'],
      [this.#permissionStatus, 'change'],
    ];
    for (const [target, type] of removals) {
      try {
        target?.removeEventListener(type, this.#refreshListener);
      } catch {
        // Continue attempting every registered listener release.
      }
    }
    this.#permissionStatus = null;
    return true;
  }

  async #attachPermissionListener(lifecycleGeneration: number): Promise<void> {
    if (this.#environment.query_microphone_permission === null) return;
    let status: MicrophonePermissionStatusLike;
    try {
      status = await this.#environment.query_microphone_permission();
    } catch {
      this.#recordDiagnosticError('MICROPHONE_PERMISSION_LISTENER_QUERY_FAILED', lifecycleGeneration);
      return;
    }
    if (!this.#started || lifecycleGeneration !== this.#lifecycleGeneration) return;
    try {
      this.#permissionStatus?.removeEventListener('change', this.#refreshListener);
      if (!this.#started || lifecycleGeneration !== this.#lifecycleGeneration) return;
      this.#permissionStatus = status;
      status.addEventListener('change', this.#refreshListener);
      if (!this.#started || lifecycleGeneration !== this.#lifecycleGeneration) {
        status.removeEventListener('change', this.#refreshListener);
        if (this.#permissionStatus === status) this.#permissionStatus = null;
        return;
      }
    } catch {
      try {
        status.removeEventListener('change', this.#refreshListener);
      } catch {
        // The stable diagnostic below remains authoritative even if the target also rejects cleanup.
      }
      if (this.#permissionStatus === status) this.#permissionStatus = null;
      this.#recordDiagnosticError('MICROPHONE_PERMISSION_LISTENER_REGISTRATION_FAILED', lifecycleGeneration);
    }
  }

  #recordDiagnosticError(error: string, lifecycleGeneration: number): void {
    if (!this.#started || lifecycleGeneration !== this.#lifecycleGeneration) return;
    this.#diagnosticErrors.add(error);
    void this.refresh();
  }
}
