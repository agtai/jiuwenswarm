# Live Voice latency development experiments: 2026-08-20

## Conclusion

- Execution status: **PRELIMINARY DEVELOPMENT DIAGNOSTIC — NOT AN ACCEPTED
  BASELINE**.
- The work established a usable stage vocabulary, implemented and reviewed the
  minimal latency probe, repaired a real Windows-Chrome-to-WSL capture defect,
  built a local supervised harness, and obtained seven coarse Browser-clock
  voice timelines.
- The measured run cannot receive baseline credit. Product source was dirty,
  the run manifest does not describe the actual Browser/input method, and the
  run directory contains no formal Browser/Gateway/Agent JSONL shards.
- The observations are nevertheless sufficient to select the next experimental
  method and working hypotheses. Capture/endpointing must be optimized and
  validated separately from the post-capture pipeline. The post-capture path
  should become the primary automated A/B loop, while Controlled Browser and
  physical runs remain required for capture, playout and final validation.
- The first optimization focus is Live Voice-owned latency rather than
  Agent-Core/model tuning: capture/EOT, recognition settlement, admission,
  presentation/TTS orchestration, successor-capture/downlink coupling, Browser
  startup buffering, playout and ACK.

This record is evidence for the exact development exercise below. It does not
replace the current judgement in [STATUS](../STATUS.md), the measurement
contract in the
[latency probe specification](../roadmap/FULL_LATENCY_PROBE_SPEC_2026-08-19.md),
or the optimization order in the
[latency optimization plan](../roadmap/LATENCY_OPTIMIZATION_PLAN_2026-08-18.md).

## 1. Source and runtime provenance

| Item | Sanitized fact |
|---|---|
| branch | `0812_live_voice_w3_renan` |
| Hongxing comparison ref | `agtai/hx/0812_live_voice_w3` |
| observed HEAD | `38d09aefec117f16fbeaafa7d47244d67acf644d` |
| run ID | `lv-diag-wsl-en-v1-20260820T140927Z-38d09aefe` |
| source state | `product_code_dirty` |
| Gateway/Agent runtime | WSL2, Python 3.11.15 |
| actual Browser path | Windows Chrome accessing the WSL-hosted Web application |
| actual input | human speech through the Windows Browser microphone path |
| declared STT | OpenAI `gpt-4o-mini-transcribe-2025-12-15` |
| declared TTS | OpenAI `gpt-4o-mini-tts-2025-12-15`, voice `marin` |
| declared VAD | OpenAI server VAD, 1,200 ms silence |
| declared playout lead | WebAudio, 1,000 ms |

Provider credentials, bearer values, endpoints, raw audio, Browser device
identifiers and private configuration remain outside Git and this record.

### 1.1 Manifest incompatibility

The retained `run.json` says:

- `Linux Chrome under WSLg with WSL2 backends`;
- `Ubuntu 24.04 WSLg` as the Browser OS class;
- fixed PCM/WAV input;
- five predefined corpus/profile cases.

The measured turns instead used Windows Chrome, a real microphone and ad-hoc
English prompts. The manifest therefore cannot bind these observations into a
formal compatible population. It is retained as evidence of the harness state,
not treated as truthful run metadata for the manual exercise.

### 1.2 Missing formal probe population

The run directory contains `run.json` but no `browser.jsonl`, `gateway.jsonl`,
`agent.jsonl`, reduced report or comparison output. Browser WebSocket logs also
showed no usable run-bound latency context on the manual turns. Consequently:

- the numbers below are reconstructed from Browser-observed RPC and
  notification timestamps;
- no cross-process subtraction is performed;
- missing internal boundaries remain unavailable rather than inferred;
- there is no sample population, p50, p95 or accepted warm/cold baseline;
- the result cannot be compared by the formal reducer/CLI contract.

## 2. Work completed before the measurement

### 2.1 Windows Chrome / WSL capture diagnosis and repair

