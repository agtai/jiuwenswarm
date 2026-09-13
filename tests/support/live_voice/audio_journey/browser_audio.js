/* Test-only digital microphone and output observation. Never imported by Web.
 * This substitutes a browser MediaStream source, not transcript/TurnCommit/RPC.
 * Real AudioIO capture, Gateway, STT, semantics, Agent/Task and playout remain.
 */
(() => {
  const NativeContext = window.AudioContext;
  const inputContexts = new WeakSet();
  const destinations = new Set();
  const events = [];
  const documentId = crypto.randomUUID();
  let sequence = 0, retainedBytes = 0, currentInput = null;
  const maxBytes = 64 * 1024 * 1024;
  const note = event => events.push({ sequence: ++sequence, document_id: documentId, at: performance.now(), ...event });
  // Observe only incoming content-free media lifecycle controls. Never retain
  // auth tickets, speech receipts, raw microphone frames or arbitrary RPC data.
  const NativeSocket = window.WebSocket;
  window.WebSocket = class extends NativeSocket {
    constructor(...args) {
      super(...args);
      if (new URL(String(args[0]), location.href).pathname !== '/ws/live-voice/media') return;
      this.addEventListener('message', event => {
        if (typeof event.data !== 'string') return;
        let control;
        try { control = JSON.parse(event.data); } catch { return; }
        if (!['media.attach', 'media.speech_start', 'media.end_of_turn', 'media.detach', 'media.reject'].includes(control.type)) return;
        note({kind:'media-boundary', type:control.type, lease_id:control.lease_id ?? control.binding?.lease_id,
          generation:control.generation ?? control.binding?.generation, reason_id:control.reason_id});
      });
    }
  };
  const makeSource = NativeContext.prototype.createBufferSource;
  NativeContext.prototype.createBufferSource = function(...args) {
    const context = this;
    const source = makeSource.apply(context, args);
    if (inputContexts.has(context)) return source;
    const nativeStart = source.start.bind(source);
    const nativeStop = source.stop.bind(source);
    let started = null;
    const id = `output-${documentId}-${++sequence}`;
    source.start = (...startArgs) => {
      const buffer = source.buffer;
      if (buffer) {
        const pcm = new Int16Array(buffer.length);
        let energy = 0;
        for (let i = 0; i < buffer.length; i++) {
          let value = 0;
          for (let ch = 0; ch < buffer.numberOfChannels; ch++) value += buffer.getChannelData(ch)[i];
          value = Math.max(-1, Math.min(1, value / buffer.numberOfChannels));
          pcm[i] = Math.round(value * 32767); energy += value * value;
        }
        if (energy === 0) {
          // Browser output warm-up/keepalive is not audible response evidence.
          // Keep its lifecycle, but do not exhaust the speech recording budget.
          note({kind:'silent-output-buffer', id, sample_rate:buffer.sampleRate, frames:buffer.length, rms:0});
        } else if (retainedBytes + pcm.byteLength <= maxBytes) {
          const bytes = new Uint8Array(pcm.buffer);
          let encoded = '';
          for (let offset = 0; offset < bytes.length; offset += 8192) {
            encoded += String.fromCharCode(...bytes.subarray(offset, offset + 8192));
          }
          retainedBytes += bytes.length;
          note({ kind: 'output-buffer', id, sample_rate: buffer.sampleRate, frames: buffer.length,
            rms: Math.sqrt(energy / buffer.length), pcm_s16le_base64: btoa(encoded) });
        } else {
          note({kind:'observation-failed', id, reason:'output-buffer-bound-exceeded'});
        }
      } else note({kind:'observation-failed', id, reason:'output-buffer-missing'});
      started = { clock: context.currentTime, scheduled: startArgs[0] ?? context.currentTime };
      nativeStart(...startArgs);
      note({kind:'output-start-scheduled', id, context_state:context.state, ...started});
      setTimeout(() => {
        note({kind:'output-render-clock', id, context_state:context.state,
          clock:context.currentTime, advanced:started !== null && context.currentTime > started.scheduled});
      }, 100);
    };
    source.stop = (...args) => {
      note({kind:'output-stop', id, clock:context.currentTime});
      return nativeStop(...args);
    };
    source.addEventListener('ended', () => note({kind:'output-ended',id,clock:context.currentTime}));
    return source;
  };
  const realGetUserMedia = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async constraints => {
    if (!constraints?.audio || constraints?.video) return realGetUserMedia(constraints);
    const context = new NativeContext({sampleRate:24000});
    inputContexts.add(context);
    const destination = context.createMediaStreamDestination();
    const entry = {context, destination, openedAt:performance.now()};
    destinations.add(entry);
    await context.resume();
    note({kind:'capture-opened', sample_rate:context.sampleRate, tracks:destination.stream.getAudioTracks().length});
    for (const track of destination.stream.getTracks()) {
      const stop = track.stop.bind(track);
      track.stop = () => {
        stop(); destinations.delete(entry); void context.close();
        note({kind:'capture-stopped', remaining:destinations.size});
      };
    }
    return destination.stream;
  };
  window.__semanticAudioTest = {
    snapshot: () => ({captures:destinations.size, input:currentInput, pending_events:events.length,
      capture_age_ms:destinations.size === 1 ? performance.now()-[...destinations][0].openedAt : null}),
    drain: () => events.splice(0, 512),
    async play(base64, sampleId) {
      if (currentInput !== null || destinations.size !== 1) throw new Error('requires exactly one live capture, no overlapping input');
      const bytes = Uint8Array.from(atob(base64), c => c.charCodeAt(0));
      const entry = [...destinations][0];
      const buffer = await entry.context.decodeAudioData(bytes.buffer);
      const source = entry.context.createBufferSource(); source.buffer = buffer;
      source.connect(entry.destination);
      currentInput = sampleId;
      note({kind:'input-start',sample_id:sampleId,frames:buffer.length,sample_rate:buffer.sampleRate});
      source.addEventListener('ended', () => {
        currentInput = null; source.disconnect();
        note({kind:'input-ended',sample_id:sampleId});
      });
      source.start();
      return {duration:buffer.duration};
    }
  };
})();
