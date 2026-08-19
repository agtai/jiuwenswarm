const MAX_TRANSIENT_INPUT_GAP_MS = 15;
const INPUT_GAP_WINDOW_MS = 1000;
const MAX_INPUT_GAP_PER_WINDOW_MS = 60;
const MAX_STARTUP_REBASE_MS = 500;
const MAX_CONSECUTIVE_DUPLICATE_RENDER_BLOCKS = 8;

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
    this.maxTransientInputGapSamples = this.validConfiguration ? Math.floor((sampleRate * MAX_TRANSIENT_INPUT_GAP_MS) / 1000) : 0;
    this.inputGapWindowSamples = this.validConfiguration ? Math.floor((sampleRate * INPUT_GAP_WINDOW_MS) / 1000) : 0;
    this.maxInputGapPerWindowSamples = this.validConfiguration ? Math.floor((sampleRate * MAX_INPUT_GAP_PER_WINDOW_MS) / 1000) : 0;
    this.maxStartupRebaseSamples = this.validConfiguration ? Math.floor((sampleRate * MAX_STARTUP_REBASE_MS) / 1000) : 0;
    this.recentInputGaps = [];
    this.recentInputGapSamples = 0;
    this.pending = new Float32Array(this.frameSamples);
    this.pendingLength = 0;
    this.pendingStartFrame = null;
    this.expectedRenderFrame = null;
    this.lastRenderFrame = null;
    this.lastInputQuantumSamples = null;
    this.initialRenderFrame = null;
    this.processCallCount = 0;
    this.lastOutputCount = 0;
    this.lastOutputChannelCount = 0;
    this.lastOutputQuantumSamples = 0;
    this.startupRebaseUsed = false;
    this.duplicateRenderFrameCount = 0;
    this.seq = 0;
    this.sampleCursor = 0;
    this.failed = false;
  }

  process(inputs, outputs = []) {
    // The capture worklet is connected to the context destination so Chrome
    // continuously pulls its render graph. Never expose microphone samples on
    // that keep-alive edge, including terminal/error callbacks.
    const keepAliveOutput = outputs[0];
    this.lastOutputCount = outputs.length;
    this.lastOutputChannelCount = keepAliveOutput?.length ?? 0;
    this.lastOutputQuantumSamples = keepAliveOutput?.[0]?.length ?? 0;
    if (keepAliveOutput) {
      for (const channel of keepAliveOutput) channel?.fill(0);
    }
    this.processCallCount += 1;
    if (this.failed) return false;
    if (!this.validConfiguration) {
      this.port.postMessage({ kind: 'error', reason: 'invalid_frame_configuration' });
      this.failed = true;
      return false;
    }
    const channels = inputs[0];
    const inputQuantumSamples = channels && channels.length > 0 && channels[0] ? channels[0].length : 0;
    const inputEmpty = inputQuantumSamples === 0;
    const previousInputQuantumSamples = this.lastInputQuantumSamples;
    this.lastInputQuantumSamples = inputQuantumSamples;
    const renderFrame = currentFrame;
    if (this.initialRenderFrame === null && Number.isSafeInteger(renderFrame) && renderFrame >= 0) {
      this.initialRenderFrame = renderFrame;
    }
    if (!Number.isSafeInteger(renderFrame) || renderFrame < 0 || (this.lastRenderFrame !== null && renderFrame < this.lastRenderFrame)) {
      this.port.postMessage({ kind: 'error', reason: 'render_frame_regressed' });
      this.failed = true;
      return false;
    }
    const previousRenderFrame = this.lastRenderFrame;
    if (previousRenderFrame !== null && renderFrame === previousRenderFrame) {
      // The declared Chrome baseline has produced a bounded duplicate callback
      // after a complete duplex playout. Treat the same timeline interval as a
      // replay, not new microphone authority. A short watchdog still rejects a
      // processor that never advances at all.
      this.duplicateRenderFrameCount += 1;
      if (this.duplicateRenderFrameCount > MAX_CONSECUTIVE_DUPLICATE_RENDER_BLOCKS) {
        this.port.postMessage({ kind: 'error', reason: 'render_frame_not_advanced' });
        this.failed = true;
        return false;
      }
    } else {
      this.duplicateRenderFrameCount = 0;
    }
    this.lastRenderFrame = renderFrame;
    if (this.expectedRenderFrame === null) this.expectedRenderFrame = renderFrame;
    this.pruneInputGapWindow(renderFrame);
    let missingSamples = Math.max(0, renderFrame - this.expectedRenderFrame);
    let rollingGapCandidateSamples = this.recentInputGapSamples + missingSamples;
    let singleGapExceeded = missingSamples > this.maxTransientInputGapSamples;
    let rollingBudgetExceeded = rollingGapCandidateSamples > this.maxInputGapPerWindowSamples;
    const startupElapsedSamples = this.initialRenderFrame === null ? this.maxStartupRebaseSamples + 1 : renderFrame - this.initialRenderFrame;
    if (
      singleGapExceeded &&
      !inputEmpty &&
      this.seq === 0 &&
      !this.startupRebaseUsed &&
      startupElapsedSamples <= this.maxStartupRebaseSamples
    ) {
      // Chrome/Windows can reconfigure its audio device immediately after the
      // capture graph becomes live, advancing the shared render clock before a
      // second Worklet callback. No PCM frame has acquired browser or media
      // authority yet, so discard the unpublished prefix and start the input
      // timeline at the recovered real quantum. This one-shot bounded startup
      // rebase never synthesizes silence and cannot weaken post-frame gap bounds.
      this.startupRebaseUsed = true;
      this.recentInputGaps = [];
      this.recentInputGapSamples = 0;
      this.pending = new Float32Array(this.frameSamples);
      this.pendingLength = 0;
      this.pendingStartFrame = null;
      this.expectedRenderFrame = renderFrame;
      missingSamples = 0;
      rollingGapCandidateSamples = 0;
      singleGapExceeded = false;
      rollingBudgetExceeded = false;
    }
    if (singleGapExceeded || rollingBudgetExceeded) {
      this.port.postMessage({
        kind: 'error',
        reason: 'input_gap_exceeded',
        diagnostic: {
          trigger: singleGapExceeded && rollingBudgetExceeded ? 'single_and_rolling' : singleGapExceeded ? 'single_gap' : 'rolling_budget',
          single_gap_exceeded: singleGapExceeded,
          rolling_budget_exceeded: rollingBudgetExceeded,
          missing_samples: missingSamples,
          recent_gap_samples: this.recentInputGapSamples,
          rolling_gap_candidate_samples: rollingGapCandidateSamples,
          max_transient_gap_samples: this.maxTransientInputGapSamples,
          max_rolling_gap_samples: this.maxInputGapPerWindowSamples,
          render_frame: renderFrame,
          expected_render_frame: this.expectedRenderFrame,
          render_delta_samples: previousRenderFrame === null ? null : renderFrame - previousRenderFrame,
          input_quantum_samples: inputQuantumSamples,
          previous_input_quantum_samples: previousInputQuantumSamples,
          input_empty: inputEmpty,
          context_sample_rate_hz: sampleRate,
          process_call_count: this.processCallCount,
          initial_render_frame: this.initialRenderFrame,
          emitted_frame_count: this.seq,
          sample_cursor: this.sampleCursor,
          output_count: this.lastOutputCount,
          output_channel_count: this.lastOutputChannelCount,
          output_quantum_samples: this.lastOutputQuantumSamples,
        },
      });
      this.failed = true;
      return false;
    }
    // Web Audio permits an empty input for a render quantum. Wait for a real
    // input before materializing the bounded interval as silence so capture
    // readiness can never be satisfied by an indefinitely disconnected input.
    if (inputEmpty) return true;

    const quantumLength = inputQuantumSamples;
    const overlapSamples = Math.max(0, this.expectedRenderFrame - renderFrame);
    // A conforming AudioWorklet advances currentFrame by one fixed render
    // quantum. Keep this first-writer-wins branch as deterministic compatibility for
    // an observed UA/device anomaly where a monotonic callback overlapped an
    // already-consumed interval. Only an actual currentFrame regression above
    // is terminal; the duplicate prefix must not become duplicate microphone
    // input or synthetic readiness.
    if (overlapSamples >= quantumLength) return true;
    if (missingSamples > 0) {
      this.recentInputGaps.push({
        startFrame: this.expectedRenderFrame,
        endFrame: renderFrame,
      });
      this.recentInputGapSamples += missingSamples;
      this.appendSamples(null, this.expectedRenderFrame, missingSamples);
    }
    const inputStartFrame = renderFrame + overlapSamples;
    const inputSampleCount = quantumLength - overlapSamples;
    this.expectedRenderFrame = Math.max(this.expectedRenderFrame, renderFrame + quantumLength);
    this.appendSamples(channels, inputStartFrame, inputSampleCount, overlapSamples);
    return true;
  }

  pruneInputGapWindow(renderFrame) {
    const cutoff = renderFrame - this.inputGapWindowSamples;
    while (this.recentInputGaps.length > 0) {
      const gap = this.recentInputGaps[0];
      if (gap.endFrame <= cutoff) {
        this.recentInputGapSamples -= gap.endFrame - gap.startFrame;
        this.recentInputGaps.shift();
        continue;
      }
      if (gap.startFrame < cutoff) {
        this.recentInputGapSamples -= cutoff - gap.startFrame;
        gap.startFrame = cutoff;
      }
      break;
    }
  }

  appendSamples(channels, startFrame, sampleCount, channelOffset = 0) {
    for (let offset = 0; offset < sampleCount; offset += 1) {
      if (this.pendingLength === 0) this.pendingStartFrame = startFrame + offset;
      let mixed = 0;
      if (channels !== null) {
        for (const channel of channels) mixed += channel[channelOffset + offset] ?? 0;
        mixed /= channels.length;
      }
      this.pending[this.pendingLength] = mixed;
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
  }
}

registerProcessor('jiuwenswarm-live-voice-capture-v1', JiuwenSwarmLiveVoiceCaptureProcessor);