The first physical path repeatedly failed with
`AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED`, `AUDIO_INPUT_GAP_EXCEEDED`,
`AUDIO_CAPTURE_NO_FRAMES` and `AUDIO_INPUT_NOT_FOUND`.

Temporary Browser diagnostics established that Chrome was delivering real
128-sample input quanta, but `AudioWorklet` render-frame jumps were being
interpreted as lost microphone samples. A representative observation had a
48 kHz track/context, non-empty input, a 128-sample quantum and a 15,360-sample
calculated gap. Another run showed a 44.1 kHz AudioContext with a 48 kHz track,
which also exercised the sample-rate-sensitive recovery limits.

The local branch separated the diagnostic instrumentation from the product fix:

| Commit | Purpose |
|---|---|
| `50c85bc41` | add bounded media-transport/capture diagnostics |
| `ec78c3d55` | stabilize Chrome capture across the WSL deployment |

The repair stopped treating discontinuous render-frame scheduling as proof that
real input samples were missing, while retaining actual empty-input and rolling
gap protection. This enabled the later real-microphone turns. It does not prove
a Browser/device compatibility matrix.

### 2.2 Minimal correlated latency probe

The implementation then added:

- a closed default-off event/batch/run contract;
- bounded Browser, Gateway and Agent recorders;
- durable JSONL collection with idempotency/conflict rules;
- deterministic reduction, reports and baseline/candidate comparison;
- Browser round ownership and post-terminal export;
- Gateway STT/TTS/media instrumentation;
- Agent commit, route, Tool, final and presentation instrumentation;
- Browser capture, submit, TTS, playout, ACK and successor-capture boundaries;
- asynchronous off-path exporters and clean-stop drain hooks;
- independent Tier-3 review and remediation.

The coherent local commit sequence is recorded in Appendix A. The probe's
automation/review result is implementation evidence; it does not compensate for
the absent shards in this physical run.

### 2.3 Local harness and corpus preparation

A private development harness outside the repository was created to:

- generate run IDs and per-run directories;
- create and validate `run.json`;
- start Web, Gateway and Agent services in `tmux`;
- apply Live Voice feature flags and an isolated P3 database;
- support fixed-WAV and manual-microphone modes;
- print the exact phrase/profile expected for a supervised attempt;
- retain service logs and inspect run progress;
- prepare for later baseline/candidate worktree comparison.

The English corpus was converted from private Android `.m4a` recordings into
declared WAV/PCM artifacts outside Git. Automated fake-media attempts were not
stable enough for a baseline: Chrome activation sometimes yielded no frames,
the first activation often needed a retry, audio timing raced capture readiness,
and injected audio could be replaced by or mixed with the wrong fixture. The
experiment therefore moved to supervised Windows Chrome plus real microphone.

The future A/B idea was retained in the
[fixed-audio benchmark draft](../roadmap/FIXED_AUDIO_LATENCY_BENCHMARK_DRAFT_2026-08-19.md),
not claimed as completed harness functionality.

## 3. Runtime preparation and product-path findings

### 3.1 Formal route startup

Initial startup failed closed because enabled product composition did not have
authenticated P3 authority. Disabling product composition would have bypassed
the intended route and was rejected as a valid benchmark setup. The local
harness was corrected to use a per-run database below the application-owned P3
directory. A later startup reported authenticated P3 readiness and registered
P1/P2/P3 product composition.

This environment repair was made in the external local harness and is not part
of the repository commit history.

### 3.2 Task route failure

The spoken Task-create/cancel experiment did not create an authoritative P3
Task. The P3 SQLite `tasks` table remained empty. On cancellation, the Agent
attempted a `bash` process inspection; permission resolved to `ask`, execution
was interrupted, and the formal Tool stream raised
`FORMAL_TOOL_EVENT_SEQUENCE_INVALID`, surfaced as
`PRODUCT_AGENT_OUTPUT_FAILED`.

