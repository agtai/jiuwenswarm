# Native result ownership repair — 2026-09-10

## Design checkpoint

The user requests an instruction and code repair of the underlying cause, not a
route-specific heuristic. Baseline: `c4755aa8`. Risk: Tier 2 (context publication,
response ownership and playback ordering). The browser/Agent wire contracts,
persisted Work schemas and authority remain unchanged.

In session `web_1a08bd3359e_28137feb7a28`, the only Work queried weather. Its raw
result was inserted into the default Provider conversation before a notification
was cancelled. A subsequent direct answer used those facts and answered a route
question; a second notification, still owned by the weather event, repeated the
route answer. Two responses were generated, not two route lookups or PCM replay.

Intended behavior and ownership:

- Background result input belongs to its exact Work event/revision and original
  request. Supply it through `response.create.input`, not a persistent synthetic
  user message. Unrelated latest questions and other results are not notification
  input. Existing default-conversation output, bounded cancellation/truncation
  cleanup and acknowledged history remain the output owners.
- A current follow-up obtains an earlier result through the real `work.get`
  tool. Its server-sealed receipt binds the resulting response to the same event
  as an automatic notification. Neither a read, response generation nor a
  transport acknowledgment means the result has been heard.
- Only the existing full-playback/history-eligibility boundary marks a bound
  result presented; the canonical history writer remains asynchronous. A
  prepared notification is checked against fresh membership
  after its predecessor plays; a queried event already delivered is discarded
  through the existing cleanup protocol. Interruption retains its distinct
  suppression state and never cancels accepted Work.
- Instructions separate original Work scope from current conversational scope,
  require real lookup tools, and forbid speculative substitutes for missing
  facts. No classifier, lexical deduplication or location-specific condition.

Owned surfaces: Native business instructions, Engine result input construction,
Runtime sealed receipt access, Router presentation binding, Registry admission,
and their focused unit/integration tests. Applicable P/N/B/S/T/C/R/I/F/K/X checks
cover result selection, exact query identities, multiple results, actual ACK,
interruption, stale revisions, preparation races, isolation, replay and existing
feature-off behavior. Real Provider/microphone acceptance belongs to the user;
offline wire fixtures are not that evidence.

Dependencies: existing authenticated context, Work journal event identity,
delegate call-group binding, prepared-output cleanup, canonical played-history
writer. Exclusions: model/VAD, transport/environment issues, Task execution,
new semantic coverage claims, provider optimization and deployment/restart.
Semantic completeness of generated speech still needs user/model evaluation;
ownership is not a proof that every sentence faithfully summarizes its result.

## Verification and review

Implemented on the baseline above:

- Engine supplies `native_work_result` and the matching original Work instruction
  in `response.create.input`. It does not publish the raw result with
  `conversation.item.create`. Output still belongs to the default conversation
  and its existing cancellation/truncation protocol. This deliberately retains
  output/history behavior rather than introducing a separate output protocol.
  The [official Realtime API reference](https://developers.openai.com/api/reference/resources/realtime/client-events)
  defines `input` as a per-response context replacing default conversational
  input; it separately controls output conversation membership.
- Runtime exposes only sealed `work.get` receipts from the exact source call
  group and turn. Router compares complete returned snapshots to current scoped
  Work facts and registers their existing event identities on the admitted
  successor. A query read alone records no delivery. Multiple queried results
  share one spoken answer; stale revisions and unrelated events remain pending.
- Full playback eligibility consumes the bound events. Failed/transcript-free
  generation releases only its ephemeral binding. Interruptions remain explicitly
  suppressed, never presented or Work cancellation. Existing fresh membership
  checks discard a prepared notification after its foreground query is heard;
  its unplayed output is still cleaned through confirmed Provider truncation.
- Instructions require real requested lookup, use supplied details instead of
  asking again, and answer only from relevant results. Explicit queries must
  answer the requested result rather than merely acknowledge the read. No city,
  route name, time threshold, text similarity or response-content classifier is
  used to decide notification retirement.

Final offline check: **680 passed, 5 failed**, in 75.04 seconds, using the existing
workspace `.venv`. The five failures are the same projection-off context-refresh
cases previously reproduced on `87eba08a` in the
[prompt review](NATIVE_BUSINESS_PROMPT_20260910.md). Four are the `status/adjust`
`fresh_context` combinations with projection disabled; the fifth is
`test_work_feature_off_retains_actual_router_context_without_restricted_tools`.
No new failure remains. These inherited failures are not a full-green claim.

The final command used `python -X utf8 -m pytest -o addopts='' -o log_cli=false
-o faulthandler_timeout=30 -q --disable-warnings --tb=short --show-capture=no` on:

- Live Voice: result ownership, continuation preparation, Realtime Engine,
  Native interaction Runtime, business Runtime, business instructions, business
  Registry, acceptance fast path, business tools, bound business tools, named
  tools Engine and Work journal tests.
- Gateway: business observation, notification wake, response downlink, Task
  presentation retirement and observation retry tests.

New tests cover independent result input, no raw-result publication, prepared
audio invalidation/cleanup, multiple queried results, actual playback versus
generation/silent/failure/interruption, exact scope/revision/state/result facts,
late ACK after a real Work revision update, call-group replay and capacity
rejection without response effects. The serialized business-query/Registry/SQLite
seam checks both ACK-before-terminal and terminal-before-ACK; two queried events
retire while a third stays pending. Existing fault/cleanup, journal recovery,
authorization, wrong-scope, legacy and feature-off tests supply the affected
regressions. An old send-failure test was updated to inject at context publication
or the new combined result `response.create`; its former second-send assumption
could leave its test reader waiting indefinitely. The production failure fence
and zero-audio/delegate assertions remain.

`ruff check --select E9,F821,F822,F823` passed for changed Python files, as did
`git diff --check`. Full scoped source/test diff review and a second cold review
were performed. No independent `/review` tool is available in this task's allowed
tool set; the cold review is the recorded substitute under `TESTING.md`, not a
claim of independent review. Reviewed seams include receipt authenticity,
capacity before admission, wrong-turn rejection, exact snapshot comparison,
silent binding release, async history eligibility and prepared cleanup. The
independent-review limitation remains explicit.

Detailed local output is in ignored `logs/result-ownership-20260910/`.
The new source is not deployed. No new real Provider, browser, microphone or
Agent execution was performed for this repair. Model compliance, language and
detail fidelity, physical playback and any latency effect await the user's
sessions; the result ledger is not proof that a model included every fact.

## Task adjustment continuation — authorized 2026-09-10

The user accepted repair of adjustment admission/closure, durable continuation,
final-state delivery and result-grounded summaries, with reuse of existing Task
mechanisms and no topic-specific patches. This extends the prior Work-only scope.

Intended behavior: the Store linearizes the last adjustment checkpoint against
admission. An explicit change admitted after that checkpoint waits durably for
the exact original result, then uses the existing immutable successor Task and
project execution queue. Replays cannot create another revision. Cancellation,
unknown/failed base results, stale identity and unrelated successors fail closed.
Accepted speech evidence and all constraints remain attached to the change.
Adjustment adoption is distinct from a successfully saved artifact. Final control
facts and actual results must reach presentation and Native context.

Owned surfaces: Task Store/Executor cutoff and continuation, production Task
policy, authenticated control/result reads, Native instructions/context and
existing notification ownership. Risk is Tier 3 for the additive durable queue
and its Core integration, Tier 2 for presentation/concurrency. No new classifier,
provider tuning, WebSocket repair, service restart, push or real voice/Agent run.
Existing immutable Task/result and executor authorization boundaries remain.

Acceptance: P/N/B/S/T/C/R/I/F/K/X from root TESTING, emphasizing exact file/result
content, arrival on both sides of closure, completed-task changes, duplicate and
ordered changes, restart, cancellation/failure, scope isolation and interrupted
presentation. Offline evidence cannot establish model/audio user acceptance.
### Implementation and verification

Baseline: `1750387a`. The Store-owned cutoff and deferred-change ledger share
the canonical SQLite transaction. A fast executor can close before its dispatch
receipt projects RUNNING. Before closure, the existing adjustment outbox settles
normally; afterwards, accepted changes await the actual saved result and create
ordinary successor Tasks atomically. The existing successor implementation was
extracted into a transaction-taking helper: AST comparison finds only SQL-string
indentation differences in its body. No second executor or replacement task state
machine is introduced.

The queue preserves original requirements and retained speech, complete changes,
context/model binding and immutable predecessor results. Consecutive changes
use the latest saved queue-owned successor without recursively nesting prior
generated instructions. Ordinary file guards remain active: Native-created work
binds its speech digest, and internally derived continuations bind the complete
durable spec to the same file-effect plan. Unplanned writes fail before mutation.
Pending is not saved; only a completed child with a captured result settles the
change as applied. Failed/cancelled continuations remain rejected; interrupted
execution explicitly reports unknown effects rather than unchanged files.

Native reads actual saved results plus independent adjustment states. Whole
result content is included within a shared 64 KiB context budget; larger results
remain available through the existing exact result query. Diagnostic progress
windows do not retire unheard final adjustment outcomes. Historical control facts
stay durable; at most 64 unpresented Task events are projected per batch, and the
existing scheduler selects one result. The queue admits at most 64 outstanding
changes across the Store; overflow has no new execution effect and exact replay
continues to work. Existing wire/context, response and journal capacity guards
remain in force.

The Native observation carrier now accepts a closed Task-adjustment event variant
alongside unchanged Work events. Gateway and Engine require exact visible Task
revision binding. Notification input contains the selected adjustment and matching
Task identity/status, excluding another question, older saved content or a newer
adjustment's requirements. Task queries and observed adjustment receipts share
the existing presentation journal. Each actual Provider generation has a distinct
response ID; the result ID survives interruption. Only heard ACK consumes it.
Interrupted or silent/failed generations can retry in an idle slot, with existing
user-speech priority and a bounded retry delay. No service was restarted or deployed.

Commands use `.venv/Scripts/python.exe -m pytest`, `-o addopts= -o log_cli=false
-p no:cov -q --tb=short --show-capture=no`. Groups overlap; do not add their counts:

| Check group | Result |
|---|---|
| Queue, full Persistent Core, full Direct executor, file-effect plan | 564 passed, 2 host-dependent filesystem checks skipped |
| Native/P3/production policy, source retention, Runtime/Engine, gateway client (14 files) | 846 passed; the same 5 inherited projection-off context-refresh failures |
| Affected Native/queue checks after final event/receipt/history refinements (9 files) | 498 passed |
| Final queue and presentation recovery scenarios, including fast cutoff and silent generation | 38 passed |

The eight intermediate Core cleanup failures were introduced by yielding inside
the intentionally deferred adjustment claim batch. They were fixed by advancing
continuations once per reconciliation batch, preserving existing claim/cleanup
ownership; the full Core/Direct rerun above passes. Intermediate rejected-envelope
format errors were also corrected to canonical failure receipts. No new explained
failure is left open. The five inherited failures are exactly the cases listed
in the earlier Work review above; they remain outside D-127, not a full-green claim.

Scenario evidence covers P/N/B/S/T/C/R/I/F/K/X: real local SQLite transactions,
concurrent admission scheduling, crash rollback/reopen, ordered changes, unrelated
successor isolation, cancelled/failed/unknown outcomes, exact scope/attempt/replay,
capacity, actual temporary Git worktrees/files and SHA-256 result matching,
file-plan rejection, serialized Native/P3/gateway queries, exact notification
revision, partial interruption, fresh generation admission, silent failure,
heard ACK and zero unapproved file/Task/audio/history effects. Agent/Provider
responses are controlled fixtures; this establishes the owned local execution
and transport seams, not real model compliance or physical audio acceptance.

Cold review covered the complete scoped diff, successor extraction, transaction
rollback, source and file-effect inheritance, canonical failure envelopes,
existing deferred cleanup scheduling, final-event retention, exact query coverage,
per-generation notification identity and failed/partial playback. Tool discovery
found review UI and GitHub review posting, but no callable independent reviewer.
The recorded substitute is Main's cold diff review plus the cross-boundary/fault
tests; it is not independent review. Changed Python compiles, Ruff F checks and
Markdown/link/diff checks are recorded at local handoff. Detailed outputs are
retained under ignored `logs/adjustment-20260910/`.

The user explicitly requested completion without redeployment. Existing services,
private configuration, Mini/VAD300 settings, WebSocket behavior and unrelated SDK
workspace files remain outside this change. Deploy server and gateway together
when later requested; older binaries do not implement the additive continuation
ledger or the new Task event variant. User voice sessions remain the model/audio
acceptance boundary.
