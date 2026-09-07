# Realtime optimization: first bounded implementation batch

The 2026-09-07 user request authorizes an isolated optimization worktree/branch,
parallel workers, and Main-owned acceptance and local integration into
`hx/0812_live_voice_w3`. This packet activates the reusable D-060/D-062 ownership
model; [root guidance](../../AGENTS.md), [testing](../../TESTING.md), D-119 and
[STATUS](../STATUS.md) retain their authority. No remote update is authorized.

## Intended behavior and boundaries

Baseline source is `26eb034bc3df0f66a9896942bb15efde356691f9`. The other server's
rehearsal evidence directories are absent at their expected local repository
paths. The handoff's 49.783 seconds and 35–40 second target are unverified input
and budget here, not measurements or acceptance of this batch.

| Owner | Owned source/test surface | Scope and risk |
|---|---|---|
| Main / integration | Native Engine, passive diagnostic allowlist, Engine and profiling tests; this packet and STATUS | P0: content-free completed-argument shape, response request/wait/send/confirmation, receipt send, first valid audio and actual presentation-ACK observations. Tier 2 because observations sit at concurrent state transitions; no scheduling or authority changes. |
| P1 worker | `native_business_contract.py`, its focused test file | Required-text descriptions consistent with existing validation and operation fields. Tier 1 model-input description candidate; no schema, operation, parser, correction-policy or permission changes. |
| P2 worker | A narrow Native Provider-output encoding helper and focused tests | P2 equivalent inner function-output JSON encoding only after canonical receipt validation. Original canonical text, digest, journal, Runtime, limits and replay remain authoritative. Main integrates the helper at the Engine seam. Tier 2 representation/replay-sensitive boundary, with unchanged wire envelope. |
| Independent reviewer | Read-only complete scoped diff and evidence | Review the implemented module and integration seams; never review one's own implementation as independent evidence. |

Workers use separately assigned worktrees and edit only assigned files. Main
alone edits the integration worktree, performs Git commits/integration, owns
shared semantics and resolves findings. Workers cannot push, change w3, integrate
their own return, rewrite history, or edit another worktree. Actual tool capacity
is Main plus up to three workers; use only independently useful lanes.

## Acceptance and exclusions

Follow the applicable Tier 1/2 dimensions in root TESTING. Prove valid work and
Task calls retain existing validation, rejected/stale/wrong-target calls have no
forbidden business/audio/history effects, successful calls are not replayed,
and STOP/new-turn/actual-playout ownership remain unchanged. Diagnostic emission
failure must not change operation success or rejection; records must contain no
request, result, argument values, credentials or arbitrary object representations.
Use bounded nonblocking existing diagnostics, retain identity and clock domains,
and distinguish Provider creation confirmation from transport send and actual
playback ACK. Automated transport tests do not establish real Provider latency.

P1 verification strips descriptions to compare the tool shape against baseline,
then runs focused contract and affected business Engine checks. P2 verifies
parsed-value equivalence, UTF-8 size on multilingual synthetic payloads, unsafe
representation fallback, exact replay/digest preservation and legacy exclusion.
P0 runs focused Engine, diagnostic sanitizer/export and affected Runtime tests.
Main performs cold complete-diff review and an independent review; repeat only
affected checks after findings. Tests use isolated data and pytest temporary paths.

This batch does not split tools, add a classifier, change shared schema or Task
authority, delete context, prepare overlapping Provider responses, change VAD or
audio buffering, deliver partial Agent conclusions, or tune models/Providers.
First argument-fragment, browser physical start/stop and cross-process timing
gaps remain for later evidence work. Effective private USER.md/project facts,
running model/deployment identity and physical headset acceptance require the
actual environment; do not rewrite fixture facts to make an answer succeed.

The broader P0/P1/P2 roadmap and P3–P9 experiments remain conditional on evidence.
No measured speedup, full optimization completion, deployment, complete
Cascade/Native physical journey or D-084 candidate credit follows from this batch.

