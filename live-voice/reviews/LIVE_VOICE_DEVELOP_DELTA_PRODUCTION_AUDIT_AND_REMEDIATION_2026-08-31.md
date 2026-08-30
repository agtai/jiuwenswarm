# Live Voice develop-delta production audit and remediation plan — 2026-08-31

> Audit state: **COMPLETE — FROZEN READ-ONLY RECORD**
>
> Candidate source: `bb3d9ab1be1e55fef88abb0bc2fbd380ef7d043f`
>
> Compared develop source: `8f34291906abf7c4e1a3a94d1a819e5a94c0ff3b`
>
> Final disposition: **NO-GO for direct integration or release**

This document consolidates the two production-code reviews performed on the
generation-interruption review branch and the subsequent remediation advice.
It is a frozen branch-specific review record under
[the documentation rules](../DOCUMENTATION_RULES.md), not a replacement for
[STATUS](../STATUS.md), not product progress, and not acceptance evidence. No
production code, tests, protocol, schema, migration, runtime configuration or
remote ref was changed by this document.

The first review was a risk-prioritized static deep review completed in about
32 minutes. It produced useful findings but did **not** inspect every production
file and its original completeness wording was withdrawn. The second review
used a frozen 191-file manifest and did not declare completion until every
listed production/runtime file had an audit owner and cross-lane reconciliation.
The second review therefore supersedes the first review's coverage and severity
claims while retaining the first review's confirmed findings.

## 1. Frozen Git baseline and scope

| Fact | Frozen value |
|---|---|
| Candidate branch | `codex/live-voice-generation-interruption-review-20260828` |
| Candidate HEAD | `bb3d9ab1be1e55fef88abb0bc2fbd380ef7d043f` |
| Candidate feature commit | `cf81f23c9a6107e98c1377e991cd0ca8a792dd83` — 41 generation-interruption commits composed as one commit |
| Candidate bugfix commit | `bb3d9ab1be1e55fef88abb0bc2fbd380ef7d043f` — migrated strict-review bugfix and semantic conflict repairs |
| Compared ref | `origin/develop` |
| Compared develop HEAD | `8f34291906abf7c4e1a3a94d1a819e5a94c0ff3b` |
| Merge base | `3f3cdbb7f45fdd29e7d03deafa5bca10e363434e` |
| Production/runtime manifest | 191 paths from the frozen develop-delta scope |
| Sorted manifest SHA-256 | `3f09b22524c77c5402c3760ceb6e861a1369ce4b8880ed221816eb367539942d` |
| Excluded from review | Documentation, tests, fixtures, examples, generated artifacts and machine-private runtime data |

The repository had no `dev` remote branch at the audit freeze, so references to
“dev” in the review request were resolved to `origin/develop`. The candidate
and develop had both advanced substantially after their merge base. The review
therefore separated candidate defects from semantic integration conflicts; it
did not treat every develop-side change as a candidate defect.

## 2. Implemented feature surface relative to develop

Code presence is not completion or acceptance credit. The audited branch adds
or materially expands the following production surfaces:

1. Browser hands-free capture, device/permission/visibility handling, browser
   ownership, WebAudio playout and speech-output lifecycle.
2. Dedicated binary media WebSocket transport, one-time media tickets,
   streaming and batch STT/TTS, speech-start and automatic EOT processing.
3. Formal P1/P2 flow in which committed final speech reaches the real Agent
   round, with response generations, presentation ACK, history commitment and
   multi-surface notifications.
4. Generation-time speech interruption: successor capture remains available
   while an Agent response is generating; the old response's text/audio is
   fenced by exact response identity and the active conversational round is
   cancelled. Background Tasks are intentionally outside that round cancel.
5. P3 Task intent, clarification, confirmation, create/adjust/control,
   progress/result notification and persistent Task storage.
6. Project execution through an isolated Git worktree, bounded Git manifests,
   task scheduling, recovery and durability-related state.
7. Replay/idempotency/capacity controls, privacy and latency observations,
   feature flags, deployment preflight and controlled launch profiles.

The review does not claim that these surfaces are complete, correctly composed,
generalized, physically validated or ready for production enablement.

## 3. Review 1 — risk-prioritized static deep review

### 3.1 Actual coverage and result

Review 1 used three parallel lanes for browser/frontend, media/speech and
protocol/task code, with a main-session cross-module pass. It filtered roughly
171 production/runtime candidates and deeply inspected the highest-risk state
machines and call chains, but many remaining files received only path filtering,
search/static checks or targeted call-site inspection. It therefore was **not a
full production-code audit**.

Its provisional result was:

