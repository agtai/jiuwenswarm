# Agent generation-time interruption — handoff

**Branch:** `hx/0823_generation_interruption`
**Base (merge-base, not a ref):** `9a3a65fd0fa1d5ef4f680a9eda61d0482dd1f789`
**Worktree used so far:** `D:/XGG AI/openjiuwen/jiuwenswarm-gen-interrupt`

The original implementation was verified by automation, but a 2026-08-24
targeted closure review found two Important defects (`C0/I2/M0`). The atomic
Runtime-ledger defect is repaired on `30300f32`; the browser release race can
still recognize only the successor capture and lose the start of the user's
utterance. A truthful repair requires an explicitly re-scoped cross-capture
Realtime Media/Speech authority boundary. **Nothing has run on a real device,
and physical acceptance must not begin until that source boundary closes.**

---

## 1. What the feature does

Hands-free speech that arrives **while an Agent answer is still being
generated** can stop or replace that exact answer. Before this change a user
could only barge in after playout had started; speaking during generation did
nothing, and the answer they no longer wanted was still spoken in full.

Five properties define it, and every one has automated coverage:

1. Controlled committed speech is still accepted during generation.
2. New input stops or replaces the **exact** current round/response.
3. Old token, final, TTS enqueue, presentation ACK and assistant history are all
   refused by the generation fence — including a presentation already sitting in
   the delivery queue.
4. It never widens into a background Task cancel. The scope is fixed at
   `round.cancel` in the runtime; no interface layer accepts a scope argument.
5. It holds under Exit, Session switch, browser capture ownership surrender and
   concurrent Task notification.

**Default off**, behind `VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION`.
Note this is browser-behaviour parity only: the new RPC is not gated by the Vite
flag and is always registered server-side and in the Gateway allowlist, so an
authenticated P2 client calling it explicitly still executes.

## 2. Environment — read before running anything

These cost real hours when they were learned. All of them still apply.

| Trap | What to do |
|---|---|
| `pytest -o addopts=''` | **Never.** It clears `--asyncio-mode=auto` and fabricates dozens of failures. Just add `--no-cov`. |
| Python interpreter | Use `D:/XGG AI/openjiuwen/jiuwenswarm/.venv/Scripts/python.exe`. The conda base is missing `httpx`/`websockets`/`aiohttp`/`loguru` and collection errors look like broken code. |
| `node --test <file>` directly | **Never for verification.** It runs the previously compiled cache, so a mutant you just introduced is not in the code under test and the check is a false negative. Always go through `npm run test:live-voice-*`. |
| A new worktree needs `node_modules` | Junction it to the main repo: `New-Item -ItemType Junction -Path <new>/jiuwenswarm/channels/web/frontend/node_modules -Target <main>/jiuwenswarm/channels/web/frontend/node_modules` |
| Removing such a worktree | `cmd /c rmdir <link>` **first**, then `git worktree remove`. `--force` walks through the junction and empties the main repo's `node_modules` (recovery is `npm ci`). |
| Editing files from PowerShell 5.1 | Don't. It writes a BOM and reads UTF-8 as CP936. Use Python or the editor tooling. |

## 3. Verification — expected values on this base

```bash
# backend focused
"D:/XGG AI/openjiuwen/jiuwenswarm/.venv/Scripts/python.exe" -m pytest \
  tests/unit_tests/live_voice/test_generation_time_interruption.py \
  tests/unit_tests/live_voice/test_agent_conversation_runtime.py \
  tests/unit_tests/live_voice/test_conversation_runtime.py \
  tests/unit_tests/live_voice/test_conversation_runtime_loop.py \
  tests/unit_tests/live_voice/test_product_p2_interaction_adapter.py -q --no-cov

# backend full sweep (~10 min)
"...python.exe" -m pytest \
  tests/unit_tests/live_voice/ tests/unit_tests/gateway/ tests/unit_tests/common/ -q --no-cov

# frontend, from jiuwenswarm/channels/web/frontend
npm run test:live-voice-integrated-web
npm run test:live-voice-l0-measurement
npx tsc --noEmit -p tsconfig.json
npm run build:live-voice
```

| Suite | Expected |
|---|---|
| `test_generation_time_interruption.py` (new) | 19 passed |
| backend focused (5 files) | 189 passed |
| `test_product_composition_registry.py` | 176 passed, 6 pre-existing failures |
| backend full sweep | 3961 passed, 2 skipped, **11 failed — all pre-existing** |
| Formal Web | 496 passed (478 baseline + 18 new) |
| L0 measurement | 5 passed |
| typecheck / build | clean |

The 11 sweep failures reproduce identically in a clean worktree of the base
commit; the nodeids are listed in the evidence record §6. Do not spend time on
them.

`test_partial_activation_failure_rolls_back_runtime` is load-sensitive and
unrelated to this work: its own fixture uses `cleanup_timeout_seconds=0.02`, and
under heavy parallel load the bounded rollback wait expires and the result
becomes `ROLLBACK_FAILED`. It failed twice this way across the whole effort.
Re-run it alone before treating it as a finding.

## 4. Where the code is

**Backend**

| File | Role |
|---|---|
| `server/live_voice/conversation_runtime.py` | `response_fence_state(ref)` — O(1) admission check for high-frequency token traffic |
| `server/live_voice/conversation_runtime_loop.py` | `interrupt_generation` / `post_generation_interrupt`, and the bounded replay ledger (`_RetainedGenerationInterrupt`, oldest-first, cap 256, never evicts an action whose future is pending) |
| `server/live_voice/agent_conversation_runtime.py` | `interrupt_generation` — the fence, the fixed `round.cancel` command, dropping an already-queued presentation, and `submit_committed_turn(..., supersedes=)` which fences **before** committing the replacement |
| `server/live_voice/product_p2_interaction_adapter.py` | `P2ActivationLease.interrupt_generation` (no scope argument exists) |
| `server/live_voice/product_composition_registry.py` | `handle_p2_interrupt_generation` — production wiring; rejects a client-supplied `cancel_scope` |

