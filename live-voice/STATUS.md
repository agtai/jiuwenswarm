# Live Voice current status

> Updated: 2026-08-16
> This is the only mutable source for current branch expectations, stage/task,
> blockers and next actions. Git is the implementation fact; detailed S7 facts
> are in the linked review record.

## Resume capsule

- **Current result:** `IMPLEMENTED / S7-A2 AUTOMATION + REVIEW PASS / S8-A3
  PHYSICAL ACCEPTANCE PENDING` for the Shared-X + P1/P2/P3alpha Tier-3
  running-adjustment and terminal-notification batch. The exact implementation
  candidate is `3bc7f9345f5b3832367e0a34b0dee8853d3d2c02` on
  `hx/0812_live_voice_w3`, four local commits ahead of
  `origin/hx/0812_live_voice_w3`. No remote-ref update has been performed. A
  later documentation-only status commit does not change this tested product
  source.
- **Product behavior now implemented:** one click starts a generation-fenced
  hands-free loop; authoritative ASR final is automatically submitted exactly
  once to the independent `live_voice.composition.unified.submit` owner.
  Partial/interim speech has zero Agent, Task or presentation effects. The
  visible panel retains enable, status, transcript and Exit, while Send,
  Agent/Task, operation and Task-ID controls are absent. The six closed routes
  are `dialogue`, `background.create`, `background.update`,
  `background.query`, `background.status` and `background.cancel`. Create and
  update use distinct high-confidence full-utterance grammars; ordinary
  non-task questions, ambiguity, negation and low confidence have zero Task
  effects, while explicit result/progress/adjustment-status questions retain
  their query/status routes.
- **One-current-task boundary:** Task Store schema v3 owns the
  subject/project/Session current pointer, restores it across activation
  rollover/page refresh, and performs current check + Task/attempt/outbox
  creation + pointer update in one SQLite transaction. A second concurrent or
  sequential create while the current Task is non-terminal produces zero new
  Task side effects. This batch intentionally does not implement multiple
  concurrent background tasks.
- **Running adjustment boundary:** schema v3 is sufficient; no v4 migration or
  adjustment table was added. An authenticated `task.adjust` command creates an
  ordered adjustment outbox item and authoritative
  `task.adjust_requested/applied/rejected` events. The Direct Executor consumes
  each request at a real pre-terminal checkpoint, and only a persisted
  `applied` event may support a claim that the final artifact includes the
  change. Terminal Tasks and immutable historical results reject adjustment;
  no successor revision is created automatically.
- **Result boundary:** immutable `task_results` are keyed by
  task/attempt/source-event identity. Only a completed Task with an applied,
  attributable patch and verified bounded artifact path/SHA can be
  `available`; running work is `not_ready`, and failed/cancelled/interrupted or
  invalid artifacts are `unavailable`. Query enters the existing P2 Agent
  facade only for `available`; the other states receive authoritative bounded
  presentation without Agent speculation. Result/artifact data is untrusted
  reference context, is not ordinary-log material, and grants no instruction
  or tool authority.
- **Authority and durability:** old `p2.submit(agent|task)`, P2 journal,
  activation recovery and `task.status/events` contracts remain unchanged.
  Unified submission validates final speech, current P2 activation, Session and
  Gateway voice claim before semantic parsing. Its independent SQLite journal
  provides request/content conflict detection, same-voice replay, leases and
  crash recovery. P3 flag-off or insufficient authority fails closed without
  Agent fallback. Demo create/cancel confirmation bypass is available only
  through the explicit trusted backend policy
  `JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED`. In the isolated
  Demo the same backend-owned flag also authorizes a distinct
  `trusted_demo_bypass` for exact authoritative finals containing critical
  tokens such as itinerary day numbers, avoiding the production clarification
  prompt. Neither path fabricates or claims user confirmation; scope,
  idempotency, target binding and mutation authority still apply. With the flag
  unset, the production confirmation and critical-input policies are unchanged.
- **Hands-free lifecycle:** Agent and Task presentation completion schedule one
  successor capture; one coordinator owns capture start/stop; Exit advances a
  loop-generation fence so late callbacks cannot reopen the microphone. A
  later explicit enable creates a new generation. Real server speech-start/EOT
  during playout interrupts the current P2 response/TTS only and asserts zero
  Task cancellation/mutation.
