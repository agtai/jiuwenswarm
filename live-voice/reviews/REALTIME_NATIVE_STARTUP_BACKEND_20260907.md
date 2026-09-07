# Native pending startup retirement — backend evidence

This Tier 3 repair owns `dedicated_media_registration.py` and its matching unit
tests. Main owns browser bootstrap readiness, integrated review and deployment.
The actual failed candidate is `3393ba8b`; these two files in worker baseline
`40f56fac` have identical Git contents (working-tree line endings differ only).
The worker branch has no upstream. Its four previously copied audio modules,
test data and EOF patch are excluded from this repair.

The observed browser retired activation 7's first media capture at
16:02:32.189 UTC with 149 local frames and zero transmitted frames. Provider
`session.updated` arrived at 16:02:32.608745; activation 8 repeated the pattern,
retiring at 16:02:41.800 and receiving `session.updated` at 16:02:45.369107.
The Gateway reserved its Native session only after Provider startup and never
rechecked revoked media ownership. Its same-activation successor then hit
`MEDIA_NATIVE_SESSION_ALREADY_ACTIVE`. The reservation gap and revoke lookup
predate the six repairs (`59401beb0`, 2026-09-01).

Intended behavior: retain the exact pending bootstrap before async work; revoke
synchronously fences and cancels that bootstrap and its shielded context read.
Each suspended startup stage must revalidate record identity, subject ownership,
activation and expiry. Only a current owner can become active, publish work or
start media/business consumers. Cancellation is an optimization, not proof that
startup settled. Close waits for exact startup and context tasks before closing
the Engine. An uncooperative task retains one bounded cleanup owner and existing
capacity; a startup close caller waits at most 100 ms and reports `False` if
cleanup is unknown. No protocol, authority source, Provider/model configuration,
replay, business mutation or real runtime data is added or changed.

Acceptance covers normal delayed startup; revoke/caller cancellation and late
results; each await boundary; direct identity/expiry changes; same-key exclusion;
successor isolation; explicit unknown cleanup and capacity; and the registered
socket path. All negative paths require zero live startup consumers, audio,
business proposals and history effects. Independent review and Main's actual
browser acceptance remain required. Focused results are recorded below.

## Verification

Run from the worker worktree with the original repository's `.venv/Scripts/python.exe`,
`PYTHONPATH` set to this worktree and `JIUWENSWARM_DATA_DIR` set to its
`.repair-test-data/startup` directory:

```powershell
python -X utf8 -m pytest tests/unit_tests/gateway/test_dedicated_media_registration.py --no-cov -q
```

The final whole-file run passed **179/179** in 5.99 seconds, including 30 new
startup cases. The final registered-socket and finalization subset passed 3/3.
Logs are local `.repair-test-data/startup-registration-full.log` and
`.repair-test-data/startup-socket-finalization.log`; these runtime artifacts are
excluded from the commit. Scoped `git diff --check` passed. The normalized tested
Git blobs are registration `6b49331918aacaeb80657416705f22adf57ab268` and tests
`150a31b0971d9101b160b9b95dd5756a7ca2732b`.

| Dimension | Evidence |
|---|---|
| P | Delayed bootstrap becomes active once, starts all four consumers and accepts one exact audio frame; registered socket attaches only after startup succeeds. |
| N | Revoke, caller cancellation, changed record object, changed subject, changed activation and expired authority fail closed. No input/delivery/event/business-poll task, work publication, proposal, audio offer, generated text or presentation ACK is produced by the retired startup. |
| B | Capacity-one cleanup stays counted after record removal. Close returns unknown within its bounded caller wait while the Provider still ignores cancellation. False, null and exception close outcomes retain the exact owner. |
| S/T | The 21-case matrix crosses context read, Provider start and context update with seven retirement/identity/expiry conditions. A late READY never promotes a retired owner, and stale context reads cannot write the old cache. |
| C | Duplicate start on the same owner waits for one bootstrap; a different capture under the same activation is rejected before creating another Engine. A new activation can start while the old Provider is blocked. Cancellation while cleanup awaits the final registry lock retains capacity. |
| R | Exact close retry releases an unknown cleanup owner; a completed Provider close is not repeated after finalization cancellation. The Runtime close request identity stays stable. |
| I | A replaced original record cannot pass via a new dictionary lookup. Old pending cleanup preserves the new activation's record, Engine and notification queue. Lock-wait retirement rejects before any Engine factory/start/close or Runtime call. |
| F/K | Existing Native startup-failure, active close, revoke, feature-off/Cascade and media route regressions pass in the complete registration file. Pending cleanup is deliberately absent from the active-session map. Wire contracts are unchanged. |
| X | Both tests use the production registered media handler and socket leaf with a deterministic socket and Engine; successful delayed attach forwards one frame, cancelled startup sends none. This is local integration evidence, not physical Provider/browser acceptance. |

An additional bounded in-memory contrast compiled only the original candidate's
`begin_native_interaction` method from `git show 3393ba8b:...` and ran it against
the same public registry fixture. Other helpers remained the current ones, so
this isolates the original startup method and is not a full old-candidate run.
After exact media revoke, releasing a cancellation-resistant Provider start gave:

| Startup method | Begin result | Active sessions | Consumer tasks | Engine close calls |
|---|---|---:|---:|---:|
| Original `3393ba8b` | `True` | 1 | 4 | 0 |
| Repaired | `MediaTransportViolation` | 0 | 0 | 1 |

The repaired order was `configure → ready → closed`, demonstrating that close
waited for the old Engine's actual startup return. The content-free output is
`.repair-test-data/startup-counterfactual.log`. No source swap, service restart,
Provider call, real Session mutation or private configuration change was used.

## Review and limits

The worker cold-read the complete changed boundary and tests. Independent ultra
review passed the final frozen module boundary. It found and reproduced premature
capacity release before cleanup acquired its final registry lock. Reservation
release and exact map deletion now occur together under that lock, with no
suspension between them. The reviewer also flagged that an initial context read
must retain the original record object; `start_record` now supplies that exact
identity. Both have formal regression coverage. The independent reviewer checked
the same frozen source/test hashes, 179/179 whole-file result, 3/3 subset and the
limited in-memory contrast, and reported no remaining module finding.

An external operation that refuses cancellation can remain alive until it
settles. It retains a closed pending owner, a single cleanup task and existing
capacity instead of being declared closed or allowing same-key reuse. The repair
does not guarantee a physical network operation can be forcibly terminated.
Main owns integrated frontend verification, redeployment and actual listening
acceptance in the designated Chrome Session.
