# Live Voice manual latency-driver runbook

> Owner: latency lane (`latency/hx-optimizations`). This documents the
> interactive manual measurement flow introduced on `497831f58+`. It is a
> diagnostic procedure: it grants no baseline, Gate C or product-readiness
> credit by itself. The formal baseline procedure remains §7.6 of
> [E2E_RUNBOOK](E2E_RUNBOOK.md); this driver automates its mechanics.

On 2026-08-25 LVL-09 measured approximately 670–673 ms of target-segment
headroom, but A2 cancelled after first-start. A later use of this driver must
retain the same-tab allocator and wait through complete playout; the result
does not authorize changing the 1000 ms default. Scoped verification belongs
in the optimization inventory and retained run artifacts rather than this
operator procedure.

## 1. What the driver does

`<archive-root>/lv-driver.sh` (archive root:
`/home/renan/openJiuwen-ai/live-voice-latency-runs/`, outside the repo):

- launches the full stack with the complete environment contract (below);
- prints the stage URL for each declared profile/case (no browser auto-open);
- monitors `<run-dir>/browser.jsonl` and beeps when a batch exports;
- snapshots every exported batch to `snapshots/stage<N>-round<K>.json`;
- keeps progress in `snapshots/state.json` (survives restarts);
- performs graceful shutdown (SIGINT → bounded drain → SIGTERM) and runs
  `latency_probe_report report` on finish.

## 2. Environment contract (what previously failed silently)

Every backend process needs ALL of:

1. Product flags (runbook §7.5): `P3_ENABLED`,
   `P3_EXECUTOR_PROFILE=live-voice.direct-project-code.d2.v1`,
   `PRODUCT_COMPOSITION_ENABLED`, `PRODUCT_P2_ENABLED`,
   `PRODUCT_P3_TEXT_ENABLED`, `PRODUCT_P3_MUTATION_ENABLED`,
   `CRITICAL_INPUT_ENABLED`, `PRODUCT_DEMO_POLICY_BYPASS_ENABLED`,
   `DEMO_ADJUSTMENT_CHECKPOINT_ENABLED`, `DEDICATED_MEDIA_ENABLED`,
   `END_OF_TURN_ENABLED`.
2. Probe trio: `LATENCY_PROBE_ENABLED=1`, `_RUN_CONFIG=<run-dir>/run.json`,
   `_OUTPUT_ROOT=<archive-root>`.
3. **Authenticated P3 authority** (the launcher normally provisions these;
   the driver now mints them):
   - `JIUWENSWARM_LIVE_VOICE_P3_AUTH_TOKEN` — fresh random 32-byte base64;
   - `JIUWENSWARM_LIVE_VOICE_P3_AUTH_EXPIRES_AT` — UTC now +12h, RFC3339;
   - `JIUWENSWARM_LIVE_VOICE_P3_PRINCIPAL_ID` = `local-live-voice-demo`;
   - `JIUWENSWARM_LIVE_VOICE_P3_PROJECT_IDS` = registered disposable project
     id (current fixture: `proj_f71b3e9c`);
   - `JIUWENSWARM_LIVE_VOICE_P3_DATABASE` — see rule 4.
4. **Fresh P3 store per run**: the database must stay under
   `<DATA_DIR>/live_voice/p3alpha/` AND must not reuse a ledger written by an
   older build (fingerprint check fails closed). The driver uses
   `formal_tasks_<run-id>.sqlite3`.
5. Frontend (Vite process only): `VITE_FEATURE_LIVE_VOICE_LATENCY_PROBE=true`
   plus `VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB=true` and
   `VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1=true`.

Topology note: in dev there are exactly THREE processes. The Gateway binds
`WEB_PORT` 19000 itself (it IS the WebChannel). Do NOT start
`channels.web.app_web` in dev — it collides on port 19000. Vite proxies
`/ws` to 19000; AgentServer stays on 18092.

## 3. Session requirements (browser side)

- Open one of the stage URLs; create/open ONE session bound to the
  registered disposable project. Task stages have real side effects there.
- Keep the same tab for all stages; reload between stages preserves the
  per-profile `round_index` in `sessionStorage`. Opening another tab or
  relaunching with cleared session state can restart at round 0 and invalidate
  later arms.
- A `completed` round reaches export after playout ACK + successor capture
  ready. Reloading, barge-in or advancing earlier can export a `cancelled`
  batch instead.