- no statically demonstrated P0;
- 8 P1 findings;
- 3 P2 findings;
- 28 merge conflicts against the frozen develop ref, including 20
  production/configuration conflicts;
- no product-code changes and no test, browser, audio-device or Provider run.

### 3.2 Reconciliation with the full audit

| Review 1 result | Full-audit disposition |
|---|---|
| Interrupt timeout/disconnect can block later capture | Confirmed as F02 / P1 |
| Shared streaming TTS Provider lacks Session scope | Confirmed as F04 / P1 |
| Dedicated media leaf lacks absolute lifetime and revocation | Confirmed as F06 / P1 |
| Unauthenticated media first frame is aggregated under a 100 MiB limit | Confirmed as F07 / P1 |
| Formal Live Voice does not own all audible TTS | Confirmed as F05 / P1 |
| Dirty submodule contents are absent from the executor fingerprint | Confirmed as F10 / P1 |
| Git manifest is not an atomic snapshot | Confirmed as F11 / P1 |
| Retired generation-interrupt action can be rebound | Confirmed and expanded as F03 / P1 |
| Dev WebSocket log leaks speech/Task content | Confirmed; upgraded from P2 to F12 / P1 |
| Build-reuse contract omits the generation-interruption Vite flag | Confirmed; upgraded from P2 to F13 / P1 |
| Consumed clarification continues to occupy active capacity | Withdrawn as a finding: the observed retention may be an intentional replay fence and no contrary owning contract was found |

No production change is recommended for the withdrawn clarification item until
its owning replay/capacity contract is established. If that contract later says
consumed entries are not active, the appropriate repair is to move them from
the active-capacity map into a separately bounded replay tombstone; silently
deleting replay identity would not be acceptable.

## 4. Review 2 — full production/runtime audit

### 4.1 Coverage ledger

| Lane | Audited | Result |
|---|---:|---:|
| Frontend/browser | 75/75 | P1 × 4, P2 × 1 |
| Media/Speech/WebSocket | 25/25 | P1 × 3, P2 × 2, P3 × 2 |
| Protocol/Task/project execution | 51/51 | P1 × 4 |
| Shared runtime/configuration/launch | 40/40 | P1 × 2, P2 × 3 |
| **Total** | **191/191** | **P1 × 13, P2 × 6, P3 × 2** |

The 191 paths consist of 184 JiuwenSwarm production/runtime files, including
the two frontend environment profiles, plus seven deployment, launch and lock
files. The review inspected each file and its changed production hunks, then
cross-checked callers, state transitions, cancellation, cleanup, capacity,
scope/authority, replay and develop compatibility.

### 4.2 Final disposition and verification boundary

- **NO-GO:** the candidate must not be directly integrated or released.
- No P0 was demonstrated within the static evidence boundary.
- 13 P1, 6 P2 and 2 P3 findings were confirmed.
- `git merge-tree` identified 28 conflicts, including 20 production/configuration
  conflicts that require semantic migration.
- 108/108 audited production Python files passed AST parsing.
- No production whitespace error was found. The range-wide whitespace command
  reported only pre-existing Markdown trailing spaces outside the production
  review scope.
- Frontend dependencies and a standalone TypeScript compiler were unavailable,
  so no TypeScript check or production build was run during the audit.
- The machine-installed `openjiuwen` did not match the dependency locked by the
  branch, so import-based runtime checks were not treated as candidate evidence.
- Per the requested scope, tests were neither reviewed nor run. No browser,
  microphone, speaker, external Speech Provider or fault-injection journey was
  executed.

“191/191 reviewed” means the frozen production manifest had no unassigned or
unread path. It is not a formal proof that no other defect exists.

## 5. Confirmed findings and remediation

### F01 — P1 — Unified submit interrupts before durable admission

**Evidence:**
`jiuwenswarm/server/live_voice/product_composition_registry.py:7352-7476` and
`jiuwenswarm/server/live_voice/unified_committed_input.py:264-318`.

The generation interrupt can run before the committed-input journal decides
whether the identity is new, replayed, in progress or conflicting. A negative
conflict path can therefore produce an irreversible interrupt side effect.

**Required change:**

- Move journal admission before interrupt, context retention, Agent submission
  and every other semantic side effect.
- Return explicit `NEW`, `REPLAY`, `IN_PROGRESS` and `CONFLICT` outcomes; only
  the `NEW` owner may execute the interrupt.
- Persist one immutable interrupt command containing action ID, superseded
  response/generation and target digest.
- Use durable phases equivalent to
  `ADMITTED -> INTERRUPT_PENDING -> INTERRUPT_SETTLED -> SUBMIT_SETTLED`.
