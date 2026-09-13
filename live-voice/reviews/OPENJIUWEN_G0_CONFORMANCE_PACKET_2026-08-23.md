# OpenJiuwen reuse OJ-G0 module conformance packet

> Date: 2026-08-23
>
> Status: completed Tier-3 discovery packet; one bounded local AgentCore PR
> candidate prepared; no production, replacement, migration or
> product-acceptance credit
>
> Locked dependency: `openjiuwen==0.1.16` from
> `94e10cb6102c36fe78a64547957c0def97299273`

## Intended behaviour and owner

OJ-G0 tests whether the existing AgentCore TaskDao, AsyncToolRuntime,
Checkpointer storage, Workflow Journal and TeamScheduler can be composed before
any of the six proposed change series are implemented. The tests derive from
the outcome contracts in the
[reuse audit](OPENJIUWEN_REUSE_AND_HERMES_VOICE_MIRROR_AUDIT_2026-08-23.md),
not from Live Voice class names.

The owned surface is one module-composition conformance file under
`tests/integration/openjiuwen/`, this record, and the minimal STATUS routing
needed at closure. The suite uses real locked AgentCore modules, a real
file-backed SQLite TaskDao, real Journal WAL and real Checkpointer storage
logic. Test-only host/message/KV probes remain under tests.

## Risk, acceptance and exclusions

This is a Tier-3 **evidence boundary** because its oracles cover shared
authority, security and durability. It does not change a production authority
or protocol. Applicable D-032 dimensions are recorded per test; all mutating
negative paths assert zero forbidden effects where the current API exposes
them.

Acceptance:

1. the installed source commit is fenced exactly;
2. existing composable capability tests pass normally;
3. missing generic contracts appear as strict xfails with stable gap IDs;
4. an implementation that satisfies an xfail becomes XPASS and therefore
   fails until the marker is removed and the test becomes ordinary PASS;
5. results identify the smallest existing AgentCore owner to change next.

Explicit exclusions:

- no Live Voice or AgentCore production edits before the tests run;
- no new Task/Attempt/Event/Effect/Cursor authority or schema in JiuwenSwarm;
- no real Agent, file Tool, browser, Provider, microphone or TTS credit;
- no migration, dual write, legacy deletion, product status change or remote
  ref update;
- the existing product `P3-G0` and this reuse-oriented `OJ-G0` are distinct.

## Planned conformance matrix

| Gap | Existing modules connected | Positive oracle | Red oracle |
|---|---|---|---|
| OJ-G0-01 cancel race | TaskDao + AsyncToolRuntime | cancel/complete has one Task terminal winner | accepted Task cancel quiesces the related Tool before effects |
| OJ-G0-02 restart | file TaskDao | a new DB object reopens persisted Task truth | no phantom running Task remains without an execution owner |
| OJ-G0-03 D1 | Checkpointer + TaskDao + Scheduler | Checkpointer and Journal facts reopen independently | wrong-profile/generation checkpoint cannot dispatch |
| OJ-G0-04 D2 | AsyncToolRuntime + Journal | Journal WAL recovers completed-prefix facts | crash after external effect does not repeat it |
| OJ-G0-05 scope | TaskDao + TeamTaskManager | team lists remain scoped | known cross-team Task ID has zero disclosure/mutation |
| OJ-G0-06 event ordering | Scheduler + WorkflowProgressEvent | Scheduler tie ordering is stable | progress carries replay-safe envelope/sequence identity |
| OJ-G0-07 cursor/ACK | MessageDao read watermark | existing per-member read path remains compatible | same-time rows do not over-ACK and text/voice identities are isolated |

## Results and next PR

### Locked-source split

The exact installed dependency was proven by
`.venv/Lib/site-packages/openjiuwen-0.1.16.dist-info/direct_url.json` and the
source fence in the suite. The normal focused run completed as:

```text
5 passed, 8 xfailed in 7.47s
```

The five green facts are:

1. exact version/commit fencing;
2. TaskDao cancel versus complete produces one terminal winner;
3. a new file-backed TaskDao object reopens persisted task truth;
4. Checkpointer AgentStorage and Journal WAL independently recover their own
   facts;
5. Scheduler equal-time selection has a stable `(updated_at, task_id)` order.

`--runxfail` then produced exactly `8 failed, 5 passed in 8.22s`. Each failure
was an owned business assertion, not a collection, fixture or setup failure:

| Gap | Observed locked-source failure |
|---|---|
| OJ-G0-01 | Task cancel leaves the related AsyncTool record `running` |
| OJ-G0-02 | reopen retains an `in_progress` task with no execution owner |
| OJ-G0-03 | wrong-profile checkpoint does not stop Scheduler dispatch |
| OJ-G0-04 | crash/retry applies the external effect twice |
| OJ-G0-05 | another team reads, cancels and publishes for a known task ID |
| OJ-G0-06 | WorkflowProgressEvent lacks the required replay-safe identity fields |
| OJ-G0-07a | a millisecond watermark consumes a distinct same-time message |
| OJ-G0-07b | ACK state lacks stream, consumer, channel and sequence identity |

Commands from the JiuwenSwarm repository root:

```powershell
.\.venv\Scripts\python.exe -m py_compile tests\integration\openjiuwen\test_agentcore_g0_conformance.py
.\.venv\Scripts\python.exe -m ruff check tests\integration\openjiuwen\test_agentcore_g0_conformance.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -o addopts='' tests\integration\openjiuwen\test_agentcore_g0_conformance.py
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -o addopts='' --runxfail tests\integration\openjiuwen\test_agentcore_g0_conformance.py
```

The last command is intentionally red proof; its non-zero pytest result is the
expected outcome, not a passing Gate.

### Smallest AgentCore PR candidate

OJ-G0-05 was selected because it is the smallest independent generic defect
and a direct confidentiality/integrity boundary. The other red gaps require a
new execution relation, recovery owner, effect receipt/reconciler, event
envelope/outbox or cursor schema and therefore are not honest small-PR work.

The candidate is a local AgentCore branch based exactly on the locked commit:

```text
branch: codex/oj-g0-scoped-taskdao
base:   94e10cb6102c36fe78a64547957c0def97299273
head:   d143b04b835f6852e8212afb22fefc3a4f05d8f1
title:  fix(swarm): enforce team scope for task lookup and cancel
```

It makes `TaskDao.get_task` and `cancel_task` accept an optional keyword-only
team predicate, requires `TeamTaskManager` to supply it, removes remaining
unscoped TaskDao reads used as manager authorization, and adds one real-DB
negative test that asserts zero disclosure, zero cancellation, unchanged task
status and zero event publication. The unscoped DAO form remains only as a
backwards-compatible low-level path; Jiuwen's subject/project authorization
and path policy remain adapter responsibilities.

Verification on the candidate:

```text
red before patch: 1 failed; disclosed=true, cancelled=true,
                  status=cancelled, published=1
native negative after patch: 1 passed
Jiuwen OJ-G0-05 oracle with --runxfail against candidate source: 1 passed
AgentCore task DAO/manager affected regression: 194 passed, 2 warnings
production Ruff: PASS
test Ruff with only six pre-existing F841 findings excluded: PASS
py_compile and git diff --check: PASS
```

The six F841 findings are unchanged unused variables elsewhere in the existing
`test_task_manager.py`; a full Ruff format check also says the three pre-existing
Python files would be reformatted. Neither baseline cleanup is included in this
security fix. The local candidate has not been pushed and no remote PR has been
opened; a remote ref update remains separately approval-gated.

OJ-G0-01/02/03/04/06/07 stay strict xfails against the locked dependency. The
OJ-G0-05 marker also stays until JiuwenSwarm actually upgrades its AgentCore
lock to a commit containing the fix; the candidate proof does not mutate the
current dependency or product authority.