- **Terminal notification boundary:** the terminal TaskEvent is the stable
  durable identity, but product delivery acquires the current valid P2
  activation and a fresh response generation. It never reuses the superseded
  task-create response. Existing presentation/ACK/TTS and replay semantics are
  reused: ACK suppresses later delivery, while a crash after playout but before
  ACK may replay. Only `completed` plus a legal TaskResult announces completion;
  failed, cancelled and interrupted outcomes remain distinct and truthful.
- **Automated verification:** on exact implementation source `3bc7f934`, the
  serial cumulative backend matrix passed `1,776` with `2` expected Windows
  symlink skips and one Authlib deprecation warning; Integrated Web passed
  `374 / 374`; the post-format affected backend set passed `324` with the same
  `2` skips; the mounted stale-TTS Session-switch regression passed; Ruff,
  Ruff format check, Python compilation, `git diff --check` and the production
  build (`4,642` modules) passed. Existing Vite chunk/dynamic-import and
  duplicate i18n `empty` notices remain non-blocking. The coherent-batch cold
  review and new independent read-only Tier-3/scoped-Sol post-review have no
  open P0-P3 source findings. See [D119](D119_RUNNING_TASK_ADJUSTMENT_AND_TERMINAL_NOTIFICATION_REVIEW_2026-08-16.md).
- **Physical acceptance:** not yet run on the exact candidate. The protected
  host configuration contains a Speech key binding, but provider/model runtime
  readiness has not been established and ports 18092, 19000, 19001, 3000 and
  5173 currently have no listeners. No credential is moved into chat or Git.
  The exact seven-step D119 itinerary Journey, including intervening dialogue,
  a truly non-terminal update, applied-before-terminal evidence, current-
  generation announcement, artifact inspection and disposable-fixture cleanup,
  remains required before S8/A3 product acceptance can pass.

## Superseded pre-implementation capsule (historical)

- **Current result:** `IN PROGRESS — POST-ALPHA DEMO COMMAND CENTER DELTA` on
  clean base `ff2c3b746`. The uncommitted product delta moves formal
  Agent/Tool and P3alpha `task.create` / `task.status` / `task.cancel` controls
  into the bottom Live Voice surface. Recognized speech remains editable but
  now dispatches with one explicit Send action; the redundant raw-ASR
  confirmation card is not used by this product entry. Backend-owned spoken
  confirmation for Task create/cancel remains mandatory and visible.
- **Delta verification:** the affected Integrated Web suite passes `351 / 351`,
  including mounted single-action Agent dispatch, formal voice Task create,
  spoken Task confirmation, exact progress activation and command-center UI
  coverage. The production frontend build completes `4,641` modules both with
  defaults and with the formal `INTEGRATED_WEB` / `INTEGRATED_P1` /
  `PRODUCT_P3_MUTATION` flags enabled while compatibility flags remain off. A
  fresh physical browser/microphone demo acceptance has not yet run on this
  dirty source, so the delta is not accepted or committed.
- **Delta review:** implementation self-review and a cold complete-diff review
  found no remaining blocking issue after the raw-ASR confirmation UI was
  removed from the bottom bar. An independent `/review` entry is unavailable
  in this session; the substitute is a second complete-diff inspection plus
  affected tests/build, and is not represented as an independent review.
- **Current-host launch boundary:** the repaired `.venv` imports
  `openjiuwen.symphony` successfully, but the previously private ephemeral
  `LIVE_VOICE_SPEECH_*` provider settings are not present in the current
  process or the user runtime `.env`. Full microphone/STT/TTS launch therefore
  still requires the user to re-enter the Speech credential through a
  protected terminal; it must not be requested in chat or inferred from the
  Agent provider configuration.
- **Prior accepted result:** `PASS — INTEGRATED WEB ALPHA`. On 2026-08-15 the
  user completed the current-host physical microphone, heard playout, voice
  barge-in, device/permission and continuous joint journey and explicitly
  returned `PASS` for S8-03. That acceptance applies only to the tested source
  below and does not pre-credit this post-Alpha UI delta.