- On unknown result or crash, recover by the original action identity. Never
  mint a replacement command for the same submitted input.

**Not sufficient:** moving only one interrupt call, marking the journal complete
before the effect settles, or compensating after a conflict.

**Minimum acceptance:** conflict and journal-failure paths have zero interrupt,
Agent and Tool side effects; response-loss replay executes the exact interrupt
at most once; crashes around every phase recover without changing identity.

### F02 — P1 — Ambiguous generation-interrupt settlement can block capture

**Evidence:**
`jiuwenswarm/channels/web/frontend/src/components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx:2904-2921,5758-5871`
and
`jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productWebActivation.ts:1357-1425`.

**Required change:**

- Replace the current minimal pending ref with a retained attempt holding the
  exact owner, action ID, response/generation, foreground fence, generation
  capture, loop generation and response identity.
- Route initial settlement, reconnect recovery and predecessor cleanup through
  one single-flight settlement function.
- For `fenced`, clear only the foreground/capture still owned by that attempt.
- For `already_settled`, remove the optimistic refusal only if the old
  foreground remains current; never revive a response already superseded by a
  successor submit.
- Definitive errors do not retry. Timeout/disconnect/transport-unknown retains
  the attempt and schedules bounded exact-identity replay.
- An attempt belonging to a retired Session may settle but must not mutate the
  successor Session's UI. Exhausted recovery enters explicit Session recovery
  or controlled close rather than silently blocking capture.

**Not sufficient:** generic owner reconstruction, a new action ID per retry,
unconditionally clearing the pending ref, or ignoring `fence_status`.

**Minimum acceptance:** cover response lost before/after server application,
`fenced`, `already_settled`, definitive rejection, reconnect and Session switch;
there must be one action ID, one in-flight settlement and no permanent capture
barrier.

### F03 — P1 — Evicted generation action can rebind and cancel conflict becomes success

**Evidence:**
`jiuwenswarm/server/live_voice/conversation_runtime_loop.py:741-768,1098-1136`,
`jiuwenswarm/server/live_voice/agent_conversation_runtime.py:3133-3259` and
`jiuwenswarm/server/live_voice/jiuwenswarm_round_harness.py:687-705`.

**Required change:**

- Bind every action ID to an immutable target digest covering interaction,
  response, generation and round.
- Preserve exact retirement identity until the Session/authority replay horizon
  closes. Capacity exhaustion must fail closed; it must not evict an identity
  and permit reuse.
- Prefer scope/authority epochs plus a durable exact tombstone. A random UUID
  only reduces accidental collisions and does not establish identity semantics.
- Propagate harness `IDEMPOTENCY_CONFLICT`, rejection and unknown settlement to
  the product layer.
- Report interruption success only when both the response fence and round cancel
  reach an allowed terminal state. `FENCED + cancel CONFLICT/UNKNOWN` remains
  failed or unknown and retains a recovery handle.

**Minimum acceptance:** after more than the current 256-entry window, old action
plus same target is replay, old action plus another target is conflict, and a
harness cancel conflict never produces `generation_interrupted` success.

### F04 — P1 — Streaming synthesis state is not Session-scoped

**Evidence:**
`jiuwenswarm/gateway/live_voice/streaming_synthesis_route.py:1464-1543`,
`jiuwenswarm/server/live_voice/streaming_speech.py:972-1038` and
`jiuwenswarm/server/live_voice/openai_streaming_speech.py`.

**Required change:**

- Introduce an immutable in-process synthesis scope containing at least Session,
  subject and correlation identity.
- Prefer `open_synthesis(scope, request) -> opaque handle`; require that handle
  for event, cancel and terminal operations.
- Scope every active-response, generation-highwater, synthesis, unit-sequence
  and tombstone map through all Provider/conformance layers.
- Only a higher generation in the same scope may supersede an earlier response.
  Scope close cancels only that scope; Provider close settles every scope.
- Global capacity may reject new admission but cannot free another scope by
  accidental supersession.

**Not sufficient:** adding scope only to `activate_response`, prefixing a public
response ID while internal maps remain unscoped, or creating unowned per-request
Provider instances.

**Minimum acceptance:** two Sessions using identical interaction/response/stream
IDs synthesize concurrently; generation and cancellation in one Session cannot
affect the other; global Provider close leaves zero active sessions/tasks.

### F05 — P1 — Formal Live Voice does not own all audible TTS

**Evidence:**
`jiuwenswarm/channels/web/frontend/src/components/ChatPanel/useProductVoiceBrowserOwnership.ts:151-186`
and `jiuwenswarm/channels/web/frontend/src/utils/ttsOutputOwnership.ts:12-40`.