## Implementation and review

P1 changes descriptions only: required text is non-null/nonblank, NUL-free and
within the existing UTF-8 limits; `request_text` does not substitute for operation
fields. Recursive removal of descriptions yields the exact baseline tool object.
No prompt text snapshot tests were added; the existing validation oracles apply.

P2 is integrated exclusively in `_send_business_result`, after original text,
size, source identity, replay and JSON checks. `compact_native_business_output`
validates grammar, then re-encodes JSON string tokens; numeric lexemes, duplicate
keys, order and all other source text stay exact. Invalid/unsupported or
non-smaller representations retain the exact original string. The original text
still supplies the receipt digest. The actual Session serializer preserves the
equivalent Unicode output. A synthetic multilingual receipt measured 3946 to
1758 UTF-8 bytes internally and 4732 to 1900 bytes for its complete client event.
These are one fixture's byte counts, not the unavailable rehearsal or token/time
savings. No context facts, receipt or playback ACK were removed.

P0 observes response send/confirmation, generation/playout/scheduler/sibling-call
waits, context refresh, successor queueing, completed/validated/rejected
arguments, receipt preparation/send, first valid Provider audio and accepted
presentation ACK. Wait observations are deduplicated and emitted through the
existing bounded nonblocking sink. Closed argument metadata carries presence,
type, string length and UTF-8/NUL/blank facts without values. Provider response
identity stays distinct from the Runtime response identity. Snapshot emission
excludes unrelated async context identities. A first valid audio observation
is not browser playback, and an Engine ACK observation follows the existing
authoritative ACK admission; it does not independently measure physical sound.
Notification occupancy, first argument fragments and full end-to-end clock
attribution remain outside this batch's diagnostic credit.

Main performed the complete scoped cold review. An independent subagent reviewed
the complete production/test diff and confirmed no remaining actionable
correctness, safety or privacy finding after the async-identity attribution fix.
That fix uses `profile_snapshot_event`, with an adverse ambient-context test;
it does not alter scheduling. The reviewer independently ran 59 focused checks,
18 affected checks after the fix, and 10,000 deterministic Unicode/escape probes.
The reviewer did not implement this batch. Workers supplied uncommitted bounded
candidates from separate worktrees; Main adopted them into one related Native
module batch and owns the resulting local commit/integration.
Before integration, w3 advanced by the unrelated documentation-only commit
`3f34f96178248adcdf645bbece3087fed89f9d4b`. Main inspected its complete file scope;
it adds only `evidence/REMOTE_LIVE_VOICE_DEPLOYMENT_AUDIT_20260907.md` and touches
none of this batch's code, tests or current-status edits. Preserve that commit
by advancing the optimization base locally before its own commit and w3 handoff.

An advisory identified synchronous encoding cost on large synthetic receipts.
Main changed the regex to consume ordinary characters in runs, retaining the
same JSON-string boundaries, and added `receipt_prepare_started` so this cost is
observable. Seven local iterations measured median 51.319 to 12.572 ms for one
337998-byte escaped-Chinese fixture, and 0.419 to 0.044 ms for a 3792-byte fixture.
These are local microbenchmarks, not stable percentiles or voice latency claims.
The encoder still uses the event loop synchronously within the existing 512 KiB
receipt bound. Only affected encoding/diagnostic/Engine checks were repeated.
Independent follow-up reviewed these exact two changes, passed 28 affected
encoding/timeline checks and 10,000 old/new tokenizer equivalence probes, and
reported no new finding. No further required code review remains for this batch.

## Verification evidence

Tests use the existing Python 3.11 environment, `PYTHONUTF8=1`, isolated
`JIUWENSWARM_DATA_DIR` and unique worktree-local `--basetemp` paths. Source is the
commit containing this packet and the listed implementation. The final handoff
records its hash. The owning command is `python -m pytest <modules> -q
-o addopts='' --no-cov -o log_cli=false --basetemp=<unique-path>`.

