# Live Voice current status

> Updated: 2026-08-15
> This is the only mutable source for current branch expectations, stage/task,
> blockers and next actions. Git is the implementation fact; detailed S7 facts
> are in the linked review record.

## Resume capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `origin/hx/0812_live_voice_w3`. The branch was pushed through `a53856de`; the
  S8-readiness integration and S7 re-freeze are local and no additional push is
  authorized.
- `S6 - Alpha Module Closure` / `A1` remains `CLOSED`. All S6-01 through
  S6-06 rows remain `SATISFIED` and the last physical closure is recorded by
  [D116](D116_S6_02_PHYSICAL_CLOSURE_2026-08-13.md).
- `S7 - Candidate Assembly, Verification and Review` / `A2` closed for exact
  candidate `500700501f06dec9a27fda99fdaf73d5ac123d2c`: the external sanitized
  report and `live-voice.s7-a3-handoff.v1` validated the clean HEAD, required
  lineage, 40 automatic `PASS`, five real `VERIFY`, S7-03 `PASS` and
  `FROZEN_FOR_A3`.
- Formal S8 began on that frozen candidate. The human journey produced useful
  product truth but is now `PAUSED / SOURCE REPAIR`. Provisional discovery found
  the two earlier lifecycle defects plus nine additional product defects: ASR
  correction was locked during confirmation; ordinary text/Tool work serialized
  formal voice; P3 mutation failures hid their stable reason; a definitive
  natural-language intent rejection retained the form until reload; status did
  not project terminal task truth; retry eligibility ignored current checkout
  and Executor cleanup truth; the product P3 query Adapter dropped that
  authoritative retry admission; Web reconnect could sleep too long after
  runtime recovery; and a complete AgentServer restart reset one interaction's
  response generation. Continued automated discovery added three more findings:
  an idle P2 notification poll crossed the Gateway's ten-minute unary ceiling
  and surfaced a false product failure; natural-language task creation activated
  progress before establishing an exact Task leaf, so authenticated progress was
  dropped; and exact full-P3 `pause` / `resume` forms were misclassified as open
  clarification instead of a definitive unsupported result.
- The cumulative repair keeps the Gateway stale-response fence intact,
  revalidates the exact active P2 binding before explicit media Start, separates
  the formal P2 Agent facade from ordinary Web work, and owns response generation
  in a bounded SQLite sidecar derived from the authoritative Task Store so it
  survives AgentServer restart without retaining raw product IDs. The UI keeps
  recognized text editable before commit, consumes authoritative retry admission
  and stable failure reasons, projects terminal Task truth, unlocks after an
  exact server rejection, and bounds reconnect delay to two seconds. The exact
  affected suites currently pass 332 integrated Web tests and 184 backend
  product/Task/durability tests; Python Ruff, format and diff checks pass, and
  the production frontend build completes 4,640 modules. The committed 16-path
  repair and the subsequent product-status Adapter and real-resolver
  stable-reason corrections each received affected Tier-3 `APPROVE`, with no
  open Critical, High or P2 finding. The product repair is committed through
  exact `5d79f47bd915f24f9948593ff6fd9ec392dc1bdd`, with current-state documentation
  through `8c2dccc82a2845653ccc0aaab77f972b4296fe29`; neither is the final frozen
  candidate. The newest ten-path working delta returns effect-free P2 keepalives,
  rejects the known full-P3-only forms explicitly, and gives natural create a
  content-free post-receipt checkpoint. A replacement progress owner is now
  published only after exact Task status, complete event history, authoritative
  retry admission and durable task-target storage all validate; reload recovers
  by query and never resends create, the receipt's real task-control generation
  is preserved, generic target recovery yields to the richer post-create CAS,
  and structured mutation stays locked while that handoff is unresolved. A
  failed replacement preserves the previous exact Task leaf. Its affected
  suites pass 335 integrated Web tests,
  120 backend product/intent tests and the broader 87-test authenticated P3
  composition suite; Ruff, Prettier, Python format and diff checks pass. The
  independent reviewer found the post-receipt handoff P2 in the earlier delta;
  the repaired ten-path boundary then received affected Tier-3 `APPROVE` with
  no open Critical, High or P2 finding and was committed as exact
  `005814b7f6e430dacc83ecd3c5291aea719f067d`. That commit is a diagnostic S8
  source candidate, not a frozen S7 handoff. Complete S7
  re-verification/re-freeze and a fresh
  formal S8 closeout remain mandatory before any
  `PASS - INTEGRATED WEB ALPHA` result.