- **Exact tested source:** `d33b520e0d21ae0829d30814d77a01cc18256f09`
  on `hx/0812_live_voice_w3`. Phase D′ destination transfer was not used. The
  exact S7 report SHA-256 is
  `3f4b0e348152a56bb9accb82c00ff47392bd8ccdb0212f06f3ac80d397f4ee2b`;
  the runtime declaration SHA-256 is
  `9aaa37fe01dd6c4cd7b664d9416f3c000767c96f89ad6904a9c34f70ebc0bbe2`.
- **Accepted deviations:** F-001 through F-005 remain recorded in the
  [fast-closeout ledger](S8_FAST_CLOSEOUT_LEDGER_2026-08-15.md). They are not
  repaired or silently relabeled. F-001 prevents the strict S8 helper from
  crediting the product-generated correlation as the pre-generated
  correlation; the fail-closed template is preserved and no validator PASS is
  claimed. The user's final decision consumes that explicit accepted deviation
  plus the separately bound machine and physical observations.
- **Cleanup:** five product-session Tasks/Attempts/Direct Executor rows are
  terminal, seven outbox rows are settled, and all owner/lease state is
  released. Dedicated AgentServer, WebChannel, Gateway and private proxy
  services are stopped; ports `18092`, `19000`, `19001` and `443` are released.
  The no-remote fixture contained only the planned `notes.txt` effect and was
  moved to the Windows Recycle Bin. Private external acceptance artifacts are
  retained. The tested source worktree did not change during A3. The external
  user-decision record SHA-256 is
  `e34dea559c3829f7624b3c340fdeab83f1f6a744ae118ca9bf1dd5f45f90ac16`;
  the final cleanup record SHA-256 is
  `e79c130a4b145ccbb0f21a04cf6ce78c85bd2a7c297789368e156f11297aee03`.
- **Branch/remote:** local `hx/0812_live_voice_w3` and its upstream
  `agtai/hx/0812_live_voice_w3` are synchronized at exact `ff2c3b746`. The
  remote already contains the C1/C2 and final closeout documentation; this
  resume operation fetched and fast-forwarded the existing W3 worktree and did
  not push or otherwise update a remote ref.
- **Non-claims:** this PASS does not claim full P3, Production authentication,
  broad browser/mobile support, public deployment, or RC/Production readiness.

## Historical execution capsule

- Expected branch/upstream: `hx/0812_live_voice_w3` /
  `agtai/hx/0812_live_voice_w3`. Both refs resolve to final docs-only closeout
  tip `ff2c3b746`, which follows C1 settlement `c04033380`, F-005 re-settlement
  `d33b520e0` and the final closeout record. The remote advance was observed by
  fetch; this resume operation did not perform it.
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
  natural-create rerun then passed: receipt-time refresh recovered one exact
  task/attempt/progress route, the task completed once, Store/outbox/Direct
  state settled, and the authorized `notes.txt` Git patch matched the persisted
  `content-v2` attribution before the disposable fixture was restored clean.
- A later P1 retry exposed a private-runtime configuration mismatch rather than
  a product media defect. The launch environment named the private FQDN, but
  the isolated data-root `config/.env` reloaded the older localhost-only Origin
  allowlist and strict media activation returned `MEDIA_ORIGIN_REJECTED` while
  P2/P3 and ordinary text remained usable. The private user/data-root
  allowlists were corrected, all four services restarted healthy, and Chrome
  then entered `Listening through formal P1`; the Gateway accepted the exact
  same-origin fixed media path and non-legacy route. The diagnostic capture was
  exited without committing speech. Final runtime preparation must preserve
  and verify this authoritative data-root Origin binding. No product source
  change was needed.