This was not an STT, TTS or OpenAI transport failure. It invalidated the Task
attempts and contaminated the continuing conversation context.

### 3.3 Session contamination and acoustic feedback

Session `web_1a01f778cc4_d99fbfdbc7c6` later reused the failed Task context.
The system answered a simple exercise prompt with the previous cancellation
answer, captured `Tamam.` as a successor turn and repeatedly emitted barge-in.
That session was retired.

A new saved Code session, `web_1a01f90a800_6bdedf242da2`, restored isolated
dialogue behavior. Operators still had to stop Live Voice after complete
playout to avoid successor capture admitting room speech or rendered audio.

### 3.4 Observed failure inventory

| Symptom / reason | Observed boundary | Disposition |
|---|---|---|
| `enabled product composition requires authenticated P3 authority` | product-composition startup | environment/configuration failure; corrected without disabling the formal product route |
| `Requires Agent mode + compatible browser` | Web availability gate | session/project/mode and Browser runtime had to be reconciled before product activation |
| `AUDIO_CAPTURE_MEDIA_NOT_ACKNOWLEDGED` | Browser capture → media authority | early media ownership/receipt failure; diagnostic precursor to the WSL capture repair |
| `AUDIO_CAPTURE_NO_FRAMES` | Browser capture | first activation sometimes produced no usable frames during fake-audio attempts |
| `AUDIO_INPUT_NOT_FOUND` | Browser capture | selected fake/virtual input was unavailable to the active Browser path |
| `AUDIO_INPUT_GAP_EXCEEDED` | AudioWorklet/Browser adapter | false gap inference from render-frame discontinuity; repaired for real non-empty input while keeping genuine gap protection |
| `PAGE_HIDDEN_PLAYOUT_FENCED` | Browser playout | page visibility fence correctly prevented an untrustworthy playout claim; attempt not usable |
| `STREAMING_SPEECH_PROVIDER_PROTOCOL` / timeout fallback | streaming recognition cleanup | observed after interrupted/barge-in media lifecycles; retained as degraded/failure evidence |
| `FORMAL_TOOL_EVENT_SEQUENCE_INVALID` / `PRODUCT_AGENT_OUTPUT_FAILED` | Agent Tool stream | permission-interrupted `bash` call invalidated the Task-control attempt |
| repeated barge-in / successor transcription | Conversation Runtime | microphone or rendered/room speech opened unintended turns; affected sessions were retired or attempts excluded |
| wrong corpus/prompt selected | supervised fake-audio harness | input identity was not trustworthy enough for a fixed-corpus baseline |
| missing formal JSONL shards | probe export/run binding | prevents reducer, p50/p95 and baseline/candidate comparison credit |

Some fences above are correct fail-closed product behavior rather than product
defects. They still remain in the experiment denominator because they determine
whether a benchmark method is operationally usable.

## 4. Spoken inputs and disposition

### 4.1 Timed A–G turns

| ID | Browser-recognized input | Session | Disposition |
|---|---|---|---|
| A | `In two short sentences, please introduce Paris.` | prior session | valid no-Tool dialogue |
| B | `What's the weather today in Paris?` | prior session | valid Tool/external-information dialogue |
| C | `Can you search the best restaurants in Paris?` | new session | valid long Tool/external-information dialogue |
| D | `Please check today's weather in London and answer in exactly two short sentences.` | new session | valid bounded weather response |
| E | `Please search for two exhibitions currently open in Paris and summarize them in exactly two short sentences.` | new session | valid bounded external-information response |
| F | `An exactly true short synthesis explaining why the sky appears blue.` | new session | pipeline completed; intended wording was not preserved by STT |
| G | `Please search for two highly hated museums in Paris and answer with only their names.` | new session | semantic STT failure; intended `highly rated` became `highly hated` |