**Required change:**

- Formal start must acquire browser ownership, revalidate Session intent,
  acquire a tokenized global TTS lease, stop existing TTS, and only then start
  capture/control. Lease acquisition precedes `stopAllTts()` so new ordinary
  TTS cannot enter the gap.
- Historical-message speech, ordinary server TTS and in-flight TTS completion
  must all reject or invalidate output while Formal owns the lease.
- A failed start retains the lease until capture/playout cleanup is complete.
- Exit, Session switch, takeover and unmount share one cleanup sequence: close
  Formal audio resources, release the exact TTS token, then release browser
  ownership.

**Not sufficient:** a shared boolean, stop-without-lease or releasing output
ownership before uncertain Formal cleanup.

**Minimum acceptance:** pre-existing HTMLAudio/SpeechSynthesis stops before
Formal start; ordinary TTS cannot start while Formal is active; stale cleanup
cannot release a successor Session's lease.

### F06 — P1 — Active media leaves lack owned deadlines and revocation

**Evidence:**
`jiuwenswarm/gateway/live_voice/dedicated_media_route.py:1073-1514` and
`jiuwenswarm/gateway/live_voice/dedicated_media_registration.py:2432-4456`.

**Required change:**

- Add an `ActiveMediaLeafOwner` that retains record ID, task, socket, absolute
  authority expiry, stop event, phase and terminal future.
- Use a one-way state machine:
  `ISSUED -> AUTHENTICATED -> ACTIVE -> STOPPING -> TERMINAL`.
- Race socket receive/send, Provider speech-start/EOT, source reads and ACK waits
  against stop and absolute deadlines.
- Revoke, expiry, replacement and shutdown first enter `STOPPING` atomically and
  reject all later frames; outside the lock they close the socket, cancel child
  work and perform a bounded join.
- Delete the record and release capacity only after terminal cleanup. A leaf in
  cleanup still consumes capacity.
- Shield the unique cleanup owner from caller cancellation and return an honest
  cleanup-incomplete outcome if the transport will not stop within budget.

**Not sufficient:** pruning only when another registry call arrives, deleting
the record without cancelling its coroutine, increasing TTL/capacity or relying
on WebSocket ping.

**Minimum acceptance:** silent/ping-only sockets expire; leaves blocked in
receive, send, source, ACK and EOT all terminate under revoke; duplicate close
shares one settlement; no post-revoke frame is accepted.

### F07 — P1 — Unauthenticated media input is aggregated under a 100 MiB limit

**Evidence:** `jiuwenswarm/common/ws_limits.py:9-11`,
`jiuwenswarm/gateway/channel_manager/web/web_connect.py:619-630` and
`jiuwenswarm/gateway/live_voice/dedicated_media_registration.py:4288-4297`.

**Required change:**

- Enforce the media message limit in the WebSocket protocol/listener before
  complete message aggregation.
- Prefer a dedicated media listener with a low protocol-derived `max_size`,
  small `max_queue`, bounded read buffers and no per-message compression.
- Prefer authenticating ticket/origin/subprotocol during HTTP Upgrade so an
  unauthenticated data message is never required. If a first-frame protocol must
  remain, the transport itself must enforce its small bound.
- Move genuinely large document uploads to HTTP/object upload if a shared
  listener cannot support a safe media limit.
- Apply the same policy to FastAPI/Uvicorn and legacy compatibility paths.

**Minimum acceptance:** boundary-sized authentication succeeds; one byte over
the bound closes with 1009 before parser/ticket consumption; malformed, slow and
oversized first messages consume no ticket and bounded concurrent memory.

### F08 — P1 — `TurnCommitLedger` probabilistic retirement fence saturates

**Evidence:**
`jiuwenswarm/common/schema/live_voice_contract_v2.py:3079-3221` and the global
ledger use in `jiuwenswarm/server/agent_ws_server.py:1381`.

The original algorithm's deterministic probe measured fresh-identity rejection
of approximately 1.35%, 29.81%, 75.66%, 95.20% and 99.03% after respectively
1,000, 1,500, 2,000, 2,500 and 3,000 retired pairs.

**Required change:**

- Replace the authoritative probabilistic fence with an exact retirement store
  containing unique commit-ID and turn-ID digests bound to the canonical commit
  and scope.
- Accept and retire both identities in one transaction. Persist RETIRED before
  removing the active in-memory origin.
- A probabilistic structure may remain only as a negative lookup optimization;
  every positive must be confirmed in the exact store.
- Garbage collection is allowed only after the entire authority epoch is
  irreversibly invalid and old credentials are rejected before ledger lookup.