- Final candidate assembly then advanced to exact clean source candidate
  `2b8f19146cb1c0d979c602afb3a8f445d71cbd4d`. A fresh isolated private runtime
  passed HTTPS/WSS, real Agent, formal Speech/Media, Task/Executor, fault,
  deployment and privacy preparation. The five real probes independently
  returned `VERIFY` with `5 / 2 / 65 / 3 / 19` samples and zero failures or
  forbidden effects. The first complete runner passed all automatic checks but
  rejected a BOM-prefixed external privacy manifest; the corrected no-BOM
  capture then passed privacy without a product-source change. A second complete
  runner passed all five real probes and every automatic check except one
  Observability cleanup timing test: under the full 1,663-test backend load its
  second 20 ms close attempt raced the already released worker. The exact test
  passed 40 isolated repetitions, and the one-test working repair now waits on
  the public worker-terminal snapshot with a one-second test oracle before
  retrying retained root cleanup; product timeouts and source behavior are
  unchanged. The complete affected file passes 27/27 with Ruff, format and diff
  checks clean. The repair received affected Tier-3 `APPROVE` and was committed
  as exact `5ee3cb29748f93db437574e4e9256628e09a9892`. A fresh exact-`5ee3cb29`
  full runner then exited zero: backend Alpha passed 1,663 tests with two skips,
  related regressions passed 789 tests, Integrated Web passed 335/335, the
  production build completed 4,640 modules, and the exact 40 automatic checks
  plus five real probes returned `PASS` / `VERIFY` with `5 / 2 / 65 / 3 / 19`
  samples and zero failures or forbidden effects. The post-run candidate was
  clean. This current-authority documentation commit changes the exact Git
  identity once more, so it must receive one final exact-current-HEAD runner,
  cumulative review and external handoff without another tracked edit.
- Exact clean `9697e5929e3beb3eb18044f522eff30ac6b53387` subsequently
  completed that final runner and external-only freeze. Its sanitized report
  bound 40 automatic `PASS`, five real `VERIFY`, the runtime digest and clean
  candidate identity; the handoff bound that report and recorded S7-03 `PASS`
  plus S7-04 `FROZEN_FOR_A3`. S7/A2 is therefore complete for exact `9697e592`.
- Fresh S8 automation then found one further product defect while inspecting a
  historical interrupted Task: the UI reused the currently selected Task leaf,
  so a valid historical Task with a different correlation failed generically
  before authoritative event inspection. The repaired two-path boundary creates
  and fully validates a candidate leaf, then atomically replaces the old leaf;
  it performs no Task mutation during inspection. An injected replacement
  failure preserves the old leaf and journal, while a deferred competing
  inspection cannot publish after a newer generation wins. The repair was
  independently approved and committed as exact
  `00584736030e5c2e91ae69d07a7b27207eb2a12b`. On that clean exact candidate,
  Integrated Web passed 337/337, the production build completed 4,640 modules,
  the complete S7 runner exited zero, all 40 automatic checks passed, and the
  five real probes returned `VERIFY` with `5 / 2 / 65 / 3 / 19` samples and zero
  failures or forbidden effects. Its affected and cumulative Tier-3 reviews
  found no open Critical, High or source/test P2 issue. The stale wording in
  this paragraph was the sole remaining documentation P2. This documentation
  correction changes the exact Git identity, so only the resulting clean
  docs-only successor may receive the final runner, review confirmation and
  external `FROZEN_FOR_A3` handoff; the historical `9697e592` freeze cannot be
  reused for formal acceptance.
- The resulting exact clean candidate
  `83660aef4f8e748e2c321d4ccc0ef03111256b9b` completed that runner, cumulative
  review and external-only freeze: backend Alpha passed 1,663 tests with two
  skips, related regressions passed 789, Integrated Web passed 337/337, the
  production build completed 4,640 modules, and all 40 automatic checks plus
  five real probes passed with `5 / 2 / 65 / 3 / 19` samples, zero failures and
  zero forbidden effects. Fresh automated S8 then passed ordinary and formal
  P2 Tool work during an independent slow Tool call, exact P3 create/status/
  cancel/restart reconciliation, three P2 turns, wrong-task rejection, clean
  Store/Executor settlement and privacy/log scans. It found one remaining P3
  progress recovery defect: after a P2 successor, a historical Task route used
  the current P2 correlation and reset its browser generation on reload. The
  coherent repair binds progress to the persisted Task correlation and
  allocates every exact Task route from a bounded, Web-Lock-protected,
  credential-free same-tab generation journal before server activation. Exact
  route-switch/remount, corruption, capacity, contention, malformed or
  unavailable persisted targets, and zero-mutation regressions are included.
  The repair was committed under the pre-documentation identity
  `e41e856ba93bee0301a0c91cab70eff8b6679e06`: Integrated Web passed 345/345,
  the production build completed 4,641 modules, affected and cumulative Tier-3
  source/test review found no open Critical, High or P2 issue, and its complete
  S7 runner passed 40 automatic checks plus five real probes with
  `5 / 2 / 65 / 3 / 19` samples, zero failures and zero forbidden effects. This
  STATUS correction changes the exact Git identity, so that pre-documentation
  run is intermediate evidence only; the resulting exact clean candidate must
  receive the final report, brief identity/review confirmation and external
  re-freeze. The exact `83660aef` freeze also remains historical.
