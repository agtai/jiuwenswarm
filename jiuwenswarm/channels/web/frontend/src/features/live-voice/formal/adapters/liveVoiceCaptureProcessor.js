class JiuwenSwarmLiveVoiceCaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const processorOptions = options?.processorOptions ?? {};
    this.captureGeneration = processorOptions.captureGeneration;
    this.frameDurationMs = processorOptions.frameDurationMs;
    const frameSampleNumerator = sampleRate * this.frameDurationMs;
    this.validConfiguration =
      Number.isSafeInteger(this.captureGeneration) &&
      this.captureGeneration >= 0 &&
      this.frameDurationMs === 20 &&
      Number.isSafeInteger(sampleRate) &&
      sampleRate > 0 &&
      Number.isSafeInteger(frameSampleNumerator) &&
      frameSampleNumerator % 1000 === 0;
    this.frameSamples = this.validConfiguration ? frameSampleNumerator / 1000 : 1;
    this.pending = new Float32Array(this.frameSamples);
    this.pendingLength = 0;
    this.pendingStartFrame = null;
    this.expectedRenderFrame = null;
    this.seq = 0;
    this.sampleCursor = 0;
    this.failed = false;
  }

  process(inputs) {
    if (this.failed) return false;
    if (!this.validConfiguration) {
      this.port.postMessage({ kind: 'error', reason: 'invalid_frame_configuration' });
      this.failed = true;
      return false;
    }
    const channels = inputs[0];
    if (!channels || channels.length === 0 || channels[0].length === 0) {
      this.port.postMessage({ kind: 'error', reason: 'missing_input' });
      this.failed = true;
      return false;
    }
    const quantumLength = channels[0].length;
    if (this.expectedRenderFrame !== null && currentFrame !== this.expectedRenderFrame) {
      this.port.postMessage({ kind: 'error', reason: 'render_gap' });
      this.failed = true;
      return false;
    }
    this.expectedRenderFrame = currentFrame + quantumLength;

    for (let offset = 0; offset < quantumLength; offset += 1) {
      if (this.pendingLength === 0) this.pendingStartFrame = currentFrame + offset;
      let mixed = 0;
      for (const channel of channels) mixed += channel[offset] ?? 0;
      this.pending[this.pendingLength] = mixed / channels.length;
      this.pendingLength += 1;
      if (this.pendingLength !== this.frameSamples) continue;

      const samples = this.pending;
      this.port.postMessage(
        {
          kind: 'frame',
          capture_generation: this.captureGeneration,
          seq: this.seq,
          sample_cursor: this.sampleCursor,
          context_time_s: this.pendingStartFrame / sampleRate,
          sample_rate_hz: sampleRate,
          samples,
        },
        [samples.buffer]
      );
      this.seq += 1;
      this.sampleCursor += this.frameSamples;
      this.pending = new Float32Array(this.frameSamples);
      this.pendingLength = 0;
      this.pendingStartFrame = null;
    }
    return true;
  }
}

registerProcessor('jiuwenswarm-live-voice-capture-v1', JiuwenSwarmLiveVoiceCaptureProcessor);
