# Cancelled Task speech policy

Baseline: `b0b017456a54ef4a040262ee427cd12307049c0e`.

The user requested disabling unsolicited cancelled-Task speech. Cancellation
remains a truthful terminal event; text-origin notifications, task cards, status
queries and explicit action replies remain available. A voice-origin cancellation
is silent, without allocating a replacement text notification. No Agent-output
rewriting, USER.md change, task mutation semantics, schema or fake presentation ACK.

Tier 2 ownership: notification eligibility in Progress Return/Registry and
unread presentation selection. Silence applies to active, deferred and restored
voice routes; a cancelled prefix cannot block a later retry notification. Silent
voice cancellation advances neither text nor voice ACK. Completed, failed and
interrupted notifications retain their existing delivery. Verification covers real Store plus Registry,
class isolation, offline delivery, deferred/replay and affected ACK regressions.
Independent review is required at this boundary. Physical listening remains a
subsequent rehearsal check, not a claim from controlled-model tests.

## Verification

Every run uses an isolated ignored `JIUWENSWARM_DATA_DIR`, a unique
`--basetemp=logs/...`, and `--no-cov --tb=short --log-cli-level=ERROR`.

- `pytest tests/unit_tests/live_voice/test_running_notification_policy.py
  tests/unit_tests/live_voice/test_task_presentation_consumption.py
  tests/unit_tests/live_voice/test_product_composition_registry.py
  -k 'running_silent or presentation_consumption or terminal_notification_waits_for_activation'
  -q`: **37 passed**, exit 0. Includes active/busy and fresh-Registry cancelled
  voice silence with zero presentations, retained replay, Agent calls and ACKs;
  text cancellation with real ACK; success/failure/interruption controls; a
  cancelled prefix followed by retry; legacy orphan/activation replay and history.
- Registry regression command uses the exact selection in
  [the running-notification record](RUNNING_NOTIFICATION_POLICY_20260905.md#verification):
  **54 passed**, exit 0. The additional case is cancelled terminal replay.
  The previously reproduced baseline exclusion set is unchanged; no full-suite
  or physical-audio claim. Raw evidence: `logs/cancel-notice-final*.txt`.
- Independent read-only complete-diff review identified unnecessary voice-to-text
  substitution crossing independent unread queues and old/successor activation
  drain ownership. The final implementation removes substitution. Focused
  re-review found no outstanding actionable issue; existing TEXT routes retain
  their own notifications and consumption, and silent VOICE events do not
  fabricate either class's ACK.
- Scoped diff and STATUS link checks pass. Controlled deployment uses the
  established runbook; the actual deployed source/probes are recorded in the
  local runtime manifest. Physical listening remains open for the next rehearsal.