F and G remain in the diagnostic denominator but are not semantic baseline
successes. G also caused a long corrective response instead of the requested
two names, demonstrating why prompt identity and semantic correctness must gate
latency comparisons.

### 4.2 Other submitted turns excluded from A–G

| Input or event | Reason for exclusion |
|---|---|
| `What is the weather today?` | underspecified location; completed without the intended external lookup |
| `Can you check on your website what is the weather today?` | underspecified location; Agent requested location |
| itinerary Task create | no authoritative Task created |
| `Cancel the background task you just created.` | failed with the formal Tool sequence defect |
| Korean `어` | unintended successor capture |
| exercise explanation in the contaminated session | answered from stale cancellation context |
| `Tamam.` | unintended room/feedback capture |

These events are correctness and run-health evidence. Discarding them silently
would make a later latency population look healthier than the product behavior.

## 5. Browser-clock stage reconstruction

All values are milliseconds. A and B came from the retired first session; C–G
came from the replacement session. The rows use one Browser clock and do not
subtract Gateway or Agent monotonic clocks.

| Stage | Block | A — Paris | B — Paris weather | C — Restaurants | D — London weather | E — Exhibitions | F — Sky | G — Museums |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Capture ready → EOT/STT requested | P1/P2 | 5,520 | 8,437 | 5,616 | 10,656 | 11,928 | 7,151 | 11,470 |
| STT finalization RPC | P1 | 516 | 829 | 415 | 826 | 726 | 411 | 442 |
| STT final → `unified.submit` | P2 | 44 | 42 | 0 | 0 | 44 | 0 | −41 |
| Commit and round admission | P2 | 508 | 520 | 849 | 444 | 436 | 610 | 529 |
| Round accepted → first Agent text | Agent/Tools | 1,812 | 5,566 | 5,527 | 1,319 | 6,504 | 532 | 5,188 |
| First Agent text → final response | Agent streaming | 3,348 | 4,549 | 9,055 | 2,017 | 3,696 | 4,056 | 5,340 |
| Final response → TTS request | Presentation handoff | 16 | 16 | 68 | 20 | 16 | 16 | 16 |
| Batch TTS generation | P1/TTS | 1,672 | 935 | 1,200 | 912 | 1,241 | 964 | 1,120 |
| TTS ready → playout completion/ACK | P1/Browser | 1,672 | 1,581 | 8,028 | 8,877 | 1,780 | 13,137 | 8,319 |
| ACK processing | P2 | 244 | 132 | 92 | 43 | 164 | 80 | 129 |
| **EOT → confirmed ACK** | **Code E2E** | **9,832** | **14,170** | **25,234** | **14,458** | **14,607** | **19,806** | **21,042** |
| Capture ready → confirmed ACK | Full experience | 15,352 | 22,607 | 30,850 | 25,114 | 26,535 | 26,957 | 32,512 |

The −41 ms value on G is an observed asynchronous overlap: the Browser emitted
`unified.submit` before the recognition RPC response was observed. It is not
negative processing time.

### 5.1 Boundary limitations

- `Capture ready → EOT/STT requested` includes speech duration, pauses, server
  VAD and, in continuous mode, time for which successor capture was ready before
  the user began speaking. It is not a pure code-latency segment.
- `TTS ready → playout completion/ACK` combines audio downlink, Browser
  scheduling and the complete duration of rendered speech. It is not
  time-to-first-audio. Long responses inflate it legitimately.
- The first visible Agent text is a Browser notification boundary, not a
  substitute for detailed Agent/Tool spans.
- F and G demonstrate that low latency without semantic input correctness is
  not a success.

## 6. Quantitative findings

### 6.1 Capture and endpointing

The coarse capture segment ranged from 5.5 to 11.9 seconds. Most of that range
is explained by utterance duration, pauses, successor-capture timing and the
1,200 ms VAD policy. These samples cannot decide a VAD optimization because
speech-end was not externally marked and the prompts differ in duration.

