# S7 Alpha integration, verification and review record

> Date: 2026-08-13
> Stage/node: S7 / A2
> Risk: Tier 3 cumulative boundary
> Comparison base: `2a69c2b87d0ee080a4a30421cbcbcdf93183f340`
> Product-source candidate: `c209e4a6cb88779277254751aa52354050a813a2`
> S8-readiness source candidate: `e58df618d3ee00776e004e8dfacd8d4d88b744dc`
> Outcome: automation, five real probes and cumulative review complete;
> S7/A2 closed; S8/A3 ready but not started.

This record applies the
[S7 execution packet](roadmap/S7_EXECUTION_PACKET_2026-08-13.md), complete
[Alpha acceptance contract](validation/ALPHA_ACCEPTANCE.md), D-074 review
cadence and D-078 runtime choices. The exact clean handoff HEAD includes this
record, [STATUS](STATUS.md) and the [Alpha showcase](demo/ALPHA_SHOWCASE.md), and
is bound by the external sanitized `s7-final-report.json` generated after
that documentation commit. The external report is authoritative for the final
Git SHA and dependency hashes; private paths, hostnames, credentials, raw media
and captures are intentionally absent from Git.

## 1. Entry and ownership

- Main worktree/branch: `hx/0812_live_voice_w3`; upstream remained the configured
  `origin/hx/0812_live_voice_w3` and was not updated.
- Initial verified HEAD: `b7573d51917eca2c3b6070c2bbc8632da4b2a2b1`.
- S6/A1 was already closed; the latest S6 history was treated as the only
  semantic baseline. No S6 commit was replayed, merged, squashed or rewritten.
- The `codex/s7-automation` source stayed read-only at
  `d2727f20669b1996257f5215d69c118447332138`.
- Main remained Integration Owner and the only history writer. The independent
  reviewer was read-only in the shared worktree and reviewed fixed SHAs/diffs.

## 2. Selective-port disposition

| Decision | Content | Disposition |
|---|---|---|
| `REUSE` | Five seven-line canonical probe entrypoints | Reused because they only dispatch fixed check IDs to tracked support code and introduce no stale product behavior. |
| `ADAPT` | `s7_alpha_verification.py`, `s7_real_probe_support.py`, their tests and `S7_AUTOMATION.md` | Updated for the final S6 inventory, exact comparison base, current flags/contracts, strict private-input handling, exact-debt static checks and current real-probe semantics. |
| `ADAPT` | Frontend `package.json` registrations | Added only the missing Live Voice S7 scripts. The runner dynamically discovers every tracked `tests/liveVoice*.test.mjs` and keeps the compatibility/product route scripts. |
| `DROP` | Broad formatting rewrite of existing Python/tests | Excluded. It was mechanically unrelated to S7 and would obscure the final S6 semantic diff. |
| `DROP` | Source-branch D113 and old Streaming Speech source/test copies | Excluded because the main branch contains newer D113-D116 repairs, including final Provider timeout, cold pre-open/EOT, long playout, ACK scheduling and 1,200 ms breath-pause behavior. |
| `REIMPLEMENT` | Observability seam | The frontend route-selection contract now accepts `source_record_id`, matching the Python matrix and fixture already authoritative in final S6. |
| `REIMPLEMENT` | Ruff compatibility boundary | File-wide per-code ignores were replaced with an unfiltered exact 21-diagnostic S6 fingerprint: path, code, row, column and message must all match. |
| `REIMPLEMENT` | Privacy raw-audio sentinel | Prefix-only checks were replaced with complete-corpus PCM16 and authoritative 48 kHz `pcm_f32le` raw sentinels, aligned base64 PCM16 slices and 3840-byte f32le media frames, the full corpus hash and a bounded multi-pattern matcher. Later-corpus raw/base64 regressions fail closed for both representations. |

The selective port was committed as:

- `bb780e39ae76885363f4d79783ef6b261d86fdaf` -
  `test(live-voice): integrate S7 candidate automation`;
- `5f154bf912dc681b91277a85416ef84c84400fb9` -
  `fix(live-voice): harden S7 candidate verification`;
