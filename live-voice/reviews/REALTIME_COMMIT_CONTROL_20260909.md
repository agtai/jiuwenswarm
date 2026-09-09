# Realtime rollback control — 2026-09-09

## Question and boundary

The user requested an exact `a8afe0cadc8fabfbb809ff519d2d64ff4bf2cca9`
control, then inspection of `d1beb113b0310f5ab508ea3f528ca8b77a5b469f` and
`5cd46346d7e9638ee4077c555295163c94dfbb08`. The history is linear:
`a8afe0c -> d1beb113 -> 5cd46346`. No product fix, history rewrite, remote
update, NIC/proxy change or source-SDK substitution was made for this control.

An independent worktree, `live voice hx-control-a8afe0c`, retained the exact
baseline with a clean tracked tree. Its own editable import mapping, Python
subprocess source paths and Session file Git-object hash were checked. It used
Python 3.11.15, websockets 15.0.1 and the same installed AgentCore package
`0.1.16+jiuwenswarm.responses2` as the Demo. Model settings remained
gpt-realtime-2.1, speed 1.25, minimal, server-vad-450, generation interruption on.
The page and media origin were `http://127.0.0.1:5173`.

Private configuration was copied without exposing secrets. A fresh project and
Task database isolated the test; all 37 original input files matched their
hashes. The project Git setting `core.autocrlf=false` isolates the older,
separately diagnosed worktree conversion defect. This recreates the old **code
in today's environment**, not yesterday's entire machine, SDK or network state.

The fresh installation's first Agent cold start exceeded the launcher's 120 s
readiness bound. The retained process subsequently became ready: Agent 16:15,
Gateway/Web 16:17 local time (UTC+02). The real browser activated successfully,
and Provider session configuration was acknowledged. The timed-out launcher run
does not receive formal startup-contract credit. Its later browser observations
are preserved separately. The owned browser injected recorded PCM through
getUserMedia; it did not measure a physical microphone or headphones.

## Exact baseline observations

Control session: `web_1a08688339b_e43aa00036ed`. Both spoken inputs were
“深圳靠海吗？用一句话回答。” No voice Task creation, query or adjustment was sent;
the page's ordinary automatic task-list/notification reads remained active.

| Control observation | Result |
|---|---|
| First ordinary input | No scheduled output audio; at 16:19:29.662, Gateway reported `MEDIA_NATIVE_INPUT_BACKPRESSURE` |
| Explicit relisten, second ordinary input | No scheduled output audio; at 16:26:12.504, the same queue-full reason recurred |
| Browser boundary | Both activations detached with `MEDIA_CONSUMER_FAILED`; no first-sound latency can be reported for either failed turn |
| Exact failing code | `input_queue.put_nowait` raised `asyncio.QueueFull`; capacity is 800 Native frames, nominally 16 s at 20 ms/frame |
| First failure's main-thread samples | Agent 330/336 and Gateway 299/336 samples were in the event-loop I/O poll; no sustained multi-second synchronous stack was observed |

Samples are supporting observations, not an exact CPU or scheduling exclusion.
The old Session does not time every audio append. Browser queue saturation alone
does not identify the precise upstream transport cause.

A separate 45 s probe therefore used the baseline's actual Session/socket
factory and 20 ms PCM append format, with no Agent, Task, interruption handler,
Registry query, browser playback or stack observer in that probe process. It
retained default socket settings (observed TCP_NODELAY=0), with no peer override.

| Raw baseline transport measurement | Observed |
|---|---:|
| Peer | 162.159.140.245 |
| Maximum awaited socket send | 2378.642 ms |
| Maximum dequeued-frame residence | 6504.430 ms |
| Maximum sampled queue depth | 324 frames |
| Maximum probe event-loop lag | 24.401 ms |
| Source frames / sent before probe stop | 2250 / 1943 |
| Final TCP retransmitted-byte counter | 277232 bytes |
| Final TCP timeout-episode counter | 52 |

The raw probe produced first output earlier in the run, then accumulated input.
Short successful speech is not sustained transmission acceptance. TCP counters
are local transport observations, not proof that Wi-Fi, the external network or
OpenAI is the originating faulty component. The probe ended at its fixed source
deadline; unsent frames were not credited as delivered.

## Inspection of the two commits