- Exact clean `9a6715da48a5b0ef51ff46dcb82a07f9478bebb3` subsequently
  completed the full runner, cumulative review and external-only
  `FROZEN_FOR_A3` handoff and became the latest historical frozen candidate.
  Fresh automated S8 discovery then reproduced one additional UI recovery
  defect: after a definitive structured-P3 rejection such as
  `TASK_ALREADY_TERMINAL`, the visible controls unlocked but a stale local
  pending-mutation reference silently suppressed the next natural-language Task
  submission until page reload. The current two-path source/test repair clears
  both pending references only when the product owner proves that no mutation
  remains pending; transport-unknown outcomes stay retained and locked. The
  mounted regression and the complete Integrated Web suite pass `349 / 349`,
  Prettier and diff checks pass, and the Integrated-Web production build
  completes `4,641` modules. In the real private Chrome surface the same
  terminal cancel failed with the truthful stable reason, and without reload an
  ambiguous natural request immediately reached
  `TASK_INTENT_EXACT_FORM_REQUIRED`; the isolated Store remained at one Task,
  one attempt, one command and one delivered outbox row. The repair receives
  current-candidate credit only when an exact clean HEAD containing it has
  affected and cumulative review credit plus a valid report and frozen handoff;
  until then formal S8 is paused and exact `9a6715da` remains historical
  evidence only.
- Exact clean `d31cc7bb00e3357db32d0a5cd864680d35330003` contains that
  definitive-rejection repair and subsequently completed the full S7 runner,
  cumulative review and external-only `FROZEN_FOR_A3` handoff. Its report bound
  all 40 automatic `PASS`, five real `VERIFY`, the exact runtime digest and a
  clean candidate; affected and cumulative review found no open Critical, High
  or P2 issue. Fresh diagnostic S8 on `d31cc7bb` exercised real formal P1/P2/P3,
  Task create/status/cancel/retry, concurrent ordinary Tool work, restart
  reconciliation, Store/Executor settlement and privacy/log inspection. It
  exposed one remaining blocking product gap: a second formal P2 turn could see
  the prior response in the page but the real isolated Agent received an empty
  CR context snapshot and therefore could not answer a simple follow-up. The
  current source/test repair keeps the no-history Agent seam and instead selects
  at most four recent same-interaction pairs consisting only of committed user
  text plus assistant TEXT spans that CR actually marked presented. It binds
  each immutable entry into the next `TurnCommit`, excludes Tool/reasoning/raw
  audio/unacknowledged output, caps selected content at 32 KiB and fails closed
  on retained-content mismatch. A canonical typed identity digest includes the
  exact interaction plus turn/commit or response generation and drives both the
  stable ID and logical URI; the content digest remains the immutable snapshot
  revision. The complete
  affected Runtime, P2 Adapter, product Registry, Bridge, formal Agent facade
  and D90 vertical suites pass `257 / 257`. The earlier complete Live Voice
  unit run passed `1,649` tests with two existing Windows-platform skips; the
  five added authority/boundary cases also pass in the current affected run.
  The source/test boundary has independent affected Tier-3 approval with no
  open Critical, High or P2 finding; that credit applies to an exact clean
  committed candidate only when its committed diff matches the reviewed
  boundary. Because this repair changes source, the `d31cc7bb` freeze is
  historical. Formal S8 remains paused unless the exact-current candidate also
  satisfies the report/review/handoff conditions below; otherwise full S7
  re-verification/re-freeze remains mandatory.