| Check | Actual result and exact boundary |
|---|---|
| Baseline and initial P0 regression | 193 passed: Native Engine and demo profiling, before and after initial diagnostics. |
| P1 worker | 40 passed / 136 deselected: contract and Engine selected by `business or invalid_adjustment or repeated_invalid_arguments`; actual imported source and description-stripped tool equivalence verified. |
| P2 worker | 27 passed: `test_native_business_encoding.py`, including real Session serializer, UTF-8 bounds and nonstandard/surrogate fallback. |
| Integrated regression before snapshot attribution repair | 367 passed: the module list below. |
| Snapshot attribution repair affected rerun | 241 passed: Engine, demo profiling, Gateway audio diagnostics and the three new modules. |
| Final run-scanning/preparation milestone rerun | 45 passed: the three new modules below. |
| Cascade/feature-off seam | 3 passed: `test_master_flag_off_constructs_no_registry_or_adapter`, `test_cascade_p2_activation_has_no_private_native_descriptor`, `test_retired_demo_policy_flag_cannot_reenable_a_production_bypass` in `test_product_composition_registry.py`. |
| Static/format | Scoped `ruff check --select F,E9` and `git diff --check` pass; changed local document links checked. |

Integrated regression module list (paths under `tests/unit_tests/`):

```text
live_voice/test_native_business_contract.py
live_voice/test_native_business_context.py
live_voice/test_native_business_registry.py
live_voice/test_native_business_runtime.py
live_voice/test_native_business_authority.py
live_voice/test_native_interaction_runtime.py
live_voice/test_openai_realtime_native_engine.py
live_voice/test_openai_realtime_session.py
live_voice/test_demo_profiling.py
gateway/test_audio_diagnostics.py
gateway/test_native_interaction_runtime_client.py
live_voice/test_native_business_diagnostics.py
live_voice/test_native_business_encoding.py
live_voice/test_native_business_encoding_engine.py
```

The three new modules prove closed/private rejected-argument diagnostics, sink
failure and identity isolation; distinct send/confirmation/first-audio/ACK facts;
complete multilingual JSON equivalence and numeric/duplicate-key preservation;
original digest conflicts; concurrent exact repeat with no extra send; original
size/identity/retirement rejection before encoding with zero new output; and
legacy exclusion. Existing Runtime/Registry/authority regressions retain business
and recovery coverage. Full-suite, frontend build and physical Cascade/Native
acceptance are not claimed by this backend-only batch.

## Runtime and remaining evidence

The expected original Realtime/Cascade evidence directories remain absent.
The local saved runtime record identifies an older `f76fde5199` Cascade source,
not a current Native candidate; its recorded ports (6175, 18194, 19120, 19121) had
no listeners during this task's check. No service was started/restarted, browser
opened, model changed, credential copied, project/USER facts edited, or original
rehearsal data regenerated. A saved runtime record is not a running identity.
Actual Native deployment, configured Agent/file integration and physical
rehearsal still require controlled startup and current-source evidence. The
handoff's hotel-departure error cannot be fact-checked from missing project/run
inputs and is not claimed fixed. Full P0/P1/P2 optimization remains partial.

An adjacent pre-existing concern was found in Router/journal replay: the journal
sorts object keys while Router canonical output follows the returned mapping's
order. This batch leaves those files and canonical bytes unchanged; route a
reproduction to the Native receipt/recovery owner instead of claiming repair.

Early worker pytest invocations reached passing test results but remained in
repository-wide coverage generation. Their completed `--no-cov` reruns are the
evidence above. A cleanup attempt for ignored worker `.coverage`/`htmlcov` output
was rejected by automatic approval review with only `blocked by policy`; the
artifacts remain ignored and excluded from the commit. No required verification
depends on deleting them. Original worker candidates remain in their worktrees.
