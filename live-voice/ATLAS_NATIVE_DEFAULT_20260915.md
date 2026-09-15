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
