import type { NativeVoiceRequest } from './headlessNativeVoice';

/** Control RPC only. Media retains its independent production WebSocket owner.
 * An instance never reconnects or replays requests after loss of authority.
 */
export class HeadlessVoiceControl {
  private readonly socket: WebSocket;
  private readonly ready: Promise<void>;
  private readonly pending = new Map<string, { accept: (value: unknown) => void; reject: (error: Error) => void }>();
  private closed = false;

  constructor(url: string, onDisconnected: () => void) {
    this.socket = new WebSocket(url);
    this.ready = new Promise((accept, reject) => {
      const timeout = setTimeout(() => { reject(new Error('VOICE_CONTROL_CONNECT_TIMEOUT')); this.close(); }, 10_000);
      this.socket.addEventListener('open', () => { clearTimeout(timeout); accept(); }, { once: true });
      this.socket.addEventListener('error', () => { clearTimeout(timeout); reject(new Error('VOICE_CONTROL_CONNECT_FAILED')); }, { once: true });
      this.socket.addEventListener('close', () => { clearTimeout(timeout); reject(new Error('VOICE_CONTROL_CLOSED')); }, { once: true });
    });
    this.socket.addEventListener('message', event => {
      if (typeof event.data !== 'string' || event.data.length > 2_097_152) return;
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (!message || message.type !== 'res' || typeof message.id !== 'string') return;
      const pending = this.pending.get(message.id);
      if (!pending) return;
      this.pending.delete(message.id);
      if (message.ok === true) pending.accept(message.payload);
      else pending.reject(Object.assign(new Error(typeof message.error === 'string' ? message.error : 'VOICE_CONTROL_REQUEST_FAILED'),
        { code: message.code, reason: message.payload?.error?.reason ?? message.payload?.reason }));
    });
    this.socket.addEventListener('close', () => {
      for (const pending of this.pending.values()) pending.reject(new Error('VOICE_CONTROL_CLOSED'));
      this.pending.clear();
      const unexpected = !this.closed;
      this.closed = true;
      if (unexpected) onDisconnected();
    });
  }

  request: NativeVoiceRequest = async (method, params, options = {}) => {
    await this.ready;
    if (this.closed || this.socket.readyState !== WebSocket.OPEN) throw new Error('VOICE_CONTROL_CLOSED');
    const id = options.requestId ?? `host-rpc-${crypto.randomUUID()}`;
    if (this.pending.has(id) || this.pending.size >= 128) throw new Error('VOICE_CONTROL_REQUEST_IN_FLIGHT');
    return new Promise((accept, reject) => {
      const finish = () => { clearTimeout(timer); options.signal?.removeEventListener('abort', abort); this.pending.delete(id); };
      const abort = () => { finish(); reject(new Error('VOICE_CONTROL_REQUEST_ABORTED')); };
      const timer = setTimeout(() => { finish(); reject(new Error('VOICE_CONTROL_REQUEST_TIMEOUT')); }, options.timeoutMs ?? 30_000);
      if (options.signal?.aborted) { abort(); return; }
      options.signal?.addEventListener('abort', abort, { once: true });
      this.pending.set(id, { accept: value => { finish(); accept(value); }, reject: error => { finish(); reject(error); } });
      try { this.socket.send(JSON.stringify({ type: 'req', id, method, params })); }
      catch (error) { finish(); reject(error); }
    });
  };

  close(): void {
    this.closed = true;
    this.socket.close();
  }
}
