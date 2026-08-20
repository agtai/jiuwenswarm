# Live Voice fixed-audio latency benchmark — discussion draft

> **Date:** 2026-08-19
> **Status:** working development methodology. The two-track optimization split
> in §2.1 and the A1/B/A2 execution loop in §5.1 were accepted for the next
> latency experiments on 2026-08-20. The controlled post-capture runner exists,
> but clean baseline execution and optimization acceptance remain open. This
> document is still not a product specification, benchmark result, or
> product-readiness claim.
> **Purpose:** provide a reproducible method for comparing the current Live
> Voice baseline with one latency optimization at a time.
> **Governing documents:** the measurement boundaries remain owned by
> [the full latency probe specification](FULL_LATENCY_PROBE_SPEC_2026-08-19.md),
> and optimization order remains owned by
> [the latency optimization plan](LATENCY_OPTIMIZATION_PLAN_2026-08-18.md).

## 1. Question and recommendation

Using the same spoken command is necessary for a trustworthy comparison, but
it is not sufficient. Provider service time, network conditions, Agent output,
Task state, Browser scheduling, audio processing and cold/warm state can all
change while the input audio remains identical.

The benchmark should therefore combine:

1. an immutable, versioned audio corpus;
2. a frozen run profile and reproducible product state;
3. repeated baseline/candidate measurements with the existing correlated
   latency probe;
4. correctness and failure guardrails in addition to latency percentiles.

The primary optimization loop is:

```text
review and freeze one clean reference
    -> smoke the measurement path
    -> measure baseline A1
    -> implement one optimization B in an isolated worktree
    -> measure candidate B
    -> re-run the unchanged reference as A2
    -> compare A1/B/A2 stages, totals, denominators and guardrails
```

This is a controlled, reproducible experiment, not a perfectly invariant one.
External Providers and real networks remain stochastic and must be handled by
repetition, compatible run profiles and explicit uncertainty.

## 2. Three complementary benchmark lanes

No single input method proves both repeatability and physical product behavior.
The benchmark should retain three separate lanes and never pool their samples.

| Lane | Audio entry point | Includes | Excludes or distorts | Intended use |
|---|---|---|---|---|
| Deterministic pipeline | Inject a run-bound deterministic fixture at the declared first boundary; this may be PCM for a media diagnostic, recognition finalization for the complete post-capture track, or authoritative committed input for an explicitly narrower post-STT profile | The real owners after the selected seam, as declared by the profile | Every earlier boundary; a later seam cannot claim coverage for the omitted Browser, capture, VAD or STT work | Fast automated A/B diagnosis and stage isolation |
| Controlled Browser | Present the exact WAV to the supported Windows Chrome as a declared virtual microphone or controlled loopback | Real Browser capture, Windows-to-WSL transport, Providers, Agent/Task, downlink and WebAudio playout | Ordinary microphone hardware and room acoustics; virtual devices may alter AEC/NS/AGC behavior | Primary repeatable end-to-end development baseline |
| Physical journey | Reproduce the same source through declared hardware into a real microphone and observe audible output | Supported human path, device behavior and acoustics | High repeatability; room and hardware add variance | Final physical validation and acceptance evidence |

The controlled Browser lane is the recommended primary comparison lane for the
current Windows Chrome plus WSL deployment. The deterministic lane explains
where a regression occurs. The physical lane proves that a measured proxy still
corresponds to the real user journey.

Browser-estimated or scheduled playout MUST NOT be relabeled as physically
audible output. If no accepted external observer measures physical first
audible, that physical headline remains unavailable as required by the probe
specification.

### 2.1 Two optimization tracks

The 2026-08-20 development exercise showed that requiring every experiment to
enter through the interactive Web microphone makes the optimization loop slow,
fragile and difficult to automate. It also showed that the coarse segment from
capture readiness to end-of-turn is dominated by input duration, VAD and
Browser/device state, while the later pipeline has different owners and can be
tested independently.

Optimization therefore uses two disjoint primary tracks:

| Track | Exact boundary | Required lane | Intended use |
|---|---|---|---|
| Capture and endpointing | `Capture ready → EOT/STT requested` | Controlled Browser or physical journey | Optimize Browser/device acquisition, AudioWorklet/uplink, VAD/EOT and capture recovery with speech-quality guardrails |
| Pipeline excluding capture | `EOT/STT requested → STT finalization → admission/routing → Agent/Task → presentation → TTS → downlink/playout → ACK` | Deterministic pipeline first, then affected Controlled Browser/physical verification | Automate the fast A/B/A loop for post-capture Live Voice changes without microphone or manual UI operation |