- If durable exact storage cannot land immediately, retain exact tombstones and
  fail explicitly at capacity before changing active state.

**Not sufficient:** a larger bitset, fewer hashes, clearing generations without
an authority epoch, or relabeling false positives as capacity errors.

**Minimum acceptance:** large fresh streams have zero probabilistic rejection;
retired same-payload replay remains no-op and changed/cross-bound identity is
conflict; retirement-store failure leaves active/downstream state unchanged.

### F09 — P1 — Concurrent `run_task` replay can release the winning context

**Evidence:**
`jiuwenswarm/agents/harness/common/auto_harness/service.py:673-756,3612-3702`.

**Required change:**

- Add bounded single-flight coordination per owner/namespace/idempotency key.
- Store context as an ownership slot with an unguessable lease token and
  `BOUND`, `CLAIMED` or `RELEASED` phase.
- Replace the ambiguous adopt boolean with `ADOPTED`, `ALREADY_BOUND`, `MISSING`
  and `REJECTED` results.
- Error/replay paths may release only their own candidate through
  `release_if_owner(task_id, lease_token)`; only the scheduler's terminal owner
  may perform authoritative unconditional release.
- Keep a candidate local until durable get/create identifies the persisted task.
  An exact replay after process restart may CAS-install a replacement context
  only when the pending task truly has none.

**Not sufficient:** one conditional around the current boolean, a global lock,
raw `task_id` deletion or blind trigger retry.

**Minimum acceptance:** two concurrent same-command calls create one task and
one delivery; the follower releases only its candidate; conflicting fingerprint
does not affect the winner; cancellation/restart permits one explicit takeover.

### F10 — P1 — Dirty submodule contents are missing from Git fingerprints

**Evidence:** `jiuwenswarm/common/bounded_git_manifest.py:293-432` and
`jiuwenswarm/server/live_voice/project_code_executor.py:4537-4585`.

**Required change:**

- The minimum safe patch is to reject every dirty initialized submodule before
  dispatch/journal/Agent/Tool effects.
- For a gitlink, reject symlink/junction/reparse escapes, read the child HEAD and
  run bounded porcelain-v2 status including untracked and nested submodules.
- A clean child HEAD remains representable by the current manifest.
- Supporting dirty submodules requires a versioned recursive manifest containing
  child HEAD/index/status/content fingerprints under shared path, byte and depth
  budgets; that is a separately scoped schema/migration change.

**Not sufficient:** child HEAD alone, the parent's generic dirty bit, `git diff`
without untracked files, or unbounded recursive hashing.

**Minimum acceptance:** pre-existing tracked, untracked and nested dirtiness
fails before side effects; a clean child changed during initialization is caught
by the after guard; reparse/junction targets fail closed.

### F11 — P1 — Git manifest is a non-atomic mixed snapshot

**Evidence:** `jiuwenswarm/common/bounded_git_manifest.py:161-208,390-499` and
`jiuwenswarm/server/live_voice/project_code_executor.py:4537-4609`.

**Required change:**

- Capture a complete envelope A containing HEAD tree, index entries and status;
  read files derived from A; capture envelope B; return only when A and B match
  exactly. Retry a small bounded number of times, otherwise fail closed.
- Read each regular file from a no-follow handle, compare pre/post `fstat`, hash
  from that handle and confirm the path still resolves to the same file identity.
- Add a project-root inspection/initialization lock covering before snapshot,
  initializer fence, after snapshot and journal ownership transfer.
- Require initializer-derived work to join before the after snapshot. A sealed
  disposable worktree is the stronger design when external writers cannot obey
  the lock.

**Not sufficient:** rereading only HEAD or status, size/mtime-only checks,
`GIT_OPTIONAL_LOCKS=0`, accepting the last unstable result or infinite retries.

**Minimum acceptance:** concurrent untracked creation, index/HEAD mutation and
same-metadata path replacement are included in a later stable snapshot or cause
pre-effect failure; unrelated attempts against the same root are serialized.

### F12 — P1 — Dev WebSocket logging persists private speech and Task text

**Evidence:**
`jiuwenswarm/channels/web/frontend/devWsTrafficPrivacy.ts:48-99`,
`jiuwenswarm/channels/web/frontend/src/services/webClient.ts:73-93,320-396`
and `jiuwenswarm/channels/web/frontend/vite.config.ts:342-411`.

**Required change:**

- Define method/schema-aware safe projections. For Live Voice events retain only
  method, non-secret identifiers, sequence, state, byte counts and digests.
- Remove or replace speech text, instructions, adjustments, task names,
  display/spoken/rendered text and embedded JSON equivalents.