- Exact clean `8ce8e0c4b1191efc4306f3493dd3d9943abd99ba` commits that
  acknowledged-context repair. Its complete S7 runner returned all 40 automatic
  checks as `PASS` and all five real probes as `VERIFY` with `5 / 2 / 65 / 3 /
  19` samples, zero failures and zero forbidden effects; its affected and
  cumulative Tier-3 reviews found no open Critical, High or P2 issue, and the
  external handoff recorded S7-03 `PASS` plus S7-04 `FROZEN_FOR_A3`. Fresh
  current-host diagnostic S8 then passed real Chrome P2 multi-turn context and
  Tool work, P2/P3 concurrency, P3 create/status/cancel and failure truth,
  refresh and complete service-restart reconciliation, exact fixture effect,
  Store/Executor settlement, privacy and sanitized-log checks. These machine
  observations are diagnostic rather than USER acceptance, and the known
  product-generated scope-correlation deviation remains explicitly accepted by
  the user as non-blocking for final judgment rather than relabeled as strict
  validator `PASS`.
- The user will perform the final A3 physical/human acceptance on this current
  host in a fresh exact-candidate Session. Phase D′ destination transfer is
  skipped. Existing source commits and current-host runtime are reusable only
  where the C1 checks confirmed the exact active environment; historical
  reports, runtime digests, resource references, fixtures, Sessions, scope
  correlations and observations are not relabeled as the new freeze. The C2/C3
  run must produce a fresh report and handoff for the exact C1 commit/runtime,
  followed by a fresh S8 entry/session before any final user action. Existing
  freezes, including `8ce8e0c4`, remain historical.
- The first complete post-documentation runner on exact
  `84d43727fb104ae70e2666c6f96c244a42db492d` preserved all five real `VERIFY`
  results but correctly refused S7 closure because one of 1,673 backend Alpha
  cases failed. The named P2 context case passed immediately in isolation and
  500 same-process repetitions, while its implementation used fixed groups of
  20 event-loop yields to observe asynchronous Agent starts. The transfer
  successor replaces those fixed-yield observations with a condition-backed,
  one-second bounded wait; the complete 95-case Registry file passes and the
  product source is unchanged. This test-evidence repair receives credit only
  when the exact committed successor has affected and cumulative review credit
  and satisfies the external closure rule below; the failed `84d43727` report
  is diagnostic history and cannot authorize S8.
- The condition-backed successor
  `52aaa5ece83b7089df31869ebe8d65a14998edb8` still failed the same named case
  once under the formal 1,673-case runner while passing the complete 95-case
  Registry file, 500 focused repetitions and a compact same-order full backend
  matrix with 1,671 passes and two skips. Agent-call start was therefore still
  an insufficient oracle for the test's declared unacknowledged-output state.
  The current test boundary waits until the formal presentation unit exists,
  deliberately leaves that unit unacknowledged, proves zero assistant-history
  persistence and only then submits the next turn. Product source remains
  unchanged. This boundary receives candidate credit only when an exact clean
  commit containing it has affected and cumulative review credit and satisfies
  the external closure rule below; both failed formal reports remain diagnostic
  history and cannot authorize S8.

- D-079 fast closeout started from exact docs-only tip `bb11530ce`. Phase A
  approved the final test-oracle boundary with the target regression, complete
  95-case Registry file, Ruff, format and dependency checks passing; the local
  independent-review CLI could not run the current model, so the recorded Main
  cold-review equivalent and that limitation are explicit in the
  [closeout ledger](S8_FAST_CLOSEOUT_LEDGER_2026-08-15.md). Phase B then
  completed one breadth-first sweep before classification: backend Alpha passed
  1,671 with two platform skips, related regressions passed 789, all 27 formal
  frontend scripts passed 878 executed assertions, the production build
  completed 4,641 modules, and a fresh fixed-corpus product round completed
  STT, committed P2, real Agent, streaming TTS and playout with zero credential
  hit or forbidden effect. The real Store/Executor was fully settled and the
  privacy scan found no secret or raw-audio persistence. It found zero D-079
  blocker and consumed zero repair batch. The new-Session P2 activation retry
  storm and one retained-socket cleanup log are F-003/F-004 non-blocking ledger
  deviations and were not repaired. The user selected this current host for
  final acceptance, so Phase D′ is skipped; active services, private
  HTTPS/WSS, isolated data root, Origin binding and no-remote fixture boundary
  were checked rather than assumed. The first C2 attempt on exact `c04033380`
  completed 39 automatic `PASS`, all five real `VERIFY`, the 4,641-module
  production build and the post-run identity check, but the backend Alpha
  matrix reported one failure in the P2 partial-activation open-failure
  rollback case. Because it was not the pre-authorized F-002 context case, C2
  returned to Phase B. The exact case then passed, its complete 45-case owner
  file passed, and the unchanged original test function passed 100/100 focused
  repetitions; product source remained unchanged, so F-005 is an accepted
  D-079 load-flaky test-evidence deviation and is not repaired. The failed
  external report remains diagnostic and cannot freeze S8. This docs-only C1
  re-settlement must commit before the next exact clean runner/probes and C3
  external freeze; formal S8 remains paused until that succeeds.