The split is a set subtraction, not a claim that capture no longer matters.
Track populations are reported separately and are never pooled. A change that
affects both tracks must pass each applicable track rather than use improvement
in one to hide regression in the other.

The preliminary measurements and failures that motivated this split are in the
[2026-08-20 development evidence](../evidence/LATENCY_EXPERIMENTS_2026-08-20.md).
That dirty-source manual exercise grants no baseline or optimization credit.

### 2.2 Automated post-capture seam

The preferred deterministic seam is a run-bound recognition-finalization
operation at the existing EOT/STT-requested boundary. It must preserve the
ordinary downstream authority, identity, cancellation and failure contracts;
it cannot inject an unbound transcript directly into Agent history or bypass
the unified committed-input owner.

If the exact finalization seam cannot be instantiated without weakening the
product contract, the first runner may expose a separately named
`post_stt_pipeline` profile beginning at authoritative `unified.submit`. That
profile excludes STT finalization and must not be reported as the complete
post-capture track.

For a Live Voice-only experiment, a declared fixture may hold the transcript,
Agent/Tool outcome or PresentationUnit input constant. Such a profile isolates
presentation, synthesis, downlink, playout and ACK, but remains separate from a
real-Agent profile. Agent time is still recorded when the real Agent is used;
it is not the initial optimization owner.

Pipeline automation may use a controlled Browser runtime for WebAudio output
without requiring the operator to navigate the product UI or speak. Removing
manual UI operation does not permit Browser playout to be replaced silently by
a server byte-receipt proxy.

## 3. Corpus v0.1

### 3.1 Required coverage

The initial corpus should cover the cases already required by the latency plan
without expanding current product scope:

- short dialogue without a Tool;
- dialogue that invokes a Tool;
- supported Task create;
- supported Task status;
- supported Task cancel;
- Chinese speech with a legitimate breath pause;
- barge-in at a declared point;
- one declared degraded-network profile.

Additional diagnostic cases may cover a short mid-utterance pause, a long
breath, low background noise and semantically ambiguous speech. They must remain
separate from the core profile so they do not silently change its population.

### 3.2 Audio construction

Each corpus artifact should have:

- a stable public `corpus_case_id` and corpus version;
- lossless source audio;
- declared sample rate, channel count, sample format and duration;
- exact leading and trailing silence;
- a reviewed speech-end reference expressed as a sample index;
- declared language, speaker class and acoustic profile;
- an expected semantic route and expected product outcome;
- required initial fixture state and state-reset procedure;
- expected allowed effects and forbidden effects.

The test input may use a reviewed synthetic voice for repeatability, but a
synthetic-only corpus is not sufficient evidence of recognition or VAD quality.
A later stable corpus should include consented, non-private human speech with
declared speakers and recording conditions.

Raw private/user recordings stay outside Git and outside probe events. A
tracked public corpus may have repository-level integrity checks, but runtime
metrics identify it only through the assigned `corpus_case_id`; they do not
emit content or content hashes.

### 3.3 Conceptual corpus entry

```json
{
  "corpus_schema_version": "live-voice.fixed-audio-corpus.v1",
  "corpus_version": "0.1",
  "corpus_case_id": "task_status_zh_001",
  "audio_artifact_id": "public/task_status_zh_001.wav",
  "audio_format": {
    "sample_rate_hz": 48000,
    "channels": 1,
    "sample_format": "pcm_s16le"
  },
  "speech_end_sample": 182400,
  "journey_type": "foreground_task_command",
  "expected_route": "task_status",
  "initial_fixture_id": "one_running_task_v1",
  "reset_procedure_id": "restore_one_running_task_v1",
  "expected_outcome_id": "truthful_status_response_v1",
  "forbidden_effects": [
    "task_created",
    "task_cancelled",
    "task_state_mutated"
  ]
}
```

The example is illustrative. Exact enum names must be aligned with accepted
code and probe contracts before the corpus becomes normative. Forty-eight kHz
is an example artifact format, not a new product invariant.

## 4. Reproducible product state

Every baseline and candidate run must use a sanitized manifest that freezes or
classifies at least:

- exact product commit and build inputs;
- probe event, catalog and reducer versions;
- corpus version and selected case IDs;
- Browser family/version and Windows class;
- Gateway and Agent runtime/WSL class;
- STT, TTS and Agent Provider/model profiles;
- VAD/EOT configuration;
- capture, encoding, chunking, downlink and playout configuration;
- feature flags and formal route selection;
- Tool catalog and deterministic Tool fixture policy;
- Task database fixture and reset procedure;
- cold/warm policy and warm-up procedure;
- network profile and degradation policy;
- physical or proxy observer profile.

Credentials, endpoints, hostnames, device identifiers and private paths remain
outside tracked artifacts and sanitized reports.

### 4.1 Task and Tool state

Audio equality does not make Task experiments comparable if authoritative state
differs between attempts.

- `task_create` starts from a fresh isolated namespace or restored database
  snapshot.
- `task_status` starts with the same declared Task and authoritative state.
- `task_cancel` starts with the same cancellable Task state and timing gate.
- every attempt restores the fixture before the next input.
- external Tool results should use a deterministic fixture when the purpose is
  pipeline comparison; real Tool variability belongs to a separately declared
  profile.

The fixture must validate positive business outcomes and zero forbidden
Agent/Tool/Task/history/audio effects where the route is rejected, stale,
cancelled or fails closed.

## 5. Run procedure

For each declared profile and corpus case:

1. verify corpus identity and run-manifest compatibility;
2. select exactly one optimization track and its compatible benchmark lane;
3. restore the exact initial Task/Tool/project state;
4. apply the declared cold or warm preparation procedure;
5. start one latency-probe attempt at the track's declared first boundary;
6. feed the exact audio or deterministic boundary fixture through the selected
   lane;
7. wait for the declared terminal, cancellation or failure boundary;
8. validate semantic route, authoritative outcome and forbidden effects;
9. collect correlated stage, total, quality and failure measurements;
10. reset the product state before the next attempt.

Case order should be fixed or deterministically randomized and recorded. Every
optimization decision uses A1/B/A2: baseline reference, candidate, then the
unchanged baseline reference again. Interleaving reference and candidate is
statistically stronger when the execution harness can switch builds without
changing other run inputs, but it does not remove the final drift check.

### 5.1 Agreed optimization execution order

The next work follows one closed loop rather than treating historical numbers,
new baselines and optimization results as one population:

1. review the implemented probe/runner, resolve unrelated product-code dirt,
   pin JiuwenSwarm and Agent-Core identities, and pass one clean no-Tool smoke;
2. establish the current A1 baseline with the fixed corpus and one frozen
   environment, first as a small pilot and then with the declared sample size;
3. analyze the earlier manual measurements only as qualitative historical
   evidence and compare their bottleneck direction—not their percentages—with
   A1;
4. reconcile A1 with the retained Hongxing optimization findings and current
   latency documents, classifying each hypothesis as `confirmed`,
   `partially_confirmed`, `not_reproduced`, `not_yet_measured`, or
   `methodologically_incompatible`;
5. rank the confirmed/open Live Voice-owned hypotheses, then implement exactly
   one named optimization per branch/worktree created from the same reference
   commit and dependency pin;
6. execute B and the unchanged-reference A2 with the same corpus, environment,
   state and attempt order, then accept, revise or discard the optimization
   from the closed A1/B/A2 result.

Earlier manual Browser-clock tables remain useful for identifying candidate
stages, reproducing symptoms and checking whether A1 tells the same broad
story. They are not a numerical baseline for the new harness because input,
Browser operation, manifest truth, run state and available stage boundaries
differ. A direct old-code/new-code latency claim would require re-running both
sources under the same current harness contract; it cannot be reconstructed by
subtracting the historical table from A1.

The first accepted A1 population belongs to Track 2. Track 1 capture/endpointing
continues independently because only it requires the supported Browser capture
surface and speech-end/recognition-quality guardrails.

## 6. Sample sizes and reporting

The governing latency documents currently require:

- at least 20 successful rounds per declared development profile;
- at least 30 rounds for a critical feature-complete acceptance scenario;
- cold and warm populations reported separately;
- failures, cancellations, fallbacks, degraded rounds, underruns and rebuffers
  retained in the attempt denominator.

Twenty samples can establish an initial development baseline but provide a weak
p95: the result is dominated by approximately one extreme observation. A
decision that depends on the tail should preferably use 50–100 successful
samples per compatible profile, or report a confidence interval and explicitly
classify the conclusion as inconclusive when observed variation exceeds the
candidate improvement.

Every comparison should report:

- optimization track and benchmark lane;
- sample and attempt counts;
- stage-by-stage p50 and p95;
- end-to-end and next-turn-ready p50 and p95;
- absolute and relative deltas;
- failure, fallback, degradation, false-EOT, underrun and rebuffer deltas;
- correctness and forbidden-effect results;
- measurement quality and unavailable segments;
- whether a reduced wait moved to a different downstream stage.

Capture/endpointing reports must also retain the reviewed physical speech-end
reference, false/missed EOT, truncation, recognition quality, capture gaps and
recovery outcomes. Pipeline-excluding-capture reports must state whether they
begin at EOT/STT requested or at the later `post_stt_pipeline` fallback seam.

The same-audio attempts should be compared by compatible case/profile. Samples
from different corpus cases, cold/warm classes, Providers, Browser/runtime
classes, VAD settings or network profiles must not be pooled.

## 7. Optimization decision rule

One optimization is accepted as a latency improvement only when all applicable
conditions hold:

1. the intended stage or boundary improves against a compatible baseline;
2. the relevant end-to-end headline improves or remains within an explicitly
   accepted trade-off;
3. the wait is not merely displaced into another stage or next-turn recovery;
4. p95 and quality guardrails do not regress beyond the declared threshold;
5. semantic outcome and authoritative effects remain correct;
6. partial, stale, wrong-scope, failed and cancelled paths retain zero forbidden
   effects;
7. the observed delta is larger than experimental noise, or the result is
   reported as inconclusive rather than positive.

This rule supports the intended loop:

```text
measure -> establish baseline -> apply one optimization -> re-measure -> compare
```

It does not create a general observability platform or require dynamic
critical-path analysis before the first useful baseline.

## 8. Artifact boundary and remaining acceptance

The development implementation now provides a private fixed-WAV manifest,
default-off controlled Browser composition, supervised post-capture runner,
v1 reports and clean-source A1/B/A2 comparison. Their existence grants no
baseline or optimization credit before clean execution and review.

The stable benchmark still needs decisions or accepted assets for:

- a public corpus manifest and lossless audio artifacts;
- a private machine/run profile with a sanitized exported fingerprint;
- reproducible Task and Tool fixtures;
- a Browser audio-feed harness for Windows Chrome;
- a deterministic capture/endpointing PCM diagnostic harness;
- an optional deterministic Agent/Presentation fixture profile for isolating
  Live Voice output stages;
- unattended state restore/cold-run orchestration where later justified;
- reviewed clean baseline, candidate and physical/capture evidence.

Artifact paths, exact browser-input technology, corpus licensing and fixture
ownership are intentionally left open for review in the main design thread.

## 9. Decisions for the next review

Before turning this draft into an accepted spec or implementation packet,
decide:

1. whether the first baseline uses Windows virtual-microphone input, controlled
   hardware loopback, or both;
2. which exact corpus cases constitute the minimum development profile;
3. whether synthetic and human speech are separate profiles or one stratified
   corpus;
4. which Task/Tool fixtures are deterministic and which retain real external
   behavior;
5. whether 20 samples are sufficient only for smoke/baseline work and which
   comparisons require 50–100;
6. how physical first-audible is observed without substituting a Browser proxy;
7. where public audio artifacts live and which licensing/privacy review applies.
8. the exact production-contract-preserving recognition-finalization seam and
   whether the first implementation needs the narrower `post_stt_pipeline`
   fallback;
9. which deterministic Agent/Presentation fixture is sufficiently stable for
   Live Voice-only output experiments without being mistaken for real-Agent
   E2E.

## 10. Next cross-worktree A1/B/A2 optimization harness

This section records the agreed experimental direction. It does not by itself
activate a specific optimization packet and grants no baseline or optimization
credit; those require the clean compatible executions below.

### 10.1 Experiment boundary

Baseline-before A1, candidate B and baseline-after A2 run as three separate
immutable executions. A1 and A2 use the same unchanged reference source; B
contains one named optimization. The harness must never switch source trees
inside an already warmed backend or reuse one `run_id`, output directory,
report, Browser storage namespace, Task store, or JiuwenSwarm data directory
across A1, B and A2.

Each invocation identifies at least:

- experiment role: `baseline_before`, `candidate`, or `baseline_after`;
- optimization track and benchmark lane;
- exact first and terminal measurement boundaries;
- exact clean JiuwenSwarm worktree and commit;
- the matching Agent Core dependency identity;
- corpus version and profile/case sequence;
- warm or cold policy;
- a private state-template identity;
- a fresh run directory and `run_id`;
- the optional compatible baseline report used for comparison.

