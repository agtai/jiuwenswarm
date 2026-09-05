import { iterateTtsText } from './ttsText';

/** One in-flight chunk, no eager synthesis queue; a new play invalidates the old run. */
export class TtsPlaybackQueue {
  private controller: AbortController | null = null;

  stop(): void {
    this.controller?.abort();
    this.controller = null;
  }

  async play(
    text: string,
    playChunk: (chunk: string, signal: AbortSignal) => Promise<boolean>,
    isCurrent: () => boolean = () => true
  ): Promise<boolean> {
    this.stop();
    const controller = new AbortController();
    this.controller = controller;
    try {
      for (const chunk of iterateTtsText(text)) {
        if (controller.signal.aborted || !isCurrent()) return false;
        if (!(await playChunk(chunk, controller.signal))) return false;
      }
      return !controller.signal.aborted && isCurrent();
    } catch (error) {
      // Provider/browser failures settle the run and never enqueue a suffix.
      console.warn('TTS playback failed:', error);
      return false;
    } finally {
      if (this.controller === controller) this.controller = null;
    }
  }
}
