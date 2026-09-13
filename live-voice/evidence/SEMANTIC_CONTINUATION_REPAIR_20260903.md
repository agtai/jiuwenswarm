# Semantic continuation repair — bounded evidence, 2026-09-03

This records the repair of a contextual delegation rejected at 14:21:27 local
time with `SEMANTIC_OUTPUT_INVALID`. It is not complete Demo, audio, latency or
artifact-quality acceptance. Scope/risk authority is the current packet in
[STATUS](../STATUS.md) and root [TESTING](../../TESTING.md).

## Failure and change

The real model returned `task.create` / `local_artifacts` with
`continuation_action=accept_proposal`, but both reference fields were null.
The unchanged decoder correctly rejected that inconsistent tuple. The durable
request recorded rejection; the rehearsal store remained at four original Tasks.

The model-only resolver now exposes the existing authoritative continuation
choices directly in the top-level schema properties. No pending record means
all three reference/action fields are null. Existing per-reference stage and
exact-confirmation constraints remain. Direct contextual delegation explicitly
uses the null tuple and preserves the selected original user requirements.

Empty final content and `SEMANTIC_OUTPUT_INVALID` share at most two total model
attempts and one overall timeout. Structural failure adds generic system feedback
to the original input/context, without feeding back the invalid object or patching
its fields. Authority is rechecked before either invocation. Tool requests,
non-retryable authority/bounds failures, cancellation and repeated invalid output
remain rejected. No Task effect occurs before a valid decision reaches its normal
authorities. No domain phrases, fixture filenames or canned answers were added.

## Focused checks

- Initial selected semantic/Registry run: 30 passed, one new test failed because
  it compared dataclass JSON key order instead of canonical frozen-record content.
  Correcting that assertion and running the affected follow-up gave eight passes;
  **38 distinct final passing cases**, not 38 plus the initial run.
- Coverage includes invalid-to-valid local create, one Task on exact replay,
  persistent failure/replayed rejection with unchanged store and zero Agent calls,
  retained user requirements, frozen replay, shared deadline, changed authority,
  cancellation, tool rejection, scope rejection and bound confirmation invariants.
- Ruff passed for the three affected Python files; `git diff --check` passed.
  The runtime's normal isolated frontend build passed in 37.29 seconds.
- Complete incremental diff received scoped self-review. No independent review
  tool was available and parallel agents were not activated; independent and
  cumulative review credit remains open. No full suite or physical run was done.

## Bounded real-model evidence

The user's reported transcript was combined with the actual durable presented
analysis and original user message, in an isolated context with no executor.
The failed request has no frozen semantic input record; this is a reconstructed
read-only semantic replay, not a replay of a complete captured audio request.

| Case | Result | Model calls | Semantic elapsed |
|---|---|---|---|
| Reported delegation with actual earlier analysis | Direct create, null continuation tuple, original requirements retained | 1 real | 6.000 s |
| Inject the exact recorded invalid first response, then use the real model | Valid corrected direct create, original requirements retained | 1 recorded injection + 1 real | 3.812 s |
| Explicitly withhold background delegation | Dialogue, no task operation | 1 real | 1.875 s |

These times exclude microphone/ASR, Task execution, answer narration and playback.
Provider configuration hashes were unchanged. The mixed injection case proves
real-model regeneration after the observed structural failure; it is not two
successful live Provider calls. No Task/Tool/audio effects occurred in these probes.

## Source and private evidence

Baseline HEAD: `87248911fde2220be6a97f72f8c0210ac67d5b67`; inherited candidate
changes were preserved. No commit or remote update was created for this repair.
Tested product file SHA-256:
`a44324ea8708e2958cb61441ded578265aee8d14bf21e16dabbf6df7fb585217`.

Machine-private evidence directory:
`%TEMP%/live-voice-semantic-retry-20260903/` contains the before-file snapshots,
incremental diff, tested source manifest, check summary, follow-up test log and
real-model final outputs. Credentials were read only from their existing location.

Deployment verification in private `deployment.json` and `deployed-source.json`
confirms the original 6175 runtime is serving this product source. Its normal
launcher restarted the owned services; ports are ready and HTTP returns 200.
The original four Tasks, four result records, 12 command records and project files
have unchanged fingerprints. This is deployment/data-preservation evidence only.
