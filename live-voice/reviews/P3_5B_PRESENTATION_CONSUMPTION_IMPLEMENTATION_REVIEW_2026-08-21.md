# P3-5B presentation-consumption implementation review — 2026-08-21

> Status: **PASS — SCOPED P3-5B SOURCE AND AFFECTED AUTOMATION.** The
> presentation-consumption source at
> `d6d3eafefef13a3aaaece289db4c95835b65cd30` passed its affected automation,
> cold review and independent Tier-3 review. This record grants no physical
> audio-device, complete Wave-3, complete P3, feature-complete, Production or
> remote-ref credit.

## 1. Authority, source and scope

- Branch: `hx/0812_live_voice_w3`.
- Activation baseline: `cfff0c43aa599c009ab9517397566fec5c1bdd95`.
- Reviewed integrated source:
  `d6d3eafefef13a3aaaece289db4c95835b65cd30`.
- Governing decisions: D-089 presentation consumption and D-090 Task-wide
  consumer-cursor re-scope.
- Risk: Tier 3. The package changes shared Runtime/Web presentation authority,
  authenticated composition, durable Task-event consumption and restart/
  recovery replay.

Explicit exclusions are physical microphone/audio-device proof, the deferred
P1/P2 capture/Exit repair, P3-4 final migration compatibility, P3-6 production
classification/Core invocation, P3-7 UI, complete Wave 3/P3, controlled
candidate, feature complete, Production, `develop` integration and every
remote update.

## 2. Accepted implementation facts

- Durable consumption identity is exactly authenticated
  `(subject_id, project_id, task_id, text|voice)`. Session, response,
  generation and delivery remain presentation-attempt bindings.
- Text becomes consumable only after the exact connected DOM node adopts the
  retained presentation. Voice becomes consumable only after the Runtime-owned
  AUDIO `PresentationAckResult`. A failed or unavailable audio presentation
  creates a separately fenced text fallback and never consumes voice.
- `task.unread_events` remains pure. Only a fresh exact `task.ack_events` grant
  and the retained presentation owner may advance the Store watermark.
- The Store/Core Task-wide cursor preserves unread truth across new Sessions,
  process restart, retry/recovery Attempt rollover, non-presentable gaps and
  prefixes larger than the ordinary Arbiter capacity. It creates no second
  event or consumption ledger.
- Frozen terminal pages close only on the exact canonical terminal head.
  Recovery has a validated producer projection and a verified Attempt epoch.
- Runtime reservations, closed tombstones, retained HTTP replay and Registry
  deliveries are bounded. Close/generation replacement, delayed ACK, response
  loss and ACK-versus-close races either consume once or fail closed.
- Successful Core ACK is committed before best-effort presentation cleanup;
  cleanup failure cannot rewrite a durable success or cause a second mutation.
- Feature-off preserves the legacy visible-text path. No presentation owner
  directly mutates Task, Attempt, Executor, Agent, Tool or history authority.

## 3. Tier-3 scenario and zero-effect closure

| Dimension | Accepted evidence |
| --- | --- |
| P | Real SQLite Store/Core unread-to-ACK path, connected React DOM adoption and canonical Runtime AUDIO ACK positives. |
| N | Closed wire/schema, wrong event/class/response/generation/delivery, invalid result and rejected playout cases fail closed. |
| B | Bounded reservations/tombstones/deliveries, paged large prefixes and more than 256 projected voice events. |
| S | Foreign subject/project/task/class and browser-chosen route attempts cannot observe or mutate another scope. |
| T | Frozen terminal append, route close/replacement, late callback and terminal-outcome projection ordering. |
| C | Concurrent ACK/close, duplicate delivery, consumer cursor and reservation settlement races have one winner. |
| R | New Session/process cursor restoration, response loss, delayed ACK after rolling validation and retry/recovery rollover. |
| I | Fresh authorization, stable presentation identity, deterministic replay and command/delivery fingerprint conflicts. |
| F | Runtime ACK success followed by Core failure, publish failure, playout failure and cleanup failure reconcile without double consumption. |
| K | Canonical progress classes and completed/failed/cancelled/interrupted/unknown truth remain distinct. |
| X | Rejected paths assert zero Agent, Tool, Task, Attempt, Executor, history, audio and foreign-scope effects as applicable. |

## 4. Automated and static evidence

- Affected Python automation: `707 passed, 1 deselected, 1 warning` in
  `169.92s`. The deselected baseline expects completed retry where D-087 admits
  only cancelled retry; product semantics were not weakened to satisfy it.
- Formal Integrated Web: `414 passed, 1 failed`. The sole failure is the
  independently reproducible pre-existing mounted Exit/immediate-re-enable ACK
  timing case; all P3-5B presentation scenarios pass.
- Formal Web production build: PASS, 4,643 modules transformed.
- Build-profile verification: `2 passed`.
- Changed Python files pass Ruff check and `py_compile`; 25 owned formatted
  files pass `ruff format --check`. Four legacy carrier files retain their
  existing formatting and only their narrow routes were changed.
- `git diff --check`: PASS; emitted line-ending conversion warnings only.

## 5. Independent review verdict and remaining Gates

The final independent Tier-3/fix-only verdict is
`0 Critical / 0 Important / 0 Minor`. It specifically rechecked frozen
terminal handling, recovery projection/epoch, fresh cursor baselines, large
voice prefixes, pending presentation identity and delayed ACK after validation
rollover.

This is not the final Wave-3 Gate. P3-4 legacy-v6 compatibility, P3-6 real
classifier/authenticated Core invocation, the final cumulative broad Gate and
the minimum honest ACL-private physical journey remain required before Wave-3
acceptance.