- Current closure is deliberately external and fail closed rather than claimed
  in advance. The external report must validate the exact current clean HEAD,
  runtime digest, 40 automatic `PASS` and five real `VERIFY`; the
  `live-voice.s7-a3-handoff.v1` must bind that exact report/runtime and separately
  record S7-03 `PASS` plus S7-04 `FROZEN_FOR_A3`. If any binding is absent or
  fails, S7-03 is still in progress, S7-04 is `REFREEZE REQUIRED`, and S8 remains
  blocked. This rule remains authoritative after an external-only freeze and
  does not require a post-freeze Git edit.

- The remaining S7/S8 window runs under the user-approved D-079 fast-closeout
  mode: batch repairs with affected-scope verification and blocking-only
  triage, one contract-grade freeze (documentation first, then the single
  complete runner plus five real probes, then the external handoff),
  machine-eligible S8 evidence, and a short physical human acceptance. The
  per-repair re-freeze cadence is superseded for this window; the external
  fail-closed binding rule above is unchanged.

The active execution contract for this window is
[S8_FAST_CLOSEOUT_PACKET_2026-08-15.md](roadmap/S8_FAST_CLOSEOUT_PACKET_2026-08-15.md)
under the
[S5-S8 plan](roadmap/ALPHA_S5_S8_EXECUTION_PLAN_2026-08-12.md); the completed S7
packet is
[S7_EXECUTION_PACKET_2026-08-13.md](roadmap/S7_EXECUTION_PACKET_2026-08-13.md),
and the detailed result is
[S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md](S7_ALPHA_INTEGRATION_REVIEW_2026-08-13.md).

## S7 dashboard

| Task | Status | Current fact |
|---|---|---|
| S7-01 selective port and candidate freeze | `SATISFIED` | The S7-owned runner, five probes, tests, documentation and frontend script registrations were selectively adapted from `d2727f20`; broad formatting, stale D113 and stale Streaming Speech copies were dropped. The repaired product source is `c209e4a6`. |
| S7-02 automation | `SATISFIED` | The external report binds exact tested source `d33b520e`, the accepted D-079 test-evidence deviation and the complete automatic result. |
| S7-02 real path | `SATISFIED` | All five current-host real probes reached `VERIFY` with nonzero samples, zero probe failure and zero forbidden effect. |
| S7-03 cumulative Tier-3 review | `SATISFIED` | The exact-current handoff records `s7_03_review=PASS`; the unavailable independent CLI and Main cold-review substitute remain explicit in the ledger. |
| S7-04 A3 handoff freeze | `SATISFIED` | The exact-current handoff binds `d33b520e`, the valid report/runtime and `s7_04_status=FROZEN_FOR_A3`; the user then completed S8 and returned `PASS`. |

The table preserves historical closure while making the external exact-current
binding the sole authority for the new candidate. Provisional S8 discovery is
never relabeled as formal evidence.

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

1. From protected local terminals, establish the private Speech/product
   runtime and run the single D119 seven-step Journey from the actual Live
   Voice entry on the exact candidate. Route Facts and mounted tests are not a
   substitute for microphone/TTS acceptance.
2. Record current-generation terminal playout/ACK behavior, the authoritative
   adjustment event order, TaskResult/artifact SHA and visible artifact
   contents, then remove only the resolved disposable fixture and isolated data
   directory described in the runbook.
3. Keep S8/A3 `PENDING` until that physical Journey actually passes. The local
   implementation is committed and four commits ahead of upstream; every
   remote-ref update still requires separate exact approval.