Formal comparison must reject dirty product source by default. A dirty-source
run may be retained as diagnostic evidence, but it cannot be promoted to the
accepted baseline or candidate population.

### 10.2 Private state isolation

Provider credentials, registered Code project state, Browser permissions and
other machine-private configuration remain outside Git. A prepared private
template may contain those values. Before each A or B run, the harness clones
the template into run-exclusive `JIUWENSWARM_DATA_DIR` and Browser-profile
locations so that histories, Sessions, Tasks, command journals, caches and
probe indices cannot leak between populations.

The template is mutable setup material, not benchmark evidence. A sanitized
fingerprint records only compatibility-relevant classes and versions; it must
not disclose credentials, endpoints, private paths, device identifiers or raw
audio content.

### 10.3 Session and cycle policy

One five-profile cycle retains one saved Code Session in the fixed order:

```text
dialogue_no_tool
    -> dialogue_with_tool
    -> task_create
    -> task_status
    -> task_cancel
```

`task_create`, `task_status` and `task_cancel` must share the exact Session so
that status and cancellation address the Task created in that cycle. A later
cycle starts with a fresh saved Code Session to avoid unbounded Chat history and
memory becoming an uncontrolled latency variable. The supported Browser tab
remains the same within a run so the per-profile `round_index` stored in
`sessionStorage` stays continuous.

Changing Session during a cycle, reusing a Session across independent A/B
runs, clearing Browser storage, or reusing output after a partial restart makes
the affected experiment invalid rather than silently repairable.

### 10.4 Track-specific execution and comparison

The capture/endpointing harness may initially favor a supervised state machine
over DOM automation. It may arm audio, validate the preceding batch, select the
next profile/case URL, track counts, perform clean shutdown/drain, generate
reports and compare A with B. A human may still create/select the saved Code
Session and activate Live Voice when prompted.

The pipeline-excluding-capture runner should instead be automated from its
declared boundary. It must not require microphone operation or interactive UI
clicks for every attempt. When Browser WebAudio is part of the measured tail, a
controlled Browser runtime may be retained and initialized once per declared
cold/warm policy; it still consumes run-exclusive state and preserves the real
playout/ACK contract.

For every transition the harness must verify the expected profile, input case,
round index, component shards and terminal outcome before advancing. Missing or
conflicting batches, unexpected fallback/degradation, wrong Task state,
forbidden effects, exporter-drain failure or an incompatible run manifest stop
the experiment and remain in its denominator.

Comparison is allowed only when A1, B and A2 agree on every declared
compatibility dimension other than B's exact source commit and named
optimization. B must improve against both A1 and A2. A1→A2 latency,
denominator and failure drift must be smaller than the minimum candidate gain.
The result must show stage-by-stage and total absolute/relative deltas,
denominators and guardrails, and must report `inconclusive` when the apparent
improvement is smaller than drift or merely moves the wait downstream.

### 10.5 Optimization ranking and worktree policy

Rank one optimization candidate at a time using, in order:

1. contribution to `response_total` and the affected user-visible headline;
2. repeatability and p95 stability of the stage in A1;
3. direct ownership by Live Voice rather than Agent-Core/model/Tool internals;
4. evidence that reducing the wait will not move it into a downstream stage or
   successor recovery;
5. failure, fallback, underrun, rebuffer, ACK and semantic-risk guardrails;
6. implementation complexity and rollback cost.

Each candidate worktree starts from the same reviewed reference commit, pins
the same Agent-Core identity and declares one target segment, hypothesis,
minimum gain, response-total expectation, guardrails and exclusions. Unrelated
optimizations never share one B population. A passing B may become the next
reference only after its own review and A1/B/A2 acceptance; otherwise the
branch is revised or discarded.

### 10.6 Deliberately deferred automation

The current MVP does not need to:

- switch automatically between two worktrees in one command;
- automate UI interaction through Chrome DevTools or DOM selectors;
- perform unattended cold restarts;
- create or restore public credential-bearing snapshots;
- pool deterministic injection, controlled Browser and physical-journey lanes;
- accept an optimization based on one smoke run.

Those capabilities can be added after the supervised Browser baseline is
repeatable. They must preserve the separate-run and state-isolation boundaries
above rather than broadening one process into a shared A/B runtime.

This deferral does not apply to the post-capture runner itself. That runner is
the intended fast optimization loop and should use the narrowest production-
contract-preserving seam rather than automate product UI gestures.