- Redact once in the browser before the logging POST and again immediately before
  persistence. Parse failures and redactor failures replace the entire data
  surface rather than fail open.
- Disable the log-read endpoint by default or require a local access token;
  retain restrictive file permission, rotation and bounded retention.
- Never include the original payload in redaction error diagnostics.

**Minimum acceptance:** unique canaries in unified input, task name,
instruction, adjustment and nested JSON appear in neither POST body, disk log
nor read endpoint, while approved diagnostic metadata remains useful.

### F13 — P1 — Validated build reuse omits compile-time Live Voice flags

**Evidence:** `scripts/live_voice/start_hands_free_demo.ps1:492-512,979-1140`.

**Required change:**

- Version the build-contract schema and add a canonical map of every
  build-affecting input, including
  `VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION` and the other Live Voice
  Vite flags, mode and public base URLs.
- Write the contract only after a successful build and bind it to source,
  dependency and bundle digests.
- Reuse requires exact canonical equality; unknown/new Vite inputs invalidate an
  older contract.
- Generate runtime flags from the verified build contract, not current command
  arguments. Prefer a Vite-emitted, non-secret build manifest whose digest is
  included in the launcher contract.

**Not sufficient:** warning on mismatch, defaulting missing fields to false or
rewriting the runtime contract without rebuilding the bundle.

**Minimum acceptance:** true→false and false→true reuse fail before service
start; same-value reuse succeeds; old schema is rejected; runtime claims match
the embedded bundle.

### F14 — P2 — Agent final can exceed the Speech API limit and silently lose audio

**Evidence:**
`jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/productP1VoiceRoute.ts:1219-1231`,
`jiuwenswarm/channels/web/frontend/src/features/live-voice/formal/gatewayBatchSpeechClient.ts:715-1123`,
`jiuwenswarm/server/live_voice/batch_speech.py:1319-1333` and
`jiuwenswarm/server/live_voice/agent_conversation_runtime.py:3685-3721`.

**Required change:**

- Add a deterministic client guard before synthesis-operation/generation state
  changes so an oversized unit fails explicitly rather than poisoning recovery.
- Implement full support in the authoritative server presentation producer:
  split a final into stable, ordered units no larger than the negotiated
  Provider metric, preserving exact Unicode text and contiguous spans.
- Give every unit a stable ID/sequence and ledger entry. Restore capture only
  after every unit is terminal; cancellation stops the current and all remaining
  units.
- Merge the units into one Assistant history final.
- Separate text-presentation ACK from audio-degraded state so a successful text
  ACK cannot erase a TTS failure.

**Not sufficient:** raising 4,000 to 8,192, truncation, or client-generated unit
identities outside the authoritative presentation ledger.

**Minimum acceptance:** 4,000/4,001/8,192 characters, Chinese/emoji/combining
characters, second-unit failure and mid-unit barge-in preserve order, exact text,
one history final and honest audio degradation.

### F15 — P2 — SSE limits apply after HTTPX has buffered a complete line

**Evidence:** `jiuwenswarm/server/live_voice/openai_streaming_speech.py:761-772,1812-1864`.

**Required change:**

- Replace `aiter_lines()` with a per-session incremental bounded byte decoder.
- Prefer `Accept-Encoding: identity` plus `aiter_raw`; otherwise independently
  bound decompressed output.
- Enforce line bytes before newline, accumulated event bytes before concatenation
  and line-count/CPU budget before UTF-8, JSON or base64 decoding.
- Preserve one event-level timeout that comments cannot refresh.
- Oversize, invalid UTF-8 and partial EOF publish one content-free protocol
  failure, fence the synthesis session and close its transport with one terminal
  owner.

**Minimum acceptance:** a no-newline stream fails at byte `max+1` with bounded
memory; split CRLF and multibyte UTF-8 work; aggregate multi-line event overflow
fails before join/decode; cancellation leaves no response/session task.

### F16 — P2 — Shutdown evaluates media cleanup before waking active leaves

**Evidence:** `jiuwenswarm/gateway/live_voice/dedicated_media_route.py:359-377,744-758`,
`jiuwenswarm/gateway/live_voice/dedicated_media_registration.py:982-990` and
`jiuwenswarm/gateway/channel_manager/web/web_connect.py:650-791`.

**Required change:**

- Land F06's leaf owner first, then make channel shutdown single-flight and
  phased: quiesce admissions, stop/close sockets and leaves, bounded join,
  close Speech Providers, close diagnostics, close writers and take a final
  resource snapshot.
- Build the stop fence before closing dependencies used by a leaf.
- Record intermediate exceptions, but decide `CLOSED` versus
  `CLEANUP_INCOMPLETE` from final state after all wake-up actions.
