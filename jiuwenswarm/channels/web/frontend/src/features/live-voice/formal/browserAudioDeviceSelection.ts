export type BrowserAudioDeviceSelectionStatus =
  | 'idle'
  | 'loading'
  | 'refreshing'
  | 'ready'
  | 'permission_denied'
  | 'unavailable'
  | 'selection_invalidated'
  | 'closed';

export type BrowserAudioDeviceSelectionKind = 'audioinput' | 'audiooutput';

type DeviceSelectionListener = () => void;

export interface BrowserAudioSelectionDeviceLike {
  readonly kind: string;
  readonly deviceId: string;
  readonly label: string;
}

export interface BrowserAudioSelectionTrackLike {
  stop(): void;
}

export interface BrowserAudioSelectionStreamLike {
  getTracks(): readonly BrowserAudioSelectionTrackLike[];
}

export interface BrowserAudioSelectionPermissionLike {
  readonly state: string;
  addEventListener(type: 'change', listener: DeviceSelectionListener): void;
  removeEventListener(type: 'change', listener: DeviceSelectionListener): void;
}

export interface BrowserAudioSelectionMediaDevicesLike {
  getUserMedia(constraints: Readonly<{ audio: true; video: false }>): Promise<BrowserAudioSelectionStreamLike>;
  enumerateDevices(): Promise<readonly BrowserAudioSelectionDeviceLike[]>;
  addEventListener(type: 'devicechange', listener: DeviceSelectionListener): void;
  removeEventListener(type: 'devicechange', listener: DeviceSelectionListener): void;
}

export interface BrowserAudioDeviceSelectionEnvironment {
  readonly is_secure_context: boolean;
  readonly media_devices: BrowserAudioSelectionMediaDevicesLike | null;
  readonly query_microphone_permission: (() => Promise<BrowserAudioSelectionPermissionLike>) | null;
  readonly create_token: (() => string) | null;
}

export interface BrowserAudioDeviceOption {
  readonly token: string;
  readonly kind: BrowserAudioDeviceSelectionKind;
  readonly label: string;
}

export interface BrowserAudioDeviceSelectionSnapshot {
  readonly status: BrowserAudioDeviceSelectionStatus;
  readonly reason: string | null;
  readonly inventory_generation: number;
  readonly selection_generation: number;
  readonly inputs: readonly Readonly<BrowserAudioDeviceOption>[];
  readonly outputs: readonly Readonly<BrowserAudioDeviceOption>[];
  readonly applied_input_token: string;
  readonly applied_output_token: string;
}

export interface BrowserAudioAppliedDeviceRoute {
  readonly selection_generation: number;
  readonly input_device_id?: string;
  readonly output_device_id?: string;
}

export const BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN = 'system_default';
const MAX_DEVICE_LABEL_CODE_POINTS = 128;

export class BrowserAudioDeviceSelectionViolation extends Error {
  constructor(readonly reason: string) {
    super('browser audio device selection failed');
    this.name = 'BrowserAudioDeviceSelectionViolation';
  }
}

interface PrivateDeviceOption extends BrowserAudioDeviceOption {
  readonly deviceId: string;
}

function defaultEnvironment(): BrowserAudioDeviceSelectionEnvironment {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return Object.freeze({
      is_secure_context: false,
      media_devices: null,
      query_microphone_permission: null,
      create_token: null,
    });
  }
  const permissions = navigator.permissions as
    | { query(descriptor: Readonly<{ name: 'microphone' }>): Promise<BrowserAudioSelectionPermissionLike> }
    | undefined;
  return Object.freeze({
    is_secure_context: window.isSecureContext,
    media_devices: (navigator.mediaDevices as unknown as BrowserAudioSelectionMediaDevicesLike | undefined) ?? null,
    query_microphone_permission: permissions ? () => permissions.query({ name: 'microphone' }) : null,
    create_token: typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? () => crypto.randomUUID() : null,
  });
}

function requiredToken(value: string): string {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_TOKEN_INVALID');
  }
  return value.trim();
}

function stableLabel(value: string, kind: BrowserAudioDeviceSelectionKind, index: number): string {
  const label =
    typeof value === 'string'
      ? Array.from(value.replace(/[\u0000-\u001f\u007f]/g, ' ').trim())
          .slice(0, MAX_DEVICE_LABEL_CODE_POINTS)
          .join('')
          .trim()
      : '';
  if (label.length > 0) return label;
  return `${kind === 'audioinput' ? 'Microphone' : 'Speaker'} ${index + 1}`;
}

