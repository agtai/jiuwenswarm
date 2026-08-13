# S8.5 Competitive Showcase acceptance

> Contract: [S8.5 task revision](../architecture/S8_5_TASK_REVISION_CONTRACT_2026-08-13.md)
> Human journey: [S8.5 showcase](../demo/S8_5_COMPETITIVE_SHOWCASE.md)
> Current state: [STATUS.md](../STATUS.md)

S8.5 is accepted only on an exact clean candidate after S8/A3 PASS and migration
onto that closeout source. Automated tests and rehearsals support, but do not
replace, the user's one complete product acceptance.

## 1. Entry

- exact Git source, clean worktree, S8 closeout parent and migration commits are
  identified;
- S8.5 flag/profile, disposable no-remote fixture and trusted verifier manifest
  are identified without private data;
- Tier 3 module/cumulative reviews have no unresolved critical finding;
- two complete unchanged rehearsals passed.

## 2. Required product result

One running Task A is revised through committed voice input. Pass requires:

- same `task_id`; monotonic immutable revision; distinct predecessor/successor
  attempts and command IDs;
- exactly one revision `1 -> 2`, originating from attempt 1; retry/revision
  mixing rejects with zero side effects;
- exact confirmation and visible `accepted -> fencing -> applied` command truth;
- predecessor cleanup ACK before successor dispatch;
- predecessor late output/patch/verifier has zero current effect;
- successor starts from trusted clean base with effective new fact/constraint;
- Executor reports truthful changed paths/diff and required verifier result;
- UI shows revision/attempt lineage and does not infer success;
- final code result and verifier pass are real, not scripted Agent prose.

One Task B is cancelled by exact committed voice command. Response, round and
playback remain unaffected; wrong-task and ambiguous cancellation mutate nothing.

## 3. Mandatory negative and recovery matrix

Pass all applicable cases:

- feature off and Alpha profile: unsupported, zero allocation/store/dispatch;
- interim/uncommitted/ambiguous/stale/expired/wrong-scope/wrong-task input: reject,
  zero Agent/Tool/Task/project mutation;
- replay: same result/no duplicate; fingerprint conflict: reject;
- concurrent revisions: at most one winner; loser stale; no double successor;
- cancel/revision race: cancel or terminal truth supersedes revision; no successor;
- Store failure at command/fence/revision/attempt/outbox boundaries: atomic recovery;
- Executor cleanup timeout/crash/mismatch: application unknown, no successor;
- restart in requested/fencing/applied/running/verifying states: truthful reconcile,
  no silent rerun;
- late predecessor progress/patch/completion: diagnostic only, zero current effect;
- dirty, remote, escaping, symlinked or real project target: reject;
- dependency/lock/API/config/out-of-scope change and commit/push attempt: reject and
  report forbidden side effects; authoritative fixture remains recoverable;
- verifier fail/timeout/missing: task cannot report verified success.

## 4. Verification and quality

- focused Core/Store/Bridge/Policy/confirmation/Executor/verifier/Web tests pass;
- affected backend regression, frontend test/build/static, `git diff --check`,
  Markdown links and source hygiene pass;
- disposable real Executor route proves cleanup, clean successor, diff and verifier;
- raw audio, credentials, private paths and unbounded Agent output are absent from
  Git/log/result/UI records;
- two rehearsals and the human run use the same source and fixture manifest.

## 5. Decision

- `PASS — S8.5 COMPETITIVE SHOWCASE`: every requirement above and the complete
  human journey passed on the exact candidate.
- `PARTIAL`: useful behavior observed but a required non-critical segment or real
  observation is missing.
- `BLOCKED`: environment/source/fixture/Provider/Executor mismatch prevents a
  truthful run; do not patch during acceptance.
- `FAIL`: wrong mutation, stale predecessor effect, false success, unrecoverable
  fixture change or another critical product defect occurred.

PASS does not claim arbitrary steer, general code autonomy, Production readiness,
complete P3, D1/D2, public deployment, broad browser support or industry exclusivity.