- `c2d3b2c49d17042c1828dd951e82e0463f62286b` -
  `fix(live-voice): close S7 review evidence gaps`;
- `4cb834cf969e9b419c72cb75ff108426775dcd08` -
  `fix(live-voice): complete S7 privacy and handoff`;
- `75cdafeaae6f393e92681aa3c2c6afe7e8ec7d53` -
  `docs(live-voice): correct S7 repair provenance`;
- `50243dec` - `fix(live-voice): bound streaming socket cleanup`;
- `c209e4a6cb88779277254751aa52354050a813a2` -
  `fix(live-voice): accept early server-vad final`.

## 3. Automation evidence

The first clean full runner pass at `5f154bf9` completed 40/40 automatic checks:

- backend Alpha suites: 1,558 passed, 2 skipped;
- S6/current regressions: 787 passed;
- frozen npm install: 694 packages, PASS;
- all 27 registered frontend commands: 847/847 tests passed;
- Vite production build: 4,640 modules, PASS;
- Ruff, format, compile, `git diff --check`, Markdown links, source/privacy
  hygiene and post-run candidate identity: PASS.

The build retained pre-existing non-blocking warnings for one duplicate i18n
key, mixed static/dynamic import and chunks larger than 500 kB. No warning was
promoted to a candidate failure. The report correctly produced
`AUTOMATION_STATUS=PASS`, `REAL_PATH_STATUS=NOT_RUN` and
`S7_READINESS=PARTIAL_AUTOMATION_ONLY`; its incomplete exit did not masquerade
as S7 completion.

Independent review first found two valid P2 automation weaknesses. The Ruff and
PCM16 repairs at `c2d3b2c4` passed 57 runner/probe tests, changed-file Ruff, the
exact 21-diagnostic baseline helper and `git diff --check`. Affected re-review
then demonstrated that the formal `pcm_f32le` representation still evaded the
privacy scan. `4cb834cf` added complete-corpus f32le sentinels and raw/base64
regressions; the expanded focused suite passed 59 tests. A 16 MiB clean privacy
sample scanned in about 1.94 seconds, while later-corpus unaligned raw and
aligned base64 PCM16/f32le samples were all rejected.

The real Provider route then exposed two bounded cleanup/EOT defects that unit
fixtures had not reproduced. `50243dec` bounded WebSocket close waiting while
retaining cleanup ownership, and `c209e4a6` accepted an OpenAI server-VAD final
that arrives after the input fence but before the Browser finish request,
without duplicating Provider commit. The affected suites passed 68 Streaming
Provider tests and 51 route tests; independent rerun passed all 119.

The complete runner on product source `c209e4a6` completed all 45 checks: 40
automatic `PASS` plus five real `VERIFY`. It recorded:

- backend Alpha matrix: 1,564 passed, 2 skipped;
- related backend regressions: 788 passed;
- frozen npm install: 694 packages, PASS;
- all 27 registered frontend commands: 847/847 tests passed;
- Vite production build: 4,640 modules, PASS;
- exact Ruff fingerprint, format, compile, diff/link/source hygiene and
  post-run identity: PASS.

The exact clean documentation-handoff candidate received the same full runner
after this record was committed. `s7-final-report.json` is the sanitized
authoritative report for that final Git SHA and remains outside Git.

Generated frontend output is excluded from candidate identity and did not dirty
the worktree. The local locked environment was reconciled with `uv sync
--frozen`; machine-local environment changes were not committed.

## 4. Canonical real-probe outcome

All five repository entrypoints returned `VERIFY` against product source
`c209e4a6` and one runtime declaration digest,
`sha256:05bf19ba821bbffec03143b7d6412ef0ce5aeee383c0edc6b6a251ea130f3fab`.
Every sanitized observation remains outside Git.