- Apply the same shutdown state machine to legacy and Uvicorn/FastAPI servers.

**Not sufficient:** swallowing the old error, lengthening one timeout, clearing
failure unconditionally or closing Providers before their leaf consumers.

**Minimum acceptance:** normal receive/EOT/source/ACK waits close without false
failure; an intentionally uncooperative leaf returns real bounded incomplete;
concurrent stop calls share one outcome.

### F17 — P2 — Recurring tasks cannot reconstruct execution context after restart

**Evidence:**
`jiuwenswarm/agents/harness/common/auto_harness/scheduler.py:368-478,775-807`.

**Required change:**

- Persist a versioned immutable execution descriptor containing stable Agent,
  executor/project and owner references, never process objects or credentials.
- Rehydrate and revalidate the descriptor before claiming an occurrence.
- If configuration is unavailable, retain the recurrence in an explicit
  suspended/blocked state rather than marking it permanently failed.
- Resolve secrets by reference at execution time.
- Live Voice one-time authority cannot be restored from stale process state; its
  occurrence must reacquire authority or remain honestly skipped/blocked.
- Claim, context-ready and occurrence lease require an atomic/single-owner
  transition to prevent duplicate execution during recovery.

**Minimum acceptance:** restarts before and after an occurrence produce exactly
one execution; missing configuration produces zero side effects and recoverable
blocked state; cancellation during rehydration settles cleanly.

### F18 — P2 — Partial Session adapter initialization can leak child state

**Evidence:**
`jiuwenswarm/server/runtime/agent_adapter/interface.py:1099-1110`,
`jiuwenswarm/server/runtime/agent_adapter/interface_code.py:1232-1243` and
`jiuwenswarm/server/runtime/agent_adapter/interface_deep.py:1599-1679,9265-9284`.

**Required change:**

- Enter a cleanup guard before the first allocation-capable await and register a
  cleanup handle as soon as a child exists.
- Use `ABSENT -> INITIALIZING -> READY` and failure
  `FAILED_CLEANING -> ABSENT` states under an initialization lease/generation.
- Coalesce concurrent same-Session initialization onto one future.
- Never cache a failed child as ready. A retry waits for prior cleanup and stale
  cleanup may release only its own generation.
- Shield cleanup from caller cancellation with a bounded deadline and report any
  remaining residue rather than merely clearing the initializing flag.

**Minimum acceptance:** inject failure/cancellation at every create/start/reload
await; no orphan remains and a subsequent call for the same Session succeeds.

### F19 — P2 — Wire serialization admits NaN and infinity

**Evidence:** `jiuwenswarm/common/e2a/wire_codec.py:151-205` and
`jiuwenswarm/server/ws_send.py:42-54`.

**Required change:**

- Recursively reject non-finite floats with `math.isfinite`, including values in
  nested containers and dictionary keys.
- Use `allow_nan=False` at every final JSON sender, including gateway senders.
- On failure, emit a stable content-free envelope containing only separately
  validated routing identifiers; never log or stringify the offending payload.
- Prefer explicit protocol rejection over silently replacing semantic values
  with `null` unless an owning schema defines that projection.

**Minimum acceptance:** NaN and positive/negative infinity at every nesting/key
position cannot produce a frame; every emitted frame is accepted by browser
`JSON.parse` and waiting owners receive one terminal outcome.

### F20 — P3 — L0 binding registry permanently saturates after 1,024 identities

**Evidence:** `jiuwenswarm/server/live_voice/latency_measurement.py:1720-1859`.

**Required change:**

- Replace process-global containers with one `RuntimeL0BindingRegistry` per L0
  run and explicit `register`, `resolve`, `finish`, `close_run` and `snapshot`
  operations.
- Model entries as `ACTIVE -> TERMINAL -> RETIRED`; never evict active entries.
  Terminal entries may leave a separately bounded replay tombstone.
- Return typed registration outcomes rather than an ignored boolean.
- Require the round's unique completion/abort owner to call `finish`; use a
  bounded lease only for missing terminal callbacks.
- Capacity does not fail the product request, but must emit an aggregated,
  content-free saturation/drop fact.

**Not sufficient:** increasing 1,024, blind LRU, clearing globals when an
environment variable changes or silently ignoring registration failure.

**Minimum acceptance:** 10,000 sequential completed rounds remain measurable
with bounded peak storage; 1,025 concurrent active rounds preserve the first
1,024 and return explicit capacity for the new binding; a new run cannot resolve
the old run's identities.

### F21 — P3 — L0 JSONL sink blocks the real-time loop and writes unreadable files

