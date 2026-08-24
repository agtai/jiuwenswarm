# Authoritative Task acknowledgement materiality screen

Date: 2026-08-25

Status: approved setup packet; implementation and evidence pending

## 1. Question

Before changing Task, PresentationUnit or ACK authority, determine whether the
existing authoritative interval from `agent.task_command_accepted` to
`agent.presentation_produced` contains enough wait to justify an early
accepted/queued acknowledgement candidate.

This screen measures an opportunity boundary. It does not claim that an early
acknowledgement has been implemented, spoken or heard, and it does not claim
faster Task completion.

## 2. Existing truth and measurement owner

The current latency probe already owns both marks and the fixed
`task_command_to_presentation` segment for `task_create`, `task_status` and
`task_cancel`. This packet reuses the canonical latency report and adds no
event protocol or product mark.

`agent.task_command_accepted` is admissible only when it binds the exact
committed Task command, Task identity and activation/generation. The later
presentation remains the current authoritative result. Accepted or queued must
never be relabelled running, completed or successfully presented.

## 3. Scope, risk and exclusions

- Capability: P3 Task perception and P2/P3 presentation handoff.
- This materiality reader is Tier 0 validation tooling because it is read-only.
- A later early-PresentationUnit candidate is Tier 3 and requires a separate
  authority/ACK design checkpoint before product code.
- Owned setup surfaces: one validation script, its tests, this spec and its
  implementation plan.
- Excluded: product flags, Task state changes, PresentationUnit production,
  TTS calls, Browser/device automation, history writes and final ACK changes.

## 4. Input contract

The screen consumes one immutable canonical `live-voice.latency-report.v0`
JSON produced by `latency_probe_report report`. It fails closed unless:

- the source commit and run identity are present in the canonical report;
- all three Task profiles are declared;
- each profile contains `task_command_to_presentation`;
- the configured minimum successful sample count is met;
- failed, cancelled, fallback, underrun and rebuffer counts are zero;
- successful plus unknown samples equals the declared denominator;
- p50/p95 values are present, finite and ordered.

Cancelled or incomplete historical Task rounds may be inspected but cannot
make the screen eligible.

## 5. Outputs and meaning

For every Task profile, report:

- attempts and successful samples;
- p50 and p95 `task_command_to_presentation`;
- `maximum_ack_opportunity_p50_ms` and p95, equal to that observed interval;
- the configured minimum materiality threshold;
- an eligible/ineligible outcome and exact reason.

The maximum opportunity assumes zero acknowledgement construction, TTS and
delivery cost. It is therefore an upper bound, not predicted user-visible
gain. Audible or perceived gain remains `UNKNOWN` until a later real candidate
and Browser/device journey.

## 6. Decision rule

The default prospective gate is deliberately conservative:

- at least five successful attempts for every Task profile;
- zero integrity/failure counters;
- p50 opportunity at least 500 ms for every profile under test.

The runner emits exactly one terminal status:

- `ELIGIBLE_FOR_TIER3_CANDIDATE`;
- `NO_MATERIAL_OPPORTUNITY`;
- `INSUFFICIENT_VALID_SAMPLES`;
- `INTEGRITY_REJECTED`;
- `INVALID_INPUT`.

An eligible screen authorizes only a separate Tier-3 design packet. It does not
authorize early speech or product activation.

## 7. Later A/B/A boundary

If eligible, the separate candidate compares current A1/A2 against B, where B
may create exactly one Store-derived accepted/queued PresentationUnit after
authoritative admission. That packet must prove the final presentation and its
ACK remain independent and unchanged, Task terminal time/state do not move,
and every rejected, stale, duplicate or wrong-scope path has zero Agent, Tool,
Task, audio, history, ACK or retained-presentation effects.