`d1beb113` changes Native response retirement: it revokes receive admission
before awaiting the Runtime fence, preserves completed played history and keeps
the later exact playback-stop cursor admissible. It does not change capture,
PCM queuing, socket send, compression, TCP options or Provider input.

`5cd46346` moves slow P3 reads outside the Registry lock, retains their tasks
through caller cancellation and drains them before stopping shared resources.
The authorized query body remains the same apart from short cleanup relocks.
Removing serialization can change concurrent read load, so a static diff alone
cannot exclude all indirect performance effects. The raw failing control does
not execute this code at all.

The exact two-commit candidate was checked out only after stopping the owned
baseline server. Native Runtime and query-lifecycle tests passed **42/42 in
26.35 s**, including late audio/done/ACK rejection, played-history preservation,
STOP cancellation/retry, slow-query audio/ACK/STOP concurrency, cancelled-query
thread ownership, shutdown, revoked authority and route close during a query.
The initially attempted default coverage run was stopped after its output
ceased advancing at 41 passes; it is retained as incomplete. The remaining
case passed alone (25.02 s including collection), and the entire bounded rerun
passed with `--no-cov`. The initial non-completion was not causally attributed
to coverage, a product deadlock or host load.

Commands: `git diff a8afe0c 5cd46346 --name-only`, complete scoped `git show`
for each implementation diff, and pytest for
`test_native_interaction_runtime.py` plus `test_product_query_lifecycle.py`.
Session, Native Engine, dedicated media, Code adapter and Deep adapter files
are byte-identical between these two control revisions.

**结论：回到两个修复之前，上行积压和断开仍能复现。撤销这两个提交不能解决
当前故障；现有证据不支持把它们认定为上行积压的必要触发条件。这个结果不等于
证明两个提交在所有场景都没有问题，也不能据此断言 Wi-Fi 故障。**

## Other root-cause evidence retained during this continuation

The preceding low-load transport controls completed after the user paused other
work. One still reached 2382.407 ms send wait and 5339.150 ms queue residence;
another reached only 5.457 ms and 88.798 ms. The user-stopped third attempt is
excluded. Persistent CPU saturation is not necessary for reproduction, but
variable connections and residual memory/driver pressure prevent a sole-cause
attribution. The same Wi-Fi having worked yesterday remains relevant history.

Separately, the earlier real Task receipt timeout delivered only 8 x 20 ms to
the browser before its 4 s buffer deadline. A Native admission batch took
4297.008 ms with only 0.037 ms Registry lock wait. It overlapped synchronous
Code runtime-state preparation and cold SDK context construction on the Agent
loop. Offline, real Code state/Git collection took 1384.673 ms and blocked the
loop for 1374.881 ms; cold SDK context creation took 1035.438 ms and blocked it
for 1025.601 ms, primarily eager trafilatura initialization. These local blockers
are independent of the two commits and are **not repaired by this control**.
Their proper repair needs owned off-loop work/readiness with preserved ordering
and cancellation, not larger buffers or discarded audio. They do not explain
away the separate raw transport retransmission evidence.

## Evidence and closure

Control evidence is private under `logs/commit-control/`: the two exported
browser diagnostics, `baseline/browser/events.jsonl`, original service log,
`transport-baseline-transport.json`, both test attempts and bounded-test output.
`baseline/result-summary.json` binds the raw files to SHA-256 hashes. Demo
private `repair-probes/` retains low-load transport/host records, the two offline
blocking probes and exact receipt timeout records. No payloads or credentials
were added to tracked evidence.

The owned control browser and service were stopped. Original Demo project
inputs remained unchanged (37 hashes); its previously generated
`秋日广州行程.md` was preserved. At 16:38 local time the regular launcher restored
the original Demo from source `37719212e9` (product implementation `9e9e5ebc`),
with that known additional file admitted at startup. The frontend build,
four local ports, route/bundle checks, real Speech round-trip and formal
receipt/identity/forged-claim checks passed; no business operation was executed
by that readiness probe. Its runtime contract confirms gpt-realtime-2.1 /
1.25 / minimal / server-vad-450. This is startup evidence, not repaired sustained
Realtime transmission or another human listening acceptance. The service log is
`logs/swarm-20260909-163652.log` in the Demo worktree.
The control worktree remains available without replacing Demo history. This
control closes the requested rollback/commit inspection, not the remaining
transmission repair, complete Task adjustment journey or physical calibration.