function stopPermissionProbe(stream: BrowserAudioSelectionStreamLike): boolean {
  let failed = false;
  let tracks: readonly BrowserAudioSelectionTrackLike[];
  try {
    tracks = stream.getTracks();
  } catch {
    return true;
  }
  for (const track of tracks) {
    try {
      track.stop();
    } catch {
      failed = true;
    }
  }
  return failed;
}

export class BrowserAudioDeviceSelectionOwner {
  readonly #enabled: boolean;
  readonly #environment: BrowserAudioDeviceSelectionEnvironment;
  readonly #onSnapshot?: (snapshot: Readonly<BrowserAudioDeviceSelectionSnapshot>) => void;
  readonly #onDeviceInvalidated?: (reason: string) => void;
  readonly #onDeviceChange: DeviceSelectionListener;
  readonly #onPermissionChange: DeviceSelectionListener;
  #status: BrowserAudioDeviceSelectionStatus;
  #reason: string | null = null;
  #inventoryGeneration = 0;
  #selectionGeneration = 1;
  #operationGeneration = 0;
  #inputs: readonly PrivateDeviceOption[] = Object.freeze([]);
  #outputs: readonly PrivateDeviceOption[] = Object.freeze([]);
  #appliedInputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
  #appliedOutputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
  #permissionStatus: BrowserAudioSelectionPermissionLike | null = null;
  #listenersAttached = false;
  #deviceRefreshQueued = false;
  #closed = false;

  constructor(
    options: Readonly<{
      enabled: boolean;
      environment?: BrowserAudioDeviceSelectionEnvironment;
      on_snapshot?: (snapshot: Readonly<BrowserAudioDeviceSelectionSnapshot>) => void;
      on_device_invalidated?: (reason: string) => void;
    }>
  ) {
    this.#enabled = options.enabled;
    this.#environment = this.#enabled ? (options.environment ?? defaultEnvironment()) : DISABLED_ENVIRONMENT;
    this.#onSnapshot = options.on_snapshot;
    this.#onDeviceInvalidated = options.on_device_invalidated;
    this.#status = this.#enabled ? 'idle' : 'closed';
    this.#closed = !this.#enabled;
    this.#onDeviceChange = () => void this.#refreshAfterDeviceChange();
    this.#onPermissionChange = () => this.#observePermissionChange();
  }