Capture/endpointing remains a high-value optimization area, but it needs a
fixed audio corpus with a reviewed speech-end sample and separate quality
guardrails. It cannot share its distribution with manual ad-hoc speech.

### 6.2 STT finalization and admission

- STT finalization was comparatively stable at 411–829 ms.
- STT-final-to-submit was 0–44 ms, with one 41 ms asynchronous overlap.
- Commit/round admission was 436–849 ms.

These are smaller than the Agent and full-playout intervals, but STT settlement
and admission are Live Voice-owned and repeatable enough to benchmark in an
automated post-capture lane.

### 6.3 Agent and Tool time

- Round-accepted-to-first-text ranged from 532 ms to 6,504 ms.
- First-text-to-final ranged from 2,017 ms to 9,055 ms.
- Tool/external-information prompts generally delayed first text by roughly
  5–6.5 seconds.

Agent-Core, model and Tool optimization are not the first target of the next
batch. Their time must still be measured and controlled because it affects the
downstream input. A fixed response/PresentationUnit fixture may be used for a
declared Live Voice-only profile, but it cannot be relabeled as real-Agent E2E.

The product-level wait for complete `chat.final` before requesting TTS remains a
Live Voice orchestration concern even though the text is generated by the
Agent. The existing optimization plan owns the later authoritative
sentence-level overlap decision.

### 6.4 Presentation, TTS, downlink and playout

- Final-response-to-TTS handoff was only 16–68 ms.
- Batch TTS generation was 912–1,672 ms.
- TTS-ready-to-full-playout/ACK ranged from 1,581 to 13,137 ms.
- ACK processing was 43–244 ms.

The large post-TTS range is dominated by response length and full playout, not
proven startup wait. It identifies the output path as important but does not
justify reducing a buffer or queue without first-audio, underrun and rebuffer
measurements. The fixed one-second WebAudio lead, downlink gating and successor
capture readiness remain concrete code hypotheses from the optimization plan.

### 6.5 Preliminary ranking

For Live Voice-owned work, the next investigation order is:

1. restore a truthful formal measurement run and first-audio boundaries;
2. automate the post-capture pipeline for fast A/B/A comparisons;
3. isolate Browser startup buffer, first frame and playout health;
4. measure and remove any downlink wait on successor-capture readiness;
5. overlap recognition final retrieval with local EOT/uplink settlement;
6. evaluate VAD only in the separate capture/endpointing track;
7. revisit sentence-level Agent-to-TTS overlap after the lower-risk pipeline
   evidence is repeatable.

## 7. Accepted experimental split

The next optimization work uses two disjoint primary tracks.

### 7.1 Track 1 — capture and endpointing

```text
Capture ready → EOT/STT requested
```

This track includes the real Browser/device path, AudioWorklet, uplink and
VAD/EOT decision. It requires Controlled Browser or physical input and reports
latency together with false-EOT, missed-EOT, truncation, recognition quality,
capture gaps and recovery outcomes.

It is the only primary track that requires audio to enter through the supported
Web capture surface. A direct Gateway PCM test may diagnose a server/media
substage, but it does not replace Browser capture evidence.

### 7.2 Track 2 — pipeline excluding capture

```text
EOT/STT requested
    → STT finalization
    → committed-input admission and routing
    → Agent/Task execution
    → PresentationUnit handoff
    → TTS
    → audio downlink and Browser playout
    → authoritative ACK
```

The primary optimization loop should automate this track without microphone
operation or manual UI steps. The intended seam is a run-bound deterministic
recognition-finalization operation that preserves the real downstream product
owners. If that exact seam cannot be instantiated without weakening production
authority, an explicitly separate `post_stt_pipeline` profile begins at
`unified.submit`; it must not claim STT-finalization coverage.

For Live Voice-only experiments, transcript, Agent/Tool result or
PresentationUnit input may be held deterministic under an explicit fixture
profile. Real-Agent and deterministic-response samples remain separate.

