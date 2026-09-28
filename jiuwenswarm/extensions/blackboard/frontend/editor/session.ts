// One open document: the Yjs document, its connection to the host's document service, and what
// the editor shows about it. The provider is created through a factory, so tests run without a
// network.
import type { DocToken, Role } from '../types';

export type SessionStatus = 'connecting' | 'syncing' | 'saved' | 'offline' | 'unavailable' | 'closed';

export interface SessionState {
  status: SessionStatus;
  readOnly: boolean;
  // The document or its workspace is archived.
  frozen: boolean;
  role: Role | null;
  // Why the session closed or cannot connect: an error code from the host or the service.
  reason: string | null;
}

export interface ProviderEvents {
  onStatus: (status: 'connecting' | 'connected' | 'disconnected') => void;
  onSynced: (synced: boolean) => void;
  onUnsyncedChanges: (count: number) => void;
  onAuthenticated: (scope: 'read-write' | 'readonly') => void;
  onAuthenticationFailed: (reason: string) => void;
}

export interface ProviderHandle {
  destroy: () => void;
}

export type ProviderFactory = (options: {
  url: string;
  name: string;
  token: () => Promise<string>;
  events: ProviderEvents;
}) => ProviderHandle;

// A token fetched this recently is handed to the provider as is; older ones are fetched again.
const TOKEN_REUSE_MS = 30_000;
// Codes after which trying again cannot help: the member left, or the document is gone.
const CLOSING_CODES = new Set(['not_member', 'not_found', 'forbidden', 'unauthorized', 'disabled']);

export function canWrite(role: Role | null): boolean {
  return role === 'owner' || role === 'editor';
}

function codeOf(error: unknown): string {
  const code = typeof error === 'object' && error !== null ? (error as { code?: unknown }).code : undefined;
  return typeof code === 'string' ? code : 'internal';
}

export class DocSession {
  private state: SessionState = { status: 'connecting', readOnly: true, frozen: false, role: null, reason: null };
  private readonly listeners = new Set<() => void>();
  private provider: ProviderHandle | null = null;
  private lastToken: { value: string; at: number } | null = null;
  private socket: 'connecting' | 'connected' | 'disconnected' = 'connecting';
  private synced = false;
  private unsynced = 0;
  private scope: 'read-write' | 'readonly' | null = null;
  private closed = false;

  constructor(
    readonly docId: string,
    private readonly fetchToken: (docId: string) => Promise<DocToken>,
    private readonly createProvider: ProviderFactory,
    private readonly now: () => number = Date.now,
  ) {}

  getState = (): SessionState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  async start(): Promise<void> {
    let first: DocToken;
    try {
      first = await this.fetch();
    } catch {
      return;
    }
    if (this.closed) return;
    this.provider = this.createProvider({
      url: first.url,
      name: this.docId,
      token: () => this.token(),
      events: {
        onStatus: (status) => {
          this.socket = status;
          if (status !== 'connected') this.synced = false;
          this.update();
        },
        onSynced: (synced) => {
          this.synced = synced;
          this.update();
        },
        onUnsyncedChanges: (count) => {
          this.unsynced = count;
          this.update();
        },
        onAuthenticated: (scope) => {
          this.scope = scope;
          this.update();
        },
        onAuthenticationFailed: (reason) => {
          // An expired token is fetched again on the next connect; anything else is reported.
          if (reason !== 'token_expired') this.update({ reason });
        },
      },
    });
  }

  destroy(): void {
    this.closed = true;
    this.provider?.destroy();
    this.provider = null;
  }

  // The provider asks for a token on every connect and whenever the service rechecks access.
  private async token(): Promise<string> {
    if (this.lastToken && this.now() - this.lastToken.at < TOKEN_REUSE_MS) {
      const value = this.lastToken.value;
      this.lastToken = null;
      return value;
    }
    return (await this.fetch()).token;
  }

  private async fetch(): Promise<DocToken> {
    try {
      const result = await this.fetchToken(this.docId);
      this.lastToken = { value: result.token, at: this.now() };
      // A token sync does not tell the provider about a new role, so the role comes from here.
      this.scope = null;
      this.update({ role: result.role, frozen: Boolean(result.frozen), reason: null });
      return result;
    } catch (error) {
      const code = codeOf(error);
      if (CLOSING_CODES.has(code)) {
        this.update({ reason: code });
        this.close();
      } else {
        this.update({ reason: code });
      }
      throw error;
    }
  }

  private close(): void {
    this.closed = true;
    this.update();
    // Not from inside the provider's own token callback.
    const provider = this.provider;
    this.provider = null;
    if (provider) setTimeout(() => provider.destroy(), 0);
  }

  private update(patch: Partial<SessionState> = {}): void {
    const next = { ...this.state, ...patch };
    next.readOnly = next.frozen || !canWrite(next.role) || this.scope === 'readonly';
    next.status = this.statusOf(next);
    const changed = (Object.keys(next) as Array<keyof SessionState>).some((key) => next[key] !== this.state[key]);
    if (!changed) return;
    this.state = next;
    for (const listener of this.listeners) listener();
  }

  private statusOf(next: SessionState): SessionStatus {
    if (this.closed) return 'closed';
    if (next.reason === 'unavailable' && this.socket !== 'connected') return 'unavailable';
    if (this.socket === 'disconnected') return 'offline';
    if (this.socket === 'connecting') return 'connecting';
    return this.synced && this.unsynced === 0 ? 'saved' : 'syncing';
  }
}