**Frontend**

| File | Role |
|---|---|
| `features/live-voice/formal/productP1VoiceRoute.ts` | `on_generation_speech_start`, and `abandonCapture(reason)` — releases a silent listening window, but when the provider reports speech during `stopCapture` it opens a **real successor capture** instead |
| `components/ChatPanel/LiveVoiceIntegratedRoutePanel.tsx` | The window's whole lifecycle. Two names carry the invariants that five review rounds converged on: `ownerHasUnsettledGenerationInterrupt(owner)` — the single question every barrier asks; `retireGenerationListening(matches?)` — the single place every retirement path goes through |

Two invariants are worth stating in words, because both were defects first:

* **A barrier belongs to an owner, not to the world.** An unsettled interruption
  closes its own activation's capture, listening window, announcement
  arbitration and turn admission. A *retired* activation's handle must close
  nothing — matching on "any pending interruption" once fenced every later
  Session out of listening for the life of the page.
* **A listening window left behind silently disables the feature.** The next
  answer is refused a window while one is retained, so every path that ends the
  window's reason to exist must retire it: Session switch, Exit, capture
  ownership surrender, and the exact response failing.

## 5. Physical acceptance — blocked until source closure

Do not run this as acceptance yet. If provider speech-start arrives while
`abandonCapture` is releasing the old track, the route opens a real successor
capture but recognizes only frames from that successor. Frames already recorded
under the predecessor capture are cleared, so scenario 2 can submit only the
tail of the utterance. The existing test proves old-track/new-track liveness,
not end-of-turn recognition of the complete sentence.

After a separately scoped Media/Speech continuation repair passes targeted
review, this physical run needs a person with headphones. Headphones remove the
echo/double-talk risk entirely, so what is being judged is timing and accuracy,
not acoustics.

Turn on `VITE_FEATURE_LIVE_VOICE_GENERATION_INTERRUPTION` and run three
scenarios:

1. **Idle window.** Submit a question, then stay silent while the Agent
   generates. The microphone is open for that whole window — confirm nothing
   false-triggers (breathing, room noise, keyboard) and the answer plays
   normally.
2. **Interrupt and replace.** Submit a question; while the answer is still being
   generated, say something like "算了，换个问题". Judge three things: how long
   until it stops, whether the new utterance was recognised in full (not just
   its tail), and whether the next answer addresses the new question.
3. **Task concurrency.** Start something that runs as a background Task, then
   interrupt a generation while it is running. The Task must keep running and
   still report — the interruption is `round.cancel`, never `task.cancel`.

While these run, the logs to watch are the `action_id` of each interruption, the
`response_id` it names, and the `round_id` in the cancel command — they have to
line up with the answer the user actually meant to stop.

**Acceptance is complete only when:** the cross-capture source Gate is closed,
all three scenarios behave, the affected suites still pass, and the flag can be
turned back off with no residue.

## 6. What is knowingly not covered

* **No physical run of any kind has happened yet.** No latency number is
  claimed, including for the listening window itself.
* **Late release-race speech can lose its prefix.** The predecessor and
  successor frames have different exact capture/media authorities; current
  Batch recognition accepts one capture. Relabeling or concatenating in the
  browser would falsify provenance, so this is a Tier-3 re-scope rather than a
  local state fix.
* Seven mutants survive, in two groups — two halves of one Exit repair that are
  redundant against each other (the combined mutant *is* killed), and five state
  hygiene guards whose external effect another guard already provides. Evidence
  §3.1.
* Five invariants have **no** mutation-sensitive oracle at all. Evidence §3.2.
  None of them can disable the feature; they are places where a future
  regression would go unnoticed.
* `pauseIdleCaptureForNotification` has the same "advance the generation before
  stopping the capture" shape that was a real defect in `abandonCapture`. It is
  pre-existing P2-notification code, outside this change, and **was not
  repaired**. It is a genuine candidate for the same fix.

## 7. History, if you need it

Five broad independent Tier-3 reviews returned `C0/I2/M0`, `C0/I6/M2`,
`C0/I4/M3`, `C0/I3/M3`, `C0/I3/M3`. A later targeted closure review on
`b476873b` returned `C0/I2/M0`: its atomic-ledger finding is repaired on
`30300f32`, while its full-utterance finding remains open pending explicit
re-scope. Full narrative in
[evidence](evidence/GENERATION_TIME_INTERRUPTION_20260823.md), decision record
in [D-095](decisions/DECISIONS.md).

Of the 25 findings, 9 were real defects in the original implementation, 6 were
incomplete repairs of earlier findings, and the rest were counts, wording and
base-SHA drift. The 6 are the reason this took five rounds instead of two: the
pattern was making the smallest change that turned a case green instead of
asking whether the invariant held on every path. If you repair something here,
enumerate the call sites with `grep` before claiming "every one is fixed", and
distrust any fix that is physically impossible but state-wise plausible.

**The base ref moves.** `hx/0812_live_voice_w3` was amended four times and
advanced three more times during this work. Resolve the base with
`git merge-base hx/0812_live_voice_w3 HEAD` — never by ref name and never by a
left/right count. Integration needs its own re-freeze against wherever that ref
points then.
