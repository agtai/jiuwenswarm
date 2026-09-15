# Atlas native execution with two optional demos

Scope: Tier 2 integration of existing business carriers, authority checks and
execution owners. Native JiuwenSwarm remains the default. No new tool schema,
general classifier, parallel Demo execution or Atlas native-task UI is added.

- Live lookups use native `work.start`; ordinary deliverables use native tasks.
- A March coffee reorder selects task name `atlas:repurchase`; Paris expense
  preparation selects `atlas:expense`. Other requests keep the native path.
- Follow-ups retain observed IDs and revisions. Only `atlas:task:` / `atlas:work:`
  targets reach the local Demo adapter. No retry across executors on failure.
- Context combines task/work facts. Swarm's canonical voice history is primary;
  untimestamped Atlas text is only an empty-history fallback. Optional Demo reads
  time out after two seconds and unavailable capabilities are not retained.
- Native task origins and result presentation acknowledgments remain active with
  the Demo adapter enabled. A new Demo is refused while an observed Demo is busy;
  native work remains available. Bridge protection remains the final concurrency
  boundary, not the snapshot precheck.

Validation on Windows, 2026-09-15:

- Native-default, local-host, approval and wording suites: 38 assertions/tests
  passed. The first grouped run hit an existing daemon logging shutdown issue
  after passing; repeat uses unbuffered Python output.
- Native registry and routing regression run: 21 passed, one excluded baseline
  failure. The excluded completed-adjustment assertion requires `retained_speech`
  inside the saved instruction. It also fails with the unmodified HEAD router;
  not changed by this routing integration.
- Independent Tier 2 review completed; history ordering finding fixed and tested.
- Real provider, synthetic microphone in Atlas: weather request invoked Swarm
  `fetch_webpage` for Open-Meteo and wttr.in, returned a forecast to voice. That
  first test was interrupted by PAGE_HIDDEN during playback; it is not a full
  uninterrupted audio acceptance pass.
- Real native task in Atlas created a two-day Paris itinerary Markdown file in
  the configured project and spoke its result. The same voice session then
  selected coffee repurchase, retrieved the March order and asked for approval.
- A separate sequential session selected coffee, rejected it by voice (no order
  placed), then selected Paris expense and spoke the EUR 1382.90 confirmation
  with the meal policy exception. No purchase or expense submission authorized.

Known boundaries: demo requests are sequential within the existing bridge
session. Native tasks are voice-queryable but not Atlas mandate cards. Atlas's
text composer still uses its configured bridge. This restores execution access;
it does not certify arbitrary task correctness, every external website, or
perfect Realtime wording. The provider still sometimes adds acknowledgments or
Demo disclaimers despite existing concise-speech instructions.

## Chinese expense and spoken decision follow-up

The expense selector now maps to the existing expense entrypoint without relying
on the model repeating its English phrase; original request/constraints and the
visible user text remain intact. Coffee text is not prefixed with an invented
month or purchase action. Returned Demo kind and mandate identity must match,
otherwise acceptance is unknown, not dispatched.

Task facts, detail responses and approval notifications carry an explicit
`pending_decision_scope`: directory listing, expense form submission or purchase.
This uses the existing two expense gates' identity rules and changes no approval
authority. Future expense gate types must extend this classification explicitly.
Prompt instructions distinguish deferral from rejection and remove conflicting
Atlas acceptance/approval preambles. Atlas opens material pages in background
tabs while voice is active.

Verification: local-host/approval/wording tests (31 passed), Chinese original
request through Bridge mandate creation, approval and reporting, tab tests,
TypeScript checking, lint and production frontend build. Real voice QA uses
synthetic English microphone input; it does not establish a human Chinese audio
acceptance result. Regression checks cover the Chinese text after transcription.

The provider tool descriptions now advertise expense directory and form approvals,
not just purchase approval. Native task adjustment is explicitly separate from
Atlas submission. Unsupported adapter operations return an operation error with
supported-tool guidance, rather than incorrectly stating that an Atlas UI is
required. Host, approval and tool-carrier checks: 109 passed.

Real voice QA also exposed same-turn approval reuse after a directory gate
revealed the form gate. The host now pins each authenticated voice turn to its
first decision's task, interaction and prepared-action hash before dispatch.
Another gate needs a new user turn; context refresh and tool retries cannot reuse
the first answer. Unknown outcomes retain the pin and capacity is fail-closed.
Host/approval regressions including this two-gate scenario: 22 passed. This is
an additional execution guard, not a claim that arbitrary new-turn consent can
be semantically verified without the voice model.