- Automated diagnostic S8 on `005814b7` rebuilt and served the 180-file
  frontend with the reviewed Integrated P1/P2/P3 flags, restarted the private
  AgentServer/Gateway/WebChannel/Caddy topology. Real browser checks passed P2 text/Agent response, P2 independence
  from a concurrent 15-second ordinary Web Tool call, explicit ambiguous and
  unsupported natural-Task rejection, exact status projection, two-turn cancel
  confirmation with zero Task effect, and visible structured-P3 dirty-worktree
  rejection without a stuck form. A controlled service restart failed the old
  authorities closed; refresh restored P1/P2/P3 with the same interaction's
  response generation increasing from 1 to 2, and a following P2 turn passed.
  The isolated Store remained at eight terminal tasks/eight attempts/nine
  delivered outbox rows with no new Task mutation. A diagnostic S8 entry audit
  against the historical `8c2dccc8` handoff returned the required
  `CANDIDATE_IDENTITY_MISMATCH`; none of these discovery events are formal A3
  evidence.
- The first real structured-P3 Executor attempt then exposed an OpenJiuwen SDK
  compatibility defect before any model or fixture effect: JiuwenSwarm passed
  the optional `ReasoningToolLoopCompactProcessor` override even though the
  installed preset does not provide that processor, so Code Agent construction
  failed closed. The working repair capability-checks the installed preset in
  both single-agent and Team builders, skips only the unsupported optional
  override, and keeps the override when a supporting SDK is present. Focused
  compatibility tests pass 6/6, the complete affected Agent/Team files pass
  91/91, and the P3/Task/Executor regression set passes 253 with two existing
  platform skips. The rebuilt private runtime then completed one real structured
  P3 create through accepted, running and terminal UI truth: only the authorized
  `notes.txt` line changed, while Task, attempt, outbox and Direct Executor state
  all settled without a retained owner or lease. Affected independent review
  approved the six-path boundary with no open Critical, High or P2 finding. The
  repair is committed as exact `d057b2d1fee1371bc4ed070caf36a7b6125b0eda`;
  it is a diagnostic source candidate, not a frozen S7 handoff.
- By explicit user direction, the already observed scope-correlation mismatch
  is retained as a non-blocking provisional S8 deviation for final human
  judgment. Continued S8 work before re-freeze is discovery only; its events
  cannot be relabeled as exact-candidate formal acceptance evidence.
- Further automated diagnostic S8 on the rebuilt runtime verified that a
  controlled service restart left one exact P3 attempt `terminal/interrupted`,
  released its owner and lease, made no fixture change and recovered the same
  task in the refreshed UI without duplicate dispatch. A P2 turn returned and
  remained visible while an independent P3 attempt was running; a structured
  retry then created exactly attempt 2, completed the authorized `notes.txt`
  change, exposed `TASK_CONTEXT_WORKTREE_DIRTY` before another retry and was
  restored to the exact CRLF fixture baseline.
- The next exact natural-language create used the required second committed
  confirmation, survived a receipt-time page refresh and recovered the same
  single task/attempt/progress route with no duplicate create. Its positive
  Executor result nevertheless failed closed as
  `PROJECT_CHANGE_ATTRIBUTION_FAILED`: the installed Windows Git has
  `core.autocrlf=true`, the Agent's `write_file` produced LF in the isolated
  checkout, and application to the real project restored CRLF, so the former
  raw-byte-only attribution proof rejected the semantically exact Git patch.
  The current Direct Executor source/test repair keeps raw-content equality as the first
  proof and, only for an exact clean target baseline, also persists the complete
  HEAD-relative binary patch fingerprint using a temporary index that never
  mutates the real index. Extra or foreign content, malformed evidence and
  restart ambiguity still fail closed. The two focused CRLF/application and
  restart tests pass; the complete Direct Executor file plus Agent/Team
  compatibility regressions pass 171 tests with two Windows-platform skips, and
  all 87 authenticated P3 composition tests pass. Direct Executor source/test
  Ruff and formatting, all changed-Python Ruff plus W605, compileall and the
  exact 21-diagnostic S7 baseline pass. The already changed legacy Agent Adapter
  now carries exact per-import E402 suppressions rather than a file-wide waiver,
  so future diagnostics remain visible. Affected Tier-3 independent review
  approved the four-path boundary with no open Critical, High or P2 finding,
  and the repair is committed as exact
  `35346ac598efe4a848f6530c58eb50f7efc1ec35`. The rebuilt-runtime positive
  natural-create rerun and remaining diagnostic S8 discovery are still pending;
  S7-04 remains `REFREEZE REQUIRED`.

The active execution contract is the
[S5-S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md), the completed S7
packet is
[S7_EXECUTION_PACKET_2026-08-13.md](roadmap/S7_EXECUTION_PACKET_2026-08-13.md),
and the detailed result is
[S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md](S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md).

## S7 dashboard