- In LVL-09 manifest mode, only an exact matching `completed` batch is
  advance-eligible. Cancelled/failed/unknown rows are retained and named from
  their authoritative profile/case/round/outcome, but do not advance.
- Failed/cancelled rounds do not receive complete-round credit. Observed
  same-clock mark pairs may be preserved as explicitly partial diagnostics;
  absent pairs remain `unknown` and must not enter p50/p95 or A/B/A summaries.
- For a startup-lead screen, use a short frozen workload whose playout remains
  below the 30-second successor-capture rotation boundary. Do not speak, reload
  or disable Live Voice until playout finishes and the eligible beep sounds.

## 4. Usage

```bash
lv-driver.sh <run-id> --launch     # launch stack + collect + report on q
lv-driver.sh <run-id>              # attach mode: stack already running
lv-driver.sh <run-id> --smoke      # non-interactive: start, validate ports,
                                   # graceful shutdown, generate report
LV_WORKTREE=<clean-lvl09-worktree> lv-driver.sh <run-id> --launch \
  --lvl09-manifest=<run-dir>/lvl09-arms.json
```

Interactive commands: `[Enter]`=next stage · `b`=back one stage ·
`r`=reset to stage 1 · `s`=status · `u`=reprint URL · `q`=finish
(shutdown + report).

Stage table lives in the script header (`STAGES=(...)`); edit phrases there.
Run config: `<archive-root>/<run-id>/run.json` — validate before starting:

```bash
uv run python -m jiuwenswarm.server.live_voice.latency_probe_report \
  validate-run --run-json '<run-dir>/run.json'
```

Service commands live in `<archive-root>/lv-launch.conf` (`name=command`,
plus `DATA_DIR=`). Logs: `<run-dir>/logs/{agentserver,gateway,vite,driver}.log`.

## 5. Troubleshooting (observed failure signatures)

| Symptom | Log signature | Cause / fix |
|---|---|---|
| "Live Voice desativado" button | `central registration failed closed: enabled product composition requires authenticated P3 authority` | Missing/invalid P3 authority env (rule 2.3) — driver mints them |
| Startup fails closed again right after | `formal Task command ledger fingerprint is inconsistent` | Old ledger from a previous build — use a fresh per-run DB (rule 2.4) |
| Startup fails closed, path error | `P3 database must remain under the application-owned P3 directory` | DB path must be under `<DATA_DIR>/live_voice/p3alpha/` |
| Page stuck at "Loading conversation history…" | gateway log: `未连接 AgentServer，请先调用 connect(uri)` | Gateway lost its AgentServer link (driver died) — relaunch the stack |
| Voice recovery failed (text, `UNIFIED_INPUT_FAILED`) | agentserver: `handle_unified_submit() got an unexpected keyword argument 'latency_probe'` | Merge regression — fixed on `497831f58+`; keep registry/server in sync |
| LVL-09 row is retained but cannot advance | terminal is not `completed`, or profile/case/round differs from the manifest arm | Preserve the row as partial/failed evidence; changed frozen state requires a fresh run |
| LVL-09 A2 reaches first start but exports `cancelled` | `live_voice.composition.p2.barge_in` after the first-start mark | Retain the target pair as partial diagnostic only; a completed replacement requires a fresh run and no speech/reload/disable action until playout ends |
| LVL-09 arm restarts at round 0 | unified submit carries an earlier `round_index` than the manifest arm | The Browser allocator lost `sessionStorage`; use one unchanged Chrome tab for the complete fresh run |
| Vite/Gateway remains after driver exit | port still bound after `q` | Treat this as cleanup failure; stop only the driver-owned process group/tree before a new run |
| Port 19000 bind conflict (`Errno 98`) | two services racing | Do not run `app_web` in dev; Gateway owns 19000 |

## 6. Non-claims

Diagnostic evidence only. No baseline credit without the §7.6 conditions
(clean source, independent Tier-3 review of the probe commit, warm/cold
separation, full denominators, frozen corpus). Remote refs, credentials and
project registration state remain outside Git and require their own
authority.

The historical driver version bound in
[the 2026-08-24 muted pilot](../evidence/MANUAL_MUTED_LATENCY_PILOT_20260824_37da36e68.md)
lacked terminal/profile/round-aware advance and complete process-tree
shutdown. The later private LVL-09 setup repairs those mechanics, but the
2026-08-25 [pilot](../evidence/LVL09_ADAPTIVE_PLAYOUT_LEAD_PILOT_RESULT_2026-08-25.md)
still grants target materiality only, not physical acceptance.
