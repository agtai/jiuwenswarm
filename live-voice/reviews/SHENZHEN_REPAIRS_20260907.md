# Shenzhen rehearsal repair and fresh-project deployment

User authorization: repair the diagnosed defects, then deploy services using a
new project directory. Baseline: `f08cd261d` (product code `d8ee9e6d3`).
The preceding [diagnosis](SHENZHEN_REHEARSAL_DIAGNOSIS_20260907.md) owns the original
sample; this record owns this implementation boundary and verification results.

## Intended behavior and ownership

| Boundary | Intended change | Owned surfaces / risk |
|---|---|---|
| Receipt scheduling | Concurrent context observations cannot discard a valid unsent receipt. The current authoritative context wins; STOP/new turn/obsolete work still prevents speech. | Native engine and continuation tests; Tier 2 concurrency/state. |
| Dialogue and delegation | Explicit background deliverables use the existing Task operation, external current facts use real Agent/tools, direct answers and receipts are concise. | Existing Native prompts/tool descriptions; Tier 1. The discovered file-only restriction is expanded to the existing SDK's exact free_search/fetch_webpage read operations for the authorized current-information lookup; Tier 2 policy boundary with callback-level positive/forbidden-effect checks, no new classifier, arbitrary tools or mutation permission. |
| Audio supply | Trace and repair demonstrated software delay before downlink source readiness; retain bounded queues and exact audio/render/STOP semantics. | Actual implicated Provider/Gateway path and focused tests; Tier 2 if scheduling changes. Physical continuity remains separately measured. |
| Deployment | Build the checked repaired source, create/register a fresh Shenzhen project, restart the authorized local services, verify runtime identity and usable routes. | Existing launcher/registration; new project content only, retain existing private configuration/data and old project. |

Main is the sole filesystem writer and Git/integration owner. Read-only workers
investigate audio and query/deployment independently; review may use a read-only
worker. No worker stages, commits, switches branches or pushes.

## Acceptance and exclusions

- The lost-successor reproduction becomes a passing positive test, including
  equivalent/newer observations. A stopped or superseded request produces zero
  old speech, duplicate tools or Task mutations.
- Natural background itinerary wording selects Task creation; ordinary questions
  remain read-only. Adjustment/retained-copy semantics and literal filenames stay
  intact. Existing consent, revision and scope validation remain authoritative.
- Current weather cannot be answered from seasonal guesses; verify real lookup
  availability without adding accounts, changing providers or exposing secrets.
- Audio changes must not repeat started PCM or substitute transport ACK for
  render ACK. Verify first sound and continuity together; do not claim that code
  tests establish human listening acceptance.
- Deploy with a fresh registered project and a reviewable Shenzhen brief. Preserve
  old files/tasks and model/credential selections. No remote Git updates.

Checks and review follow root [TESTING](../../TESTING.md), focusing on touched
boundaries rather than historical full-suite counts. Source/config changes bind
new evidence; physical acceptance and previously open unrelated candidate gates
are not silently closed by this batch.

## Verification and deployment results

### Implemented and reviewed

- Receipt scheduling no longer treats a concurrent context-object replacement
  as interruption. Gateway refresh waiters return the latest cursor-ordered
  cache and recheck close; the engine retains exact STOP/turn/work fences.
- Context authority resolves project/session/Git state in a worker thread,
  outside the registry lock. Principal/context expiry and route retirement are
  rechecked after that await and again after acquiring the lock. No authority
  cache or relaxed scope/permission policy is introduced.
- Native answers normally use one or two complete sentences. Tool requests
  have no spoken preamble; real receipts use one short sentence. Explicit
  background plans use Task creation; current-information questions use real
  Agent lookup. Personal `USER.md` remains unchanged because Native direct
  speech uses its own instructions.
- The read-only rail admits the existing SDK's exact `free_search` and
  `fetch_webpage` readers. Write, Task, paid search, disabled tools and callback
  name mismatch remain rejected. Deployment enables the existing free engines
  through process environment, without new accounts or credential changes.
- Passive, content-free per-delta/per-RPC timing joins Provider arrival, engine
  mapping, Gateway admission and registry lock wait. PCM ordering, the 250 ms
  playout reserve and actual-render ACK authority are unchanged.

Main reviewed the complete diff. Independent read-only reviewers found two P2
issues during implementation: newer refresh ordering and expiry while waiting
for the registry lock. Both were repaired, covered by regression scenarios and
re-reviewed. The reviewer also corrected a stale network-denial comment.

### Evidence and limits

Machine-local evidence is under `logs/shenzhen-repair-tests/` (ignored, no
credentials). Focused commands use `-o addopts='' -o log_cli=false`, unique local
`--basetemp` paths and the existing venv. Relevant groups are engine/continuation/
audio diagnostics/downlink; Native context/registry/authority/observation; and
Agent read-only policy/analysis/tools. Exact command results and source identity
are retained in the deployment evidence, rather than inferred from test counts.
The final focused groups report **429 passed** (one upstream Authlib deprecation
warning) and **53 passed**, respectively.

- The receipt race initially failed both positive cases. Added inverse ordering
  and Gateway waiter-close/cache scenarios also failed before repair.
- Slow resolver tests initially blocked the event loop. Current, close,
  replacement, resolver-time expiry and lock-wait expiry now pass with zero
  forbidden execution/projection effects (53 context/authority/observation tests).
- The broader legacy registry file reports **68 failed, 167 passed** on both
  `f08cd261d` and this repair. A baseline source loader reads Git into memory
  without switching the checkout; the two failed-nodeid sets are identical.
  These retained fixture/retired-path/environment failures are not new repair
  regressions and are not reported as passing. This is not full-suite closure.
- Real Provider prompt-conformance probes use only fixed synthetic inputs and
  never execute returned functions. The final five cases route background
  itinerary to `jiuwen_task_create` (2.687 s), dated weather to
  `jiuwen_work_start` (1.787 s), original-task change to `jiuwen_task_adjust`
  (1.798 s), a self-contained question to a short answer, and park ticket
  conditions to lookup. Tool cases emit zero preamble audio in that sample.
  These are measured request-to-function times, not user endpoint-to-first-sound
  or full Agent/Task acceptance evidence.
- Real free search returned results in 0.764 s and Shenzhen's meteorological
  homepage returned HTTP 200 in 1.438 s. Its dynamic `Loading` placeholders are
  not a forecast; the Agent must fetch a usable source or report missing data.

### Fresh-project deployment packet

The registered project is `proj_41f2b443`, at
`D:\XGG AI\openjiuwen\shenzhen-showcase-20260907`, with its own initial Git commit,
`README.md`, project instructions and one intentionally uncommitted independent
note. Existing private model/provider configuration and data store are reused;
the old project and historical tasks are retained. The repeatable launch/evidence
packet is in the ignored machine-local directory above.

Build/restart must use the checked clean source, explicit new ProjectPath and
ProjectId, `formal-web-validation`, `openai-realtime-native`, `gpt-realtime-2`,
VAD `auto`, output tokens `inf`, verified headset barge-in and `AllowDirtyProject`.
The launcher/runtime contract and real speech receipt probe own deployment
verification. Human listening for the original stutter, five mixed turns,
interruptions, actual background files/adjustments and stop/reopen remains open.
Current mutable status is owned by [STATUS](../STATUS.md).