| Task | Status | Current fact |
|---|---|---|
| S7-01 selective port and candidate freeze | `SATISFIED` | The S7-owned runner, five probes, tests, documentation and frontend script registrations were selectively adapted from `d2727f20`; broad formatting, stale D113 and stale Streaming Speech copies were dropped. The repaired product source is `c209e4a6`. |
| S7-02 automation | `SATISFIED` | The readiness candidate and exact documentation handoff each receive all 40 automatic checks. The source-candidate run completed backend Alpha 1,635 passed / 2 skipped, related regressions 788 passed, 27 frontend commands 847/847 passed and production build 4,640 modules; exact Ruff debt, format/compile, diff/link/hygiene and post-run identity passed. The ignored build froze 180 files / 16,275,167 bytes and private 443 served all 180 exact contents. |
| S7-02 real path | `SATISFIED` | All five probes returned `VERIFY` on one private-only HTTPS/WSS runtime declaration: Speech/Media 5 samples, Agent/Executor 2, Benchmark/Fault 65, Secure Deployment 3 and Privacy 19; failures and forbidden side effects were zero. Speech/Media p50 was 18,188.395 ms and p95/max 19,001.572 ms. |
| S7-03 cumulative Tier-3 review | `SATISFIED` | Cumulative main review and independent read-only review found no open Critical/High/P2 source issue. The S8 readiness boundary closed strict topology/port, S7 report, Task Store/Direct settlement, trace, human-observer and ignored-build/served-content findings; independent exact-`e58df618` verification passed 112 tests. |
| S7-04 A3 handoff freeze | `REFREEZE REQUIRED` | Exact `50070050` was frozen and admitted S8. The current lifecycle repairs change source, so that handoff is now historical and a final exact-clean-HEAD report/handoff must be regenerated after provisional discovery. No public deployment or real-user project is permitted. |

The table records the last closed S7 line. The current source-repair tree
supersedes that candidate for further product work and therefore returns S7-04
to `REFREEZE REQUIRED` until the final batched S8 findings are repaired and the
complete S7 verification/handoff is regenerated.

## S7 accepted limitations

- The controlled Browser bridge could not read origin storage APIs. The privacy
  probe scanned all 19 supplied external capture surfaces against credential,
  PCM16 and authoritative f32le raw/base64 sentinels and found zero forbidden
  persistence, but A3 must still inspect the user-visible browser storage and
  lifecycle behavior rather than treating bridge unavailability as a broad
  browser-forensics guarantee.
- A duplicate unary request ID at the Web transport boundary failed closed with
  a bounded no-response result and zero repeated mutation, rather than returning
  an explicit conflict envelope. Product-layer automated tests retain explicit
  replay/conflict coverage. A3 must continue to judge visible product behavior,
  not transport diagnostic wording.
- The deployment is a private-address-only FQDN with trusted same-origin
  HTTPS/WSS. S7 makes no public-deployment, Production-authentication, wider
  browser/mobile/PWA, RC or audit-grade claim.

## Frozen product boundary

- Gateway-only key: `LIVE_VOICE_SPEECH_API_KEY`.
- Speech: official OpenAI origin,
  `gpt-4o-mini-transcribe-2025-12-15`,
  `gpt-4o-mini-tts-2025-12-15`, voice `marin`.
- Degradation: Streaming -> W2 Batch -> Browser/text, explicitly identified.
- Agent: JiuwenSwarm Agent Provider. P3alpha: formal Task Core,
  `DirectProjectCodeExecutorAdapter`, disposable no-remote local Git fixtures.
- Deployment: private same-origin HTTPS/WSS; no public deployment.
- The D107 migration corrections remain authoritative. Do not restore signed
  Gate tooling, Replacement Ledger, fixed manifests, migrated APIs or
  `schedule.*` as P3alpha Task authority.

## Next actions

1. Rebuild the private runtime from exact `35346ac5` and repeat exact natural
   create plus receipt-time refresh against that clean source.
2. If the real rerun passes, resume user-directed S8 discovery using Chrome,
   Computer Use, sanitized logs, Store/Executor inspection and other automated
   observers. Record non-blocking findings through the pass,
   batch-fix them, and repeat until only physical audio/device and final human
   judgment remain; provisional events are never relabeled as formal proof.
3. Run the complete S7 runner, five real probes, cumulative Tier-3 review and
   external handoff freeze on the final exact clean HEAD after the last source
   repair.
4. Run a fresh exact-candidate S8 entry audit and all automated acceptance, then
   hand the remaining physical product journey to the user for the final
   `PASS`, `PARTIAL`, `BLOCKED` or `FAIL` decision under
   [Alpha acceptance](validation/ALPHA_ACCEPTANCE.md).