| Probe | Status | Samples | Failure / forbidden effects | Actual outcome |
|---|---|---:|---|---|
| Speech/Media | `VERIFY` | 5 | 0 / 0 | Five fixed-corpus whole-route rounds passed over private same-origin HTTPS/WSS. p50 was 18,188.395 ms; p95/max was 19,001.572 ms. |
| Agent/Executor | `VERIFY` | 2 | 0 / 0 | Exact structured completion and cancellation passed through formal Task Core, the real JiuwenSwarm Agent and `DirectProjectCodeExecutorAdapter` in disposable no-remote projects. |
| Benchmark/Fault | `VERIFY` | 65 | 0 / 0 | The declared latency/route metrics and all 13 media, authorization, reconnect, feature-off, slow-Harness and cancellation-domain fault outcomes passed. |
| Secure deployment | `VERIFY` | 3 | 0 / 0 | A non-loopback private FQDN resolved only to a private address and served trusted same-origin HTTPS/WSS with the declared proxy/media route. No public deployment was created. |
| Privacy | `VERIFY` | 19 | 0 / 0 | All supplied capture surfaces scanned clean for the Gateway-only credential and complete-corpus PCM16/f32le raw/base64 sentinels. |

The whole-route producer used the fixed corpus plus bounded post-speech silence,
Provider-time server VAD, formal media ACK/EOT, the real Agent final, successor
capture overlap, Streaming TTS, downlink ACK and playout receipt. The user also
confirmed the controlled Chrome microphone, speaker and permission precondition;
physical spoken/audio-quality judgment remains intentionally owned by S8/A3.

The real P3alpha producer additionally exercised structured completion/cancel,
committed natural-language create/status/cancel with clarification and exact
confirmation, cross-scope rejection and duplicate-request replay with zero
repeated mutation. At the Web unary transport boundary the duplicate request ID
failed closed as a bounded no-response result rather than an explicit conflict
envelope; product-layer automated tests retain explicit replay/conflict proof.

The Browser bridge reported origin storage APIs unavailable. The privacy result
therefore proves the supplied 19-surface external captures and declared
PCM16/f32le representations, not unrestricted browser forensics. The A3 script
retains direct user-visible storage/lifecycle inspection. Historical S6 evidence
was not relabelled or rebound.

## 5. Cumulative Tier-3 review

Main reviewed `2a69c2b8..candidate` across:

- P1 capture/recognition/synthesis/playout and P2 media ownership;
- P2 response/progress/cancel and P3alpha Task/attempt authority;
- frontend, Gateway, AgentServer, Store, Executor, outbox, restart and cleanup;
- observability/privacy, malformed/error/timeout/reconnect and flag-off paths;
- response/round/task cancellation domains, stale-generation fencing and all
  applicable forbidden side effects.

The independent read-only review found no Critical/High product-source issue.
Across the repair and handoff loop it found seven P2 automation/documentation
items:

1. file-wide Ruff code waivers could hide new debt - valid and fixed in
   `c2d3b2c4` by the exact diagnostic fingerprint;
2. the prefix-only privacy sentinel could miss later PCM16 - valid and fixed in
   `c2d3b2c4` with complete-corpus sentinels and bounded matching;
3. affected review then showed the formal `pcm_f32le` representation could
   still evade the scanner - valid and fixed in `4cb834cf` with raw/base64 f32le
   coverage and regressions;
4. STATUS still said S7 had not started - valid and fixed in the first S7
   documentation handoff;
5. STATUS and this record attributed the f32 repair to the prior candidate -
   valid and fixed in `75cdafea`;
6. STATUS and this record still reported the pre-environment 0/5 state after the
   real probes passed - valid and fixed by the S7 closeout documentation;
7. the closeout documentation declared final-candidate closure while its exact
   post-commit runner was still in progress - valid, and closed when that runner
   exited 0 with 40 automatic `PASS`, five real `VERIFY`, a clean post-run
   identity and the bound external report.

The later `50243dec..c209e4a6` affected review found no Critical/High/P2 source
issue. It verified the bounded `websockets 15.0.1` close/abort behavior and the
server-VAD early-final fence/commit-owner proof, then independently passed 119
focused tests, Ruff, format, compile, cumulative diff-check and the exact
21-diagnostic historical Ruff baseline.

The affected source fixes received independent re-review. The reviewer used
the same shared worktree in read-only mode rather than a separate worktree;
fixed SHA boundaries preserved review scope. Main produced and inspected the
real effects; the independent reviewer did not rerun those external effects or
inspect private artifacts, but the canonical runner verified their sanitized
candidate/runtime binding, counts and zero-effect fields.