### 7.3 No pooling and no substitution

- Track 1 and Track 2 samples are never pooled.
- Deterministic, Controlled Browser and physical lanes remain distinct.
- Browser scheduled/estimated audio is not physical first audible.
- A deterministic Agent/Presentation fixture is not real-Agent latency.
- Pipeline automation does not grant capture, device or acoustic quality
  credit.
- A manual physical success does not grant a repeatable A/B population.

## 8. Next A/B loop

The A–G tables in this record are historical hypothesis evidence, not A1. They
may be used to check whether a new clean baseline reproduces the same broad
bottleneck direction, but they must not be pooled with the fixed-WAV runner or
used to calculate an old→new percentage. Hongxing's retained optimization
findings have the same role until the new runner confirms them. During A1
analysis, classify every historical/Hongxing hypothesis as `confirmed`,
`partially_confirmed`, `not_reproduced`, `not_yet_measured`, or
`methodologically_incompatible`.

Each optimization receives its own clean candidate worktree and one named
change. The loop is:

```text
reviewed clean reference and smoke
    → automated Track 2 baseline A1
    → rank A1 plus historical/Hongxing hypotheses
    → apply one Live Voice optimization B in one worktree
    → compatible automated Track 2 candidate B
    → unchanged-reference baseline A2
    → stage-by-stage, total, denominator and drift comparison
    → Controlled Browser verification for affected Browser/output seams
    → physical Track 1 or full-journey verification when required
```

The runner must freeze source/dependency identities, run profile, transcript or
corpus case, Provider/model classes, response fixture class, VAD, playout,
network, cold/warm policy and private-state template. Failures, semantic
mismatches, fallbacks and degradations stay in the denominator.

An optimization is accepted only if the intended Live Voice stage improves,
the wait is not displaced downstream, correctness and forbidden-effect checks
remain closed, and the delta exceeds run variability. Until that loop produces
a compatible clean-source population, the measurements in this record remain
hypothesis evidence only.

## Appendix A — local branch commit sequence

Relative to `agtai/hx/0812_live_voice_w3`, the observed non-merge sequence was:

```text
50c85bc41 chore(live-voice): add safe media transport diagnostics
ec78c3d55 fix(live-voice): stabilize Chrome capture across WSL
62605dd10 docs(live-voice): define minimal latency probe
a9cbc0462 docs(live-voice): plan minimal latency probe implementation
0a6587c78 feat(live-voice): add minimal latency probe contract
edc224e13 fix(live-voice): harden latency probe isolation
ab1295102 fix(live-voice): close latency probe producer contract
d724f8d6c fix(live-voice): close gateway probe mode
c0e7532cf fix(live-voice): accept generated urlsafe probe ids
69568089e feat(live-voice): add latency baseline reducer
f1d70d147 fix(live-voice): close latency report semantics
85a3225fb fix(live-voice): close latency comparison catalogs
c074a1d77 feat(live-voice): accept browser latency batches
744cf4b18 fix(live-voice): bind latency batches to dispatcher sessions
9c40d1c0e fix(live-voice): confirm latency batch enqueue
d05c90161 feat(live-voice): add browser latency recorder
bd037be75 fix(live-voice): harden browser latency recorder
da7fe08ee feat(live-voice): measure browser voice rounds
8f61bc23b fix(live-voice): align browser latency boundaries
fd57bfb31 fix(live-voice): measure exact transport boundaries
f5e167923 feat(live-voice): measure gateway speech stages
a1b0435da feat(live-voice): measure foreground agent stages
7c2739a0d docs(live-voice): document latency baseline procedure
edbee4d3d feat(live-voice): add reviewed latency baseline probe
38d09aefe fix(live-voice): defer successor capture until presentation
```

This list records local implementation history. It is not a statement that the
current dirty working tree equals any one clean tested candidate, and it does
not authorize a remote-ref update.