  snapshot(): Readonly<BrowserAudioDeviceSelectionSnapshot> {
    return Object.freeze({
      status: this.#status,
      reason: this.#reason,
      inventory_generation: this.#inventoryGeneration,
      selection_generation: this.#selectionGeneration,
      inputs: Object.freeze(this.#inputs.map(({ token, kind, label }) => Object.freeze({ token, kind, label }))),
      outputs: Object.freeze(this.#outputs.map(({ token, kind, label }) => Object.freeze({ token, kind, label }))),
      applied_input_token: this.#appliedInputToken,
      applied_output_token: this.#appliedOutputToken,
    });
  }

  async load(): Promise<Readonly<BrowserAudioDeviceSelectionSnapshot>> {
    if (!this.#enabled || this.#closed) throw new BrowserAudioDeviceSelectionViolation('FEATURE_DISABLED');
    if (this.#status === 'loading') throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_LOAD_IN_PROGRESS');
    if (this.#status === 'refreshing') throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_REFRESH_IN_PROGRESS');
    if (!this.#environment.is_secure_context) return this.#fail('INSECURE_CONTEXT');
    if (this.#environment.media_devices === null || this.#environment.create_token === null) {
      return this.#fail('AUDIO_DEVICE_SELECTION_UNAVAILABLE');
    }
    const priorInputId = this.#status === 'ready' ? this.#resolveToken(this.#appliedInputToken, this.#inputs) : null;
    const priorOutputId = this.#status === 'ready' ? this.#resolveToken(this.#appliedOutputToken, this.#outputs) : null;
    const operation = ++this.#operationGeneration;
    this.#status = 'loading';
    this.#reason = null;
    this.#publish();
    let permission: BrowserAudioSelectionPermissionLike | null = null;
    try {
      if (this.#environment.query_microphone_permission !== null) {
        try {
          permission = await this.#environment.query_microphone_permission();
        } catch {
          permission = null;
        }
        this.#requireCurrent(operation);
        if (permission?.state === 'denied') return this.#fail('MICROPHONE_PERMISSION_DENIED');
      }
      if (permission?.state !== 'granted') {
        const stream = await this.#environment.media_devices.getUserMedia({ audio: true, video: false });
        const stale = !this.#isCurrent(operation);
        const cleanupFailed = stopPermissionProbe(stream);
        if (stale) throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_SELECTION_CANCELLED');
        if (cleanupFailed) return this.#fail('MICROPHONE_PERMISSION_PROBE_CLEANUP_FAILED');
      }
      const devices = await this.#environment.media_devices.enumerateDevices();
      this.#requireCurrent(operation);
      if (permission?.state === 'denied') return this.#fail('MICROPHONE_PERMISSION_DENIED');
      const ids = new Set(devices.map(device => this.#deviceKey(device.kind, device.deviceId)));
      if (priorInputId !== null && !ids.has(this.#deviceKey('audioinput', priorInputId))) {
        this.#invalidate('AUDIO_INPUT_SELECTION_LOST');
        return this.snapshot();
      }
      if (priorOutputId !== null && !ids.has(this.#deviceKey('audiooutput', priorOutputId))) {
        this.#invalidate('AUDIO_OUTPUT_SELECTION_LOST');
        return this.snapshot();
      }
      this.#adoptInventory(devices);
      this.#appliedInputToken = this.#tokenForId(priorInputId, this.#inputs);
      this.#appliedOutputToken = this.#tokenForId(priorOutputId, this.#outputs);
      this.#attachListeners(permission);
      if (permission?.state === 'denied') {
        this.#invalidate('MICROPHONE_PERMISSION_REVOKED');
        return this.snapshot();
      }
      this.#requireCurrent(operation);
      this.#status = 'ready';
      this.#reason = null;
      this.#publish();
      return this.snapshot();
    } catch (error) {
      // A close or a newer load owns the terminal state. Browser rejection from
      // the superseded operation must not resurrect a closed/invalidated owner.
      if (!this.#isCurrent(operation)) {
        throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_SELECTION_CANCELLED');
      }
      if (error instanceof BrowserAudioDeviceSelectionViolation) {
        if (error.reason === 'AUDIO_DEVICE_SELECTION_CANCELLED') throw error;
        return this.#fail(error.reason);
      }
      return this.#fail(this.#browserFailureReason(error));
    }
  }

  apply(input: Readonly<{ inventory_generation: number; input_token: string; output_token: string }>): Readonly<BrowserAudioDeviceSelectionSnapshot> {
    if (!this.#enabled || this.#closed) throw new BrowserAudioDeviceSelectionViolation('FEATURE_DISABLED');
    if (this.#status === 'refreshing') throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_REFRESH_IN_PROGRESS');
    if (this.#status !== 'ready' || input.inventory_generation !== this.#inventoryGeneration) {
      throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_INVENTORY_STALE');
    }
    const inputToken = requiredToken(input.input_token);
    const outputToken = requiredToken(input.output_token);
    this.#resolveToken(inputToken, this.#inputs);
    this.#resolveToken(outputToken, this.#outputs);
    this.#appliedInputToken = inputToken;
    this.#appliedOutputToken = outputToken;
    this.#selectionGeneration += 1;
    this.#reason = null;
    this.#publish();
    return this.snapshot();
  }

  appliedRoute(): Readonly<BrowserAudioAppliedDeviceRoute> {
    if (!this.#enabled || this.#closed) throw new BrowserAudioDeviceSelectionViolation('FEATURE_DISABLED');
    if (this.#status === 'loading') throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_LOAD_IN_PROGRESS');
    if (this.#status === 'refreshing') throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_REFRESH_IN_PROGRESS');
    if (this.#status === 'selection_invalidated') {
      throw new BrowserAudioDeviceSelectionViolation(this.#reason ?? 'AUDIO_DEVICE_SELECTION_INVALIDATED');
    }
    if (this.#status === 'permission_denied' || this.#status === 'unavailable') {
      throw new BrowserAudioDeviceSelectionViolation(this.#reason ?? 'AUDIO_DEVICE_SELECTION_UNAVAILABLE');
    }
    const inputId = this.#resolveToken(this.#appliedInputToken, this.#inputs);
    const outputId = this.#resolveToken(this.#appliedOutputToken, this.#outputs);
    return Object.freeze({
      selection_generation: this.#selectionGeneration,
      ...(inputId === null ? {} : { input_device_id: inputId }),
      ...(outputId === null ? {} : { output_device_id: outputId }),
    });
  }

  close(): boolean {
    if (this.#closed) return false;
    this.#closed = true;
    this.#operationGeneration += 1;
    this.#deviceRefreshQueued = false;
    this.#detachListeners();
    this.#inputs = Object.freeze([]);
    this.#outputs = Object.freeze([]);
    this.#appliedInputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
    this.#appliedOutputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
    this.#selectionGeneration += 1;
    this.#status = 'closed';
    this.#reason = null;
    this.#publish();
    return true;
  }

  #adoptInventory(devices: readonly BrowserAudioSelectionDeviceLike[]): void {
    const createToken = this.#environment.create_token;
    if (createToken === null) throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_SELECTION_UNAVAILABLE');
    const seen = new Set<string>();
    const tokens = new Set<string>([BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN]);
    const inputs: PrivateDeviceOption[] = [];
    const outputs: PrivateDeviceOption[] = [];
    for (const device of devices) {
      if (device.kind !== 'audioinput' && device.kind !== 'audiooutput') continue;
      const deviceId = typeof device.deviceId === 'string' ? device.deviceId.trim() : '';
      if (!deviceId || deviceId === 'default' || seen.has(`${device.kind}\u0000${deviceId}`)) continue;
      seen.add(`${device.kind}\u0000${deviceId}`);
      const target = device.kind === 'audioinput' ? inputs : outputs;
      const token = requiredToken(createToken());
      if (tokens.has(token)) throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_TOKEN_COLLISION');
      tokens.add(token);
      target.push(
        Object.freeze({
          token,
          kind: device.kind,
          label: stableLabel(device.label, device.kind, target.length),
          deviceId,
        })
      );
    }
    this.#inputs = Object.freeze(inputs);
    this.#outputs = Object.freeze(outputs);
    this.#inventoryGeneration += 1;
  }

  async #refreshAfterDeviceChange(): Promise<void> {
    if (this.#closed || this.#environment.media_devices === null) return;
    if (this.#status === 'refreshing') {
      this.#deviceRefreshQueued = true;
      return;
    }
    if (this.#status !== 'ready') return;
    const operation = ++this.#operationGeneration;
    const oldInputId = this.#resolveToken(this.#appliedInputToken, this.#inputs);
    const oldOutputId = this.#resolveToken(this.#appliedOutputToken, this.#outputs);
    // Fence every route handle issued before the browser reported a device
    // change. The new generation is publishable only after current verification.
    this.#selectionGeneration += 1;
    this.#status = 'refreshing';
    this.#reason = null;
    this.#deviceRefreshQueued = false;
    this.#publish();
    try {
      do {
        this.#deviceRefreshQueued = false;
        const devices = await this.#environment.media_devices.enumerateDevices();
        this.#requireCurrent(operation);
        const ids = new Set(devices.map(device => this.#deviceKey(device.kind, device.deviceId)));
        const missingInput = oldInputId !== null && !ids.has(this.#deviceKey('audioinput', oldInputId));
        const missingOutput = oldOutputId !== null && !ids.has(this.#deviceKey('audiooutput', oldOutputId));
        if (missingInput || missingOutput) {
          this.#invalidate(missingInput ? 'AUDIO_INPUT_SELECTION_LOST' : 'AUDIO_OUTPUT_SELECTION_LOST');
          return;
        }
        this.#adoptInventory(devices);
        // Device IDs remain private; remap the applied choice to this inventory's
        // fresh opaque tokens instead of retaining the old token generation.
        this.#appliedInputToken = this.#tokenForId(oldInputId, this.#inputs);
        this.#appliedOutputToken = this.#tokenForId(oldOutputId, this.#outputs);
      } while (this.#deviceRefreshQueued);
      this.#status = 'ready';
      this.#publish();
    } catch {
      if (this.#isCurrent(operation)) this.#invalidate('AUDIO_DEVICE_SELECTION_UNVERIFIED');
    }
  }

  #observePermissionChange(): void {
    if (this.#closed || this.#permissionStatus?.state !== 'denied') return;
    this.#invalidate('MICROPHONE_PERMISSION_REVOKED');
  }

  #attachListeners(permission: BrowserAudioSelectionPermissionLike | null): void {
    if (this.#environment.media_devices === null) return;
    this.#detachListeners();
    let mediaListenerAttached = false;
    try {
      this.#environment.media_devices.addEventListener('devicechange', this.#onDeviceChange);
      mediaListenerAttached = true;
      if (permission !== null) {
        permission.addEventListener('change', this.#onPermissionChange);
        this.#permissionStatus = permission;
      }
      this.#listenersAttached = true;
    } catch {
      if (permission !== null) {
        try {
          permission.removeEventListener('change', this.#onPermissionChange);
        } catch {
          // The failing registration cannot leave live ownership behind.
        }
      }
      if (mediaListenerAttached) {
        try {
          this.#environment.media_devices.removeEventListener('devicechange', this.#onDeviceChange);
        } catch {
          // Generation fencing still makes a retained callback inert.
        }
      }
      this.#permissionStatus = null;
      this.#listenersAttached = false;
      throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_LISTENER_FAILED');
    }
  }

  #detachListeners(): void {
    if (this.#listenersAttached) {
      try {
        this.#environment.media_devices?.removeEventListener('devicechange', this.#onDeviceChange);
      } catch {
        // Closed generation makes a retained browser callback inert.
      }
    }
    this.#listenersAttached = false;
    if (this.#permissionStatus !== null) {
      try {
        this.#permissionStatus.removeEventListener('change', this.#onPermissionChange);
      } catch {
        // Closed generation makes a retained browser callback inert.
      }
    }
    this.#permissionStatus = null;
  }

  #resolveToken(token: string, values: readonly PrivateDeviceOption[]): string | null {
    if (token === BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN) return null;
    const match = values.find(value => value.token === token);
    if (match === undefined) throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_TOKEN_STALE');
    return match.deviceId;
  }

  #deviceKey(kind: string, deviceId: string): string {
    return `${kind}\u0000${typeof deviceId === 'string' ? deviceId.trim() : ''}`;
  }

  #tokenForId(deviceId: string | null, values: readonly PrivateDeviceOption[]): string {
    if (deviceId === null) return BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
    const match = values.find(value => value.deviceId === deviceId);
    if (match === undefined) throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_SELECTION_INVALIDATED');
    return match.token;
  }

  #invalidate(reason: string): void {
    this.#operationGeneration += 1;
    this.#deviceRefreshQueued = false;
    this.#inputs = Object.freeze([]);
    this.#outputs = Object.freeze([]);
    this.#appliedInputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
    this.#appliedOutputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
    this.#selectionGeneration += 1;
    this.#status = 'selection_invalidated';
    this.#reason = reason;
    this.#detachListeners();
    this.#publish();
    try {
      this.#onDeviceInvalidated?.(reason);
    } catch {
      // UI observers never own browser permission or device state.
    }
  }

  #fail(reason: string): Readonly<BrowserAudioDeviceSelectionSnapshot> {
    this.#deviceRefreshQueued = false;
    this.#detachListeners();
    this.#inputs = Object.freeze([]);
    this.#outputs = Object.freeze([]);
    this.#appliedInputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
    this.#appliedOutputToken = BROWSER_AUDIO_SYSTEM_DEFAULT_TOKEN;
    this.#selectionGeneration += 1;
    this.#status = reason === 'MICROPHONE_PERMISSION_DENIED' ? 'permission_denied' : 'unavailable';
    this.#reason = reason;
    this.#publish();
    try {
      this.#onDeviceInvalidated?.(reason);
    } catch {
      // UI observers never own browser permission or device state.
    }
    return this.snapshot();
  }

  #browserFailureReason(error: unknown): string {
    const name = typeof error === 'object' && error !== null && 'name' in error ? String(error.name) : '';
    if (name === 'NotAllowedError' || name === 'SecurityError') return 'MICROPHONE_PERMISSION_DENIED';
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return 'AUDIO_INPUT_NOT_FOUND';
    return 'AUDIO_DEVICE_ENUMERATION_FAILED';
  }

  #isCurrent(operation: number): boolean {
    return !this.#closed && operation === this.#operationGeneration;
  }

  #requireCurrent(operation: number): void {
    if (!this.#isCurrent(operation)) throw new BrowserAudioDeviceSelectionViolation('AUDIO_DEVICE_SELECTION_CANCELLED');
  }

  #publish(): void {
    try {
      this.#onSnapshot?.(this.snapshot());
    } catch {
      // UI observers cannot mutate private device ownership.
    }
  }
}

const DISABLED_ENVIRONMENT: BrowserAudioDeviceSelectionEnvironment = Object.freeze({
  is_secure_context: false,
  media_devices: null,
  query_microphone_permission: null,
  create_token: null,
});