## 6. Exit and handoff decision

| State | Result |
|---|---|
| S7 automation ready | Yes |
| S7 real-path verified | Yes - 5/5 `VERIFY`, zero failures/forbidden effects |
| S7 cumulative source review complete | Yes - no open Critical/High/P2 source finding |
| A3 handoff ready | Yes - private profile and exact external report bound |
| Alpha human acceptance complete | No - S8/A3 has not started |
| S7/A2 exit satisfied | Yes |

S7/A2 is closed. The next stage is the user-owned A3 journey in
[STATUS](STATUS.md) and [ALPHA_SHOWCASE](demo/ALPHA_SHOWCASE.md). It must keep
the candidate/profile unchanged and physically verify microphone capture,
heard playout, permission/device/lifecycle behavior and the complete joint
P1/P2/P3alpha product journey. This record does not claim
`PASS - INTEGRATED WEB ALPHA`.

## 7. S8-readiness re-freeze addendum

The local `codex/s8-readiness-prep` work was audited rather than replayed as an
unreviewed branch. Its coherent helper/test/operator boundary was adapted onto
the closed S7 line and committed as:

- `e58df618d3ee00776e004e8dfacd8d4d88b744dc` -
  `feat(live-voice): integrate S8 readiness safeguards`.

The formal S8 packet also requires the original `b7efa14f` port commit to be an
ancestor of the frozen HEAD. The final documentation-handoff history records
that already-adapted lineage with a no-tree-change integration merge; the
reviewed `e58df618` tree remains authoritative rather than reintroducing the
older S6-base implementation.

No product implementation changed after `c209e4a6`. The readiness integration
strictly re-derives the 40 automatic and five real S7 result rows, binds the
product-authoritative SQLite Task Store to complete task/attempt/outbox/Direct
settlement, requires exact trace and USER-observer consistency, fixes the
18092/19000/19001 plus external-private-443 topology, and retains destructive
fixture locks through exact deletion. The S7 runner now freezes a bounded
complete path/size/content identity for the ignored production `dist` and
rechecks it after every later check. S8 recomputes that disk identity and reads
every canonical file from private 443 with exact 200, identity encoding, length
and content hash under one deadline.

Affected Main verification passed 112 readiness/runner/CLI tests and 18 real
probe contract tests. Independent affected review passed the same exact source
candidate with 112 tests and found no open Critical, High or P2 issue. The
complete source-candidate runner then returned 40 automatic `PASS` plus five
real `VERIFY`: backend Alpha 1,635 passed / 2 skipped, related regressions 788
passed, 27 frontend commands 847/847 passed and Vite transformed 4,640 modules.
The frozen build contained 180 files / 16,275,167 bytes; its post-run identity
and all 180 private-443 response contents matched. S7-03 independently approved
the exact clean `e58df618` candidate.

The first exact lineage-merge-HEAD run correctly remained non-authoritative: it
returned the five real `VERIFY` probes and every other automatic check, but one
backend test exposed that its 20 ms wall-clock budget could expire during
`open_recognition()` before the stream-deadline behavior under test began. The
failure reproduced independently at low frequency. The final candidate changes
only that test to complete open under a reasonable budget, advance an injected
monotonic clock beyond the deadline, wake the receiver with a valid nonterminal
Provider event and await the exact worker cleanup. The affected file passed 68
tests and the deterministic deadline path passed 1,000 direct repetitions.

S7/A2 closure is intentionally conditional rather than claimed in advance. The
external sanitized final report and `live-voice.s7-a3-handoff.v1` must validate
the exact clean current HEAD containing this addendum, current STATUS, the
test-only stabilization and the no-tree-change `b7efa14f` lineage. Only a
post-commit runner with the same 40 automatic `PASS` plus five real `VERIFY`, a
clean final identity, S7-03 `PASS` and handoff `FROZEN_FOR_A3` closes S7-04 and
makes S8 ready. Otherwise S7-04 remains in progress and S8 is blocked. This
addendum does not claim S8/A3 human acceptance.
