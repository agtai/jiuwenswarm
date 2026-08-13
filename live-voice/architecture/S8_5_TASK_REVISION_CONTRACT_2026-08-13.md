# S8.5 bounded task-revision contract

> Decision: D-079 in [DECISIONS.md](../decisions/DECISIONS.md)
> Execution: [S8.5 plan](../roadmap/S8_5_COMPETITIVE_SHOWCASE_EXECUTION_PLAN_2026-08-13.md)
> Current state: [STATUS.md](../STATUS.md)

## 1. Contract identity

- Milestone: post-Alpha `S8.5 Competitive Showcase`; it is not a D-075 stage.
- Target: one committed Live Voice command revises one running background code
  task while preserving truthful Task/Attempt/Executor provenance.
- Track/modules: `P3 / TC + ED + VB + Web`.
- Risk: Tier 3 shared authority, persistence, concurrency and project mutation.
- Flag/profile: disabled by default and unavailable to the Alpha/P3alpha profile.

## 2. Identities and immutable records

`task_id` is stable for the task aggregate. `task_revision` starts at `1` and
increases by exactly one. Every revision is immutable and contains its complete
effective instruction, additive facts, effective constraints, origin commit and
the command that created it. `attempt_id` identifies exactly one execution of
exactly one revision; it is never reused.

```text
TaskRevision {
  task_id, task_revision, predecessor_revision,
  instruction, additive_facts[], constraints,
  origin_commit_id, created_by_command_id
}

RevisionTarget {
  task_id, expected_task_revision, expected_attempt_id
}
```

The current revision is a Core/Store fact. A UI label, transcript, Agent claim,
worktree contents, or command ACK cannot advance it.

## 3. Allowed operations

`task.provide_input` appends one or more committed facts. Existing facts and the
base instruction cannot be deleted, reordered or rewritten.

`task.update_constraints` applies a canonical patch to this allowlist only:

| Constraint | Allowed change | Forbidden change |
|---|---|---|
| `write_scope` | narrow to normalized fixture-relative paths | broaden, escape root, symlink traversal |
| `dependency_policy` | retain `locked` | dependency or lock-file update |
| `public_api_policy` | retain `preserve` | public API change |
| `configuration_policy` | retain `preserve` | project/runtime configuration change |
| `regression_verifier_required` | `false -> true` or retain `true` | `true -> false` |

Unknown keys, empty patches, conflicting facts, instruction replacement,
constraint relaxation, `pause`, `resume`, `reprioritize`, decision response and
same-attempt steer return a stable error with zero mutation.

## 4. Admission and confirmation

Every mutation requires all of the following:

1. committed input and an authenticated exact `ScopeRef`;
2. exact `task_id`, current `expected_task_revision` and current
   `expected_attempt_id`;
3. the matching S8.5 capability and enabled feature profile;
4. a confirmation binding over operation, canonical payload, task/revision/
   attempt, subject/scope, origin commit and expiry;
5. a globally stable `command_id` whose canonical fingerprint cannot change;
6. an active non-terminal predecessor and no other pending revision command.

Replay of the same fingerprint returns the durable prior result. Reusing a
`command_id` with different meaning is `CONFLICT`. A stale revision/attempt is
`STALE`; ambiguity is `CLARIFICATION_REQUIRED`; expiry or scope mismatch is
`PERMISSION_DENIED`. All reject paths have zero side effects.

## 5. Revision saga and authority

```mermaid
sequenceDiagram
    participant V as Voice/Structured Client
    participant C as Task Core + Store
    participant E as Executor
    participant U as Task Truth UI
    V->>C: confirmed revision command
    C-->>V: command accepted, application=fencing
    C->>E: fence exact predecessor attempt
    E-->>C: cleanup ACK or unknown
    alt exact cleanup ACK
        C->>C: append revision N+1 + successor attempt atomically
        C->>E: dispatch revision N+1 from clean fixture base
        C-->>U: revision applied + successor identity
        E-->>C: execution ACK + diff + verifier result
        C-->>U: authoritative attempt/task events
    else timeout, crash, mismatch, dirty/unknown cleanup
        C-->>U: application unknown/rejected; no successor dispatch
    end
```

On admission, Store atomically records the command, pending revision payload,
outbox fence intent and `task.revision_requested`. It also fences predecessor
outputs from becoming current. The canonical task revision remains unchanged
until exact Executor cleanup ACK.

Executor ACK must bind task, predecessor revision/attempt, fence command,
checkout/worktree identity and `unapplied_changes_discarded=true`. Store then
atomically marks the predecessor `interrupted`, appends revision `N+1`, creates
one successor attempt and one dispatch outbox row, advances current revision and
emits `task.revision_applied`. No ACK means no successor.

Only authoritative successor attempt events may produce running/terminal task
truth. Late predecessor progress, patches, verifier results and completion are
retained as fenced diagnostics but have zero current-task/UI/project effect.

## 6. Executor and project boundary

The successor starts from the trusted fixture manifest's original clean base,
not from the predecessor worktree, its Agent context or an inferred filesystem
state. Executor enforces:

- disposable local Git fixture with no remote and no push credential;
- normalized write scope and no symlink/root escape;
- no dependency, lock-file, public API or configuration mutation;
- no `git commit`, `git push`, network publication or real-user project target;
- one Executor-owned allowlisted verifier selected by manifest ID;
- bounded process/runtime/output and sanitized result fields.

The result contains `execution_ack`, changed-path/diff summary, verifier ID,
exit/result, cleanup state and forbidden-side-effect count. Agent text alone is
never an execution or verification ACK.

## 7. Truthful UI projection

The existing Task panel gains a compact Task Truth projection:

- stable task ID, current/pending revision and current/superseded attempt;
- command state: `accepted`, `fencing`, `applied`, `rejected` or `unknown`;
- predecessor cleanup truth and successor start truth;
- changed paths/diff summary, verifier name/result and terminal outcome;
- explicit warning when cleanup, execution or verification is unknown.

Command application state must not be rendered as task lifecycle state. The UI
does not infer success from transcript wording, an accepted command or silence.

## 8. Restart, concurrency and failure rules

- Restart reloads command, pending revision, fence/dispatch outbox, revision and
  attempt records and reconciles Executor facts; it never silently reruns.
- At most one revision command is pending per task. Concurrent commands compete
  by expected revision/attempt; one may win and all stale contenders reject.
- Duplicate/out-of-order events are deduplicated by identity and sequence.
- Executor cleanup/apply/verifier `unknown` stays visible and blocks successor or
  success as applicable.
- Cancel and revision do not cross scopes: exact task cancel may terminate the
  current attempt, while response/round/playback cancellation never does.

## 9. Non-goals

This contract does not provide arbitrary live steer, in-place attempt mutation,
approval/decision response, pause/resume/reprioritize, durable preferences,
general user repositories, arbitrary shell/tests, dependency/API/config changes,
D1/D2, cross-provider exactly-once, rollback of irreversible effects, public
deployment, Production authorization or complete P3.