**Evidence:** `jiuwenswarm/server/live_voice/latency_measurement.py:1546-1623,1754-1807`.

**Required change:**

- Introduce one owned `BoundedL0JsonlWriter`; `emit` validates/encodes and uses a
  non-blocking bounded queue, while one writer thread batches writes and fsync.
- Before writing a record, rotate if the resulting segment would exceed the
  reader's 16 MiB limit. Never split a record.
- Finalize each segment through `.partial -> fsync -> close -> atomic rename` and
  expose an ordered manifest with an overall segment/byte budget.
- Queue saturation returns a typed drop and aggregated count without blocking
  the product loop. Disk/permission/fsync failure latches the writer as failed.
- Idempotent bounded close returns accepted, written, dropped, pending and error
  facts. A crash or partial write may leave `.partial`, never a malformed file
  presented as complete evidence.

**Minimum acceptance:** crossing 16 MiB rotates into independently readable
segments; slow fsync does not block event handling; queue/disk/partial-write and
shutdown failure produce accurate incomplete evidence.

## 6. Develop integration blockers

At the frozen baseline, `git merge-tree` found 28 conflicts; 20 were production
code or configuration conflicts. They included Web entrypoints and handlers,
frontend App/ChatPanel/WebSocket lifecycle and types, Agent client/server/manager,
runtime adapters, history, configuration and `uv.lock`.

The conflicts are not 20 additional findings, but they independently block a
direct merge. The integration strategy must be semantic migration rather than
whole-file `ours`/`theirs` selection:

1. Refresh the actual develop ref at implementation time and create a clean
   integration worktree from it.
2. Use develop's
   `jiuwenswarm/server/runtime/session/session_history.py` as the base. Preserve
   its request-completion event/Future, subagent history-path APIs,
   `subagent_id` and FIFO queue semantics; reapply only the required Live Voice
   no-history/idempotency hooks.
3. Use develop's FastAPI/Uvicorn dual-protocol
   `jiuwenswarm/gateway/channel_manager/web/web_connect.py` as the base. Port the
   media path, subprotocol/authentication, transport limits and F06 leaf owner
   into both the default and explicitly retained compatibility paths.
4. Preserve develop's App, ChatPanel and WebSocket lifecycle, then transplant
   Formal feature hooks in small reviewed steps.
5. Resolve dependency declarations semantically and regenerate `uv.lock`; do
   not hand-edit lockfile conflict markers.
6. Re-run production build, affected static checks and risk-tier verification
   only after the conflict-resolved tree exists. Passing the pre-migration branch
   cannot grant integration credit.

## 7. Recommended implementation order and commit boundaries

The 21 repairs should not be squashed into one implementation commit. Suggested
dependency order is:

1. **Develop semantic migration:** resolve the 20 production/configuration
   conflicts without changing product claims.
2. **Atomic interruption and replay:** F01, F02, F03, F08 and F09. Keep browser
   settlement separate from server journal/ledger commits even if reviewed in
   one PR.
3. **Media scope and lifecycle:** F04, F06, F07, F15 and F16. F06 precedes F16;
   F04 must migrate the complete Provider API in one coherent boundary.
4. **Audible ownership and presentation:** F05 and F14. A defensive F14
   fail-fast may land first, but long-response support is incomplete until the
   authoritative producer creates bounded units.
5. **Executor/runtime integrity:** F10, F11, F17, F18 and F19. The minimal F10
   package rejects dirty submodules; recursive dirty-submodule support is a
   separate schema/risk packet.
6. **Privacy, build and L0 evidence:** F12, F13, F20 and F21, preferably as four
   reviewable commits because their owners and failure consequences differ.

Every implementation packet must independently state intended behaviour,
owned production/test surfaces, exclusions, risk tier and zero-forbidden-side-
effect negatives under root `TESTING.md`. This document proposes repairs but
does not authorize a new shared protocol/schema/migration or grant any repair
credit before source, review and required evidence actually pass.

## 8. Final conclusion

The first review found real high-risk defects but overclaimed completeness; that
claim was explicitly corrected. The full second review established a verifiable
191/191 production/runtime ledger and confirmed 21 findings: 13 P1, 6 P2 and 2
P3. Ten first-review findings survived or were strengthened, one was withdrawn,
and eleven additional findings were established by the full audit.

The candidate remains **NO-GO** until the P1 boundaries are repaired, the P2/P3
issues are dispositioned under their owning acceptance, the develop conflicts
are semantically migrated, and the resulting exact candidate passes its own
risk-proportional verification and independent review. This audit alone changes
no current capability status and grants no product, physical or release credit.
