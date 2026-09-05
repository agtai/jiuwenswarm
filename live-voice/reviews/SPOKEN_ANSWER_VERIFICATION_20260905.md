# Agent answer ownership and faithful Live Voice delivery

## Accepted scope, revised by the user

On 2026-09-05 the user rejected Live Voice limiting, rechecking or rewriting the
Agent model's final answer. This supersedes the earlier optimization proposal.
Baseline: `076065f1bd5495dbafdee612d030b0e56f6910e0`.

Owner: Agent Bridge / formal adapter, Tier 2 for final-event delivery, private
model observation, cancellation and cleanup. Documentation is Tier 0.

Before implementation, the final boundary is:
- Remove the post-generation model call, length/quantity gate, replacement notice
  and evidence collection used only by that call. Deliver the Agent final text
  without semantic rewriting, including long answers and numeric claims.
- Retain only soft input guidance to the Agent about the spoken setting and the
  current user's requested depth. No sentence/character quota or forced summary.
- Preserve the configured Agent model options in the private observed clone;
  Live Voice does not force thinking on or off for answer generation.
- Keep current-turn/context authority, truthful Task receipts, Tool permission,
  stream completion/error handling, cancellation, history isolation and resource
  bounds. Do not change schemas, Task state, speech segmentation or audio fences.
- Verify exact final-text identity and no second model invocation, with and without
  numeric file evidence, errors/cancellation, concurrent scope isolation and
  configuration restoration. Use a real isolated Agent/file-tool path.
- Deploy locally after affected tests/review. Do not change the fixture, saved
  Provider configuration, existing Tasks/results/notifications, or remote refs.

Arithmetic, source interpretation and response quality belong to the Agent and
its instructions/tools. Passing text through does not claim those model answers
are correct. Full A/B/A2 and physical microphone/speaker acceptance remain open.

## Investigation and rejected approach

The original failing session `web_1a070a2a2a3_177f9eb1eac3` read the project's
input successfully. Its 675-character answer triggered a second arithmetic
model call, which timed out after 12.015 seconds and replaced the answer with the
unavailable notice. Missing or misnamed input was not the cause.

The rejected experiment removed the 200-character gate but retained a private
JSON audit, tried 30/45/90-second budgets and forced low reasoning for analysis.
Real drafts ranged 474–1541 characters. Multiple 30/45-second audits timed out;
one 90-second trial returned after ~104 seconds total and then failed its separate
semantic proposal probe. Diagnostic calls with a 120-second budget took 31.328
and 56.469 seconds. One wrongly returned a verified verdict; later corrections
still called a 1220-yuan option cheaper than an 830-yuan option. These are failed
quality evidence, not success merely because a model returned.

Independent review found and corrected prompt contradictions and a probe that
mistook unassessed completion for quality PASS. No missing-source, wrong-request,
configuration override or evidence-cap defect explained these trials. Raw tool
content did not eliminate their failures. The final change removes this entire
postprocessing approach; none of those experimental budgets or forced reasoning
settings is retained. Raw trial records stay in ignored local logs.

The large `c707c1e2d` integration also contains independent semantic routing,
Task authority, interruption, notification and entry repairs. The final change
removes the inappropriate output-processing boundary without reverting that
124-file integration or rewriting history.

## Final verification and deployment

- Before removal, the long numeric final-text regression failed by receiving the
  replacement notice, and the configured-model tests failed on forced thinking
  changes. A separate new test setup initially registered the wrong rail; that
  fixture was repaired and is not evidence of a product defect.
- Final focused command: `.venv/Scripts/python.exe -X utf8 -m pytest
  tests/unit_tests/agentserver/test_formal_live_voice_adapter.py
  tests/unit_tests/agentserver/test_formal_model_diagnostics.py
  tests/unit_tests/live_voice/test_rehearsal_context_audio_repair.py
  -q --no-cov --tb=short -o log_cli=false`: **50 passed**, exit 0, in 10.24 seconds;
  one existing Authlib deprecation warning. Bridge commands using
  `test_agent_bridge.py` and `test_agent_bridge_runtime.py`: **33 passed**, exit 0.
- The changed boundary covers exact long numeric/qualitative output, zero model
  calls after the Agent final, both tool grants/providers, deep-copied unchanged
  generation options, final/error/cancel delivery, detached cleanup, concurrent
  scope and no-history authority. Audit-only tests were retired with their removed
  implementation; context and observability checks remain. There is no new
  unchecked/checked status or silent fallback; the Agent answer is authoritative.
- Independent read-only review found no remaining actionable production issue;
  its 9 focused tests exited0. Main reviewed the complete affected diff, passed
  scoped Ruff checks, `git diff --check` and changed-document link resolution.
  The test-fixture fix, prior audit contradictions and invalid probe PASS handling
  are preserved above rather than treated as successful product evidence.
- A real isolated formal Agent read the current project input using actual file
  tools after the semantic model selected dialogue. Its 890-character final was
  delivered exactly, with no second audit call, in 59.922 seconds. The input and
  saved configuration hashes were preserved; no write/refund/booking/message
  operation or formal Task dispatch occurred. This typed probe establishes this
  output boundary, not physical speech, proposal continuity or arithmetic quality.
  The original real-model verbosity/latency and full A/B/A2 remain open.
- Before local deployment: 56 Tasks and 56 Attempts are all terminal; 34 result
  rows and 35 notification-consumption rows exist. Read-only row hashes and private
  configuration/input hashes were saved for preservation checks. No frontend
  Session or completion notification was opened. Controlled deployment pending.

