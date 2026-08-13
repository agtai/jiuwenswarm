# S7 Alpha integration, verification and review record

> Date: 2026-08-13
> Stage/node: S7 / A2
> Risk: Tier 3 cumulative boundary
> Comparison base: `2a69c2b87d0ee080a4a30421cbcbcdf93183f340`
> Source repair candidate: `c2d3b2c49d17042c1828dd951e82e0463f62286b`
> Outcome: automation and source review complete; real path `ENVIRONMENT`;
> S7/A2 not closed; S8 not started.

This record applies the
[S7 execution packet](roadmap/S7_EXECUTION_PACKET_2026-08-13.md), complete
[Alpha acceptance contract](validation/ALPHA_ACCEPTANCE.md), D-074 review
cadence and D-078 runtime choices. The exact clean handoff HEAD includes this
record, [STATUS](STATUS.md) and the [Alpha showcase](demo/ALPHA_SHOWCASE.md), and
is bound by the external sanitized `s7-final-automation.json` generated after
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
  `fix(live-voice): close S7 review evidence gaps`.

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

Independent review then found two valid P2 automation weaknesses. The repairs
at `c2d3b2c4` passed 57 runner/probe tests, changed-file Ruff, the exact
21-diagnostic baseline helper and `git diff --check`. A 16 MiB clean privacy
sample was separately timed; later-corpus raw and base64 PCM16/f32le samples
were all rejected. The final clean handoff candidate received the full runner
again after this documentation commit; `s7-final-automation.json` is the
sanitized authoritative report and remains outside Git.

Generated frontend output is excluded from candidate identity and did not dirty
the worktree. The local locked environment was reconciled with `uv sync
--frozen`; machine-local environment changes were not committed.

## 4. Canonical real-probe outcome

All five repository entrypoints were invoked on the committed candidate. They
returned content-free failure identifiers and no sample; no fake observation,
`VERIFY` or `PASS` was created.

| Probe | Status | Samples | Actual outcome | Cause / shortest path |
|---|---|---:|---|---|
| Speech/Media | `ENVIRONMENT` | 0 | `REQUIRED_ENV_MISSING` | No fresh S7 speech/media observation exists. Run 5-20 controlled fixed-corpus rounds through the D-078 Streaming route and bind the closed observation to the exact candidate/runtime digest. |
| Agent/Executor | `ENVIRONMENT` | 0 | `REQUIRED_ENV_MISSING` | No fresh S7 formal-route observation and paired completion/cancellation no-remote fixtures exist. Produce them with the isolated Direct Project Executor route. |
| Benchmark/Fault | `ENVIRONMENT` | 0 | `REQUIRED_ENV_MISSING` | No fresh 13-target/13-fault S7 observation exists. Run the controlled route/fault producer on the exact candidate. |
| Secure deployment | `ENVIRONMENT` | 0 | `SECURE_RUNTIME_UNOBSERVED` | The available controlled origin is localhost. The formal S7 probe requires a non-loopback private FQDN resolving only to private addresses, trusted TLS, same-origin HTTPS/WSS and the declared proxy/CSP/CORS route. |
| Privacy | `ENVIRONMENT` | 0 | `REQUIRED_ENV_MISSING` | No fresh exact-candidate 19-surface manifest/capture root exists. Capture the declared surfaces externally, then scan with Gateway-only secret inputs without printing or copying them. |

Previously accepted S6 observations were made on earlier source and a different
acceptance boundary. They remain valid S6 history but cannot be rebound to this
S7 candidate. Current long-running controlled services were not counted as S7
proof because they had not been restarted on the final candidate and cannot
supply the missing formal origin or observation producers.

## 5. Cumulative Tier-3 review

Main reviewed `2a69c2b8..candidate` across:

- P1 capture/recognition/synthesis/playout and P2 media ownership;
- P2 response/progress/cancel and P3alpha Task/attempt authority;
- frontend, Gateway, AgentServer, Store, Executor, outbox, restart and cleanup;
- observability/privacy, malformed/error/timeout/reconnect and flag-off paths;
- response/round/task cancellation domains, stale-generation fencing and all
  applicable forbidden side effects.

The independent read-only review found no Critical/High product-source issue.
It found three P2 items:

1. file-wide Ruff code waivers could hide new debt - valid and fixed by the
   exact diagnostic fingerprint;
2. the privacy sentinel could miss later PCM16 and formal `pcm_f32le` raw audio -
   valid and fixed with complete-corpus representation-specific sentinels,
   raw/base64 regressions and bounded matching;
3. STATUS still said S7 had not started - valid and fixed by this documentation
   closure.

The affected source fixes received an independent re-review. The reviewer used
the same shared worktree in read-only mode rather than a separate worktree;
fixed SHA boundaries preserved review scope. Real probe absence remains an
evidence limitation and was not converted into a source finding.

## 6. Exit and handoff decision

| State | Result |
|---|---|
| S7 automation ready | Yes |
| S7 real-path verified | No - `ENVIRONMENT`, 0/5 verified |
| S7 cumulative source review complete | Yes - no open Critical/High finding |
| A3 handoff ready | No - requires S7 real-path completion on the same candidate |
| Alpha human acceptance complete | No - S8/A3 has not started |
| S7/A2 exit satisfied | No |

There is no known source gap and no remaining automatic-check gap. The shortest
remaining path is the three-step environment route in [STATUS](STATUS.md):
establish the formal private DNS/TLS topology, produce the four fresh closed
observation/capture inputs on the exact candidate, then rerun all five probes
through `--require-real` and review their actual producer invocations/results.
Only after S7/A2 closes may the user execute the A3 showcase. This record does
not claim `PASS - INTEGRATED WEB ALPHA`.
