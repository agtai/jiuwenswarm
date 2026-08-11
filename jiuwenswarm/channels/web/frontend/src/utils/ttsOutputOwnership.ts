/**
 * Process-local ownership for mutually exclusive TTS playback paths.
 *
 * Live Voice uses browser SpeechSynthesis while the legacy chat path may fetch
 * generated audio from tts.synthesize. A token set keeps stale React cleanup
 * from releasing a newer owner and lets the legacy path fence both request
 * start and an in-flight response.
 */

const liveVoiceOwners = new Set<symbol>();
let ownershipRevision = 0;

export type ServerTtsOutputTicket = number;

export function acquireLiveVoiceTtsOutputOwnership(): () => void {
  const token = Symbol('live-voice-tts-output-owner');
  // Invalidate every server synthesis that started before this acquisition.
  // Releasing ownership must not make one of those old responses playable.
  ownershipRevision += 1;
  liveVoiceOwners.add(token);
  let released = false;

  return () => {
    if (released) return;
    released = true;
    liveVoiceOwners.delete(token);
  };
}

export function isLiveVoiceTtsOutputOwned(): boolean {
  return liveVoiceOwners.size > 0;
}

export function beginServerTtsOutput(): ServerTtsOutputTicket | null {
  return isLiveVoiceTtsOutputOwned() ? null : ownershipRevision;
}

export function canCompleteServerTtsOutput(ticket: ServerTtsOutputTicket): boolean {
  return liveVoiceOwners.size === 0 && ticket === ownershipRevision;
}
