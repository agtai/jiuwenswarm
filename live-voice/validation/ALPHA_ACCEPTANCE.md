# Live Voice W3/W4 Integrated Web Alpha acceptance

> Status: `NOT STARTED`
> Accepted scope: P1 + P2 + P3alpha; complete P3 is stretch
> Architecture: historical [FULL_SOLUTION_2026-07-30.md](../architecture/FULL_SOLUTION_2026-07-30.md), normative [ARCHITECTURE_CONTRACT_GATE_V1.md](../architecture/ARCHITECTURE_CONTRACT_GATE_V1.md), and all applicable current decisions, especially D-046, D-047, D-050, D-052, D-053 and D-055
> Stable package/replacement map: [WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md](../roadmap/WEB_ALPHA_DELIVERY_MATRIX_2026-08-05.md)

This contract decides whether the Integrated Web Alpha scope is complete; `W3/W4` is a delivery-order window, not a current single-lane calendar promise. The accepted carrier is the JiuwenSwarm desktop Web frontend. Chrome/Chromium 107 remains the implementation compatibility floor for modified frontend code, while the candidate must separately name the exact accepted single-desktop-Google-Chrome evidence baseline. D-058 does not turn that evidence into a Chrome+Edge or wider compatibility promise. This is not a mobile/PWA, Firefox/Safari, public compatibility-matrix, RC, or Production approval.

## 1. Candidate boundary

- One immutable candidate contains every runtime, schema, Adapter, flag, fixture, benchmark and documentation input.
- The candidate has a clean worktree and an explicit relation to its development branch/upstream.
- Private Provider/Executor/project/browser/device/network/deployment conditions are recorded without secrets and restored independently of Git.
- All required Tier 3 automated suites and real-path evidence run against this candidate; historical counts or Week 2 evidence are context, not automatic PASS.

## 2. Shared contract Gate

The complete Alpha-consumed ACG boundary must be implemented and conformant:

- versioned identity/scope/authority and Command/Query/Result/Event envelopes;
- committed input and zero partial side effects;
- interaction/turn/response/round/task/attempt state and terminal outcome;
- exact cancel scopes, response generation fence and presentation truth;
- WorkProgress and Context provenance/known-unknown semantics;
- capability/error/fallback and feature-off compatibility;
- the AuthorizationContext, atomic outbox/attempt and restart rules consumed by P3alpha.

Unknown or unsupported facts remain explicit. A legacy v1 Adapter cannot be relabeled as complete v2.

## 3. P1 Gate

Pass the real `browser microphone → browser Audio I/O → STT → existing Chat/E2A → TTS → browser playout` path:

- real browser Audio I/O capture/playout, permission/device lifecycle and immediate exact-response stop;
- Recognition and Synthesis Ports with one real Adapter plus Browser or other declared fallback;
- ordered partial/final/cancel and audio chunk/text-span provenance;
- critical-token and side-effect clarification policy;
- Provider degradation, permission denial and text fallback;
- fixed corpus and real-device measurements with p50/p95, failures and sample count;
- partial Agent/Tool/Task side effects, stale playback and wrong-response stop equal 0.

## 4. P2 Gate

Pass the real `browser microphone → Browser↔Gateway Realtime Media → Conversation Runtime/Interaction Engine → Agent Bridge/Harness → streaming TTS/browser playout` path:

- concurrent bounded media, ACK/backpressure/drop/reorder/close behavior;
- canonical response/generation owner and zero stale UI/audio/history effects;
- natural or documented Alpha barge-in, EOT and stop/revise behavior;
- non-blocking Agent dispatch and source-backed progress under slow Harness load;
- exact playback/presentation facts and history selection;
- background work does not freeze microphone, new Turn or progress notification;
- cross-response/round/task/playback cancellation errors equal 0.

## 5. P3alpha Gate

Pass both structured and committed natural-language routes:

- authorized `create/get/list/status/cancel/events` against formal Task Core;
- stable task/command/attempt IDs, replay/conflict behavior and TaskEvent-only lifecycle truth;
- atomic command/task/event/result/outbox behavior under injected failure;
- one real D0 Executor with attempt dedup, status/cancel and capability/outcome truth;
- voice/Session disconnect does not stop a task while application/Executor remain alive;
- restart reconciliation produces exact active/terminal/interrupted/unknown/pending facts without silent rerun;
- committed Voice–Task Bridge resolution, clarification and confirmation;
- TaskEvent-derived WorkProgress returns to voice through Runtime and text through Chat/UI Adapter without becoming direct TTS or Chat lifecycle truth;
- wrong-task/scope mutation and partial command effects equal 0.

Full-P3-only operations must return explicit `unsupported` unless a separately reviewed stretch implementation and acceptance extension exists.

## 6. Joint P2/P3alpha Gate

Run one slow conversational Harness round and one detached task concurrently while the user continues multiple voice Turns, interrupts/revises the current response, queries or cancels the exact task, and receives blocked/decision/terminal progress.

Pass requires:

- media and microphone remain bounded and responsive;
- response interruption never cancels the task, and task cancel never stops playback/response/round;
- new conversational requirements target the correct round/response and task commands target the correct task/attempt;
- WorkProgress source correlation is 100%; terminal outcome is exact;
- slow Harness synchronous wait on the realtime hot path is 0;
- partial speech mutations and stale post-fence effects are 0.

## 7. Web platform and degradation Gate

- freeze the desktop-browser scope before candidate testing and run the complete candidate on every browser/version in that declared baseline; an absent or changing baseline is `BLOCKED`, and exact browser, OS, origin, device and network labels are evidence rather than a public compatibility promise;
- non-localhost deployment uses HTTPS/WSS or an equivalent secure context; localhost remains a development/controlled-test exception only;
- microphone grant, denial and revocation; device selection and `devicechange`; input/output loss; autoplay/user-activation; page hidden/background/resume; refresh/reconnect and visible diagnostics have no silent failure or stale audio resurrection;
- the selected browser capture/playout implementation, media encoding and Browser↔Gateway transport are documented with capability and fallback provenance; unsupported behavior remains explicit;
- Gateway/AgentServer proxying, CSP, CORS and WebSocket/transport routing work in the declared deployment topology; Browser code contains no long-lived Speech/model Provider credential;
- selected real Provider and Executor failure profiles are exercised;
- feature/capability off and permission/Provider/media failure preserve the text product path;
- route/metric traces can reproduce the declared Alpha targets or record an explicit accepted Alpha deviation;
- raw audio is not persisted by default, and no credentials, raw secrets or unauthorized content appear in browser storage, URLs, logs, Context, TaskEvent, WorkProgress or speech evidence.

## 8. Final decision

Sol reviews the actual diff, grouped Tier 2/3 evidence, exact candidate, unresolved gaps and every accepted deviation. Result is one of:

- `PASS — INTEGRATED WEB ALPHA`;
- `PARTIAL — candidate runs but one or more committed Gate requirements remain`;
- `BLOCKED — required external condition or authority decision is unavailable`;
- `FAIL — candidate violates a committed invariant or cannot run the required real paths`.

Production authentication, full P3, D1/D2, mobile/PWA and browsers outside the accepted Alpha baseline, public compatibility promises and RC hardening remain separate even after PASS.
