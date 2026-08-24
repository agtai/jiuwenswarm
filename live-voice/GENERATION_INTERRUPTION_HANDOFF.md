# Agent generation-time interruption — handoff

**Branch:** `hx/0823_generation_interruption`
**Base (merge-base, not a ref):** `9a3a65fd0fa1d5ef4f680a9eda61d0482dd1f789`
**Current worktree:** `C:/Users/admin/Desktop/live voice hx-generation-interruption`

The original implementation was verified by automation, but a 2026-08-24
targeted closure review found two Important defects (`C0/I2/M0`). The atomic
Runtime-ledger defect is repaired on `30300f32`; the cross-capture release race
is repaired by source candidate `35537a9a`, which retains an exact predecessor
plus successor, composes one Batch final and fences both competing Streaming
commit paths. **Nothing has run on a real device. One bounded independent
Tier-3 review of `35537a9a` remains before physical acceptance.**

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
| Python interpreter | In the current machine use `C:/Users/admin/Desktop/live voice hx/.venv/Scripts/python.exe`. The conda base is missing `httpx`/`websockets`/`aiohttp`/`loguru` and collection errors look like broken code. |
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

### Current `35537a9a` continuation checks

The table above is the historical broad baseline. The exact new source boundary
has these fresh results:

| Check | Result |
|---|---|
| Batch Speech + Media registration/RPC + product authority + Streaming Speech + Python media transport | `257 passed` |
| Formal Integrated Web | `496 passed` |
| Browser Gateway Media / Browser Dedicated Media / Gateway Batch Speech | `38 / 27 / 30 passed` |
| Ruff / `git diff --check` / `npm run build:live-voice` | PASS |

The review target is the immutable code/test commit `35537a9a`; documentation
may be a later commit. Do not ask the reviewer to reopen the five historical
broad rounds. Review only the cross-capture request, media-authority chain,
receipt fence, replay boundary and cleanup diff introduced by this candidate.
Use the prepared
[targeted review prompt](reviews/GENERATION_INTERRUPTION_CROSS_CAPTURE_TIER3_REVIEW_PROMPT_2026-08-24.md).

## 4. Where the code is

**Backend**

| File | Role |
|---|---|
| `server/live_voice/conversation_runtime.py` | `response_fence_state(ref)` — O(1) admission check for high-frequency token traffic |
| `server/live_voice/conversation_runtime_loop.py` | `interrupt_generation` / `post_generation_interrupt`, and the bounded replay ledger (`_RetainedGenerationInterrupt`, oldest-first, cap 256, never evicts an action whose future is pending) |
| `server/live_voice/agent_conversation_runtime.py` | `interrupt_generation` — the fence, the fixed `round.cancel` command, dropping an already-queued presentation, and `submit_committed_turn(..., supersedes=)` which fences **before** committing the replacement |
| `server/live_voice/product_p2_interaction_adapter.py` | `P2ActivationLease.interrupt_generation` (no scope argument exists) |
| `server/live_voice/product_composition_registry.py` | `handle_p2_interrupt_generation` — production wiring; rejects a client-supplied `cancel_scope` |
| `gateway/live_voice/dedicated_media_registration.py` | Verifies the predecessor-close and successor-activation chain, exact per-segment digests and the no-Streaming-receipt fence |
| `server/live_voice/batch_speech.py` | Parses the optional predecessor, composes PCM in memory in exact order and atomically reserves both capture identities |

**Frontend**

| File | Role |
|---|---|
| `features/live-voice/formal/productP1VoiceRoute.ts` | `on_generation_speech_start`, and `abandonCapture(reason)` — releases a silent listening window, but when the provider reports speech during `stopCapture` it opens a **real successor capture** instead |
| `features/live-voice/formal/gatewayBatchSpeechClient.ts` | Emits two separately finalized WAV segments only for the one accepted predecessor/successor continuation |
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

## 5. Physical acceptance — blocked until one source review closes

Do not run this as acceptance yet. `35537a9a` now has an automated
full-utterance/EOT oracle: the predecessor prefix and successor tail retain
separate exact capture authorities, Gateway validates both, and one combined
Batch final is returned. Physical credit is still blocked until one independent
Tier-3 review of that exact commit closes with no unresolved finding.

After that review, this physical run needs a person with headphones. Headphones remove the
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

**Acceptance is complete only when:** the cross-capture source review is closed,
all three scenarios behave, the affected suites still pass, and the flag can be
turned back off with no residue.

## 6. What is knowingly not covered

* **No physical run of any kind has happened yet.** No latency number is
  claimed, including for the listening window itself.
* **The late release-race source repair is not independently accepted yet.**
  `35537a9a` implements the D-096 two-authority Batch boundary and its automated
  oracle, but the required independent review and physical observation remain
  open.
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
`30300f32`, while its full-utterance finding is implemented by the explicitly
re-scoped D-096 candidate `35537a9a` and awaits one bounded independent review.
Full narrative in
[evidence](evidence/GENERATION_TIME_INTERRUPTION_20260823.md), decision record
in [D-095](decisions/DECISIONS.md).

Of the 25 findings, 9 were real defects in the original implementation, 6 were
incomplete repairs of earlier findings, and the rest were counts, wording and
base-SHA drift. The 6 are the reason this took five rounds instead of two: the
pattern was making the smallest change that turned a case green instead of
asking whether the invariant held on every path. The current candidate therefore
fences both predecessor and successor Streaming receipts at the server seam,
instead of relying only on the browser not to request them.

**The base ref moves.** `hx/0812_live_voice_w3` was amended four times and
advanced three more times during this work. Resolve the base with
`git merge-base hx/0812_live_voice_w3 HEAD` — never by ref name and never by a
left/right count. Integration needs its own re-freeze against wherever that ref
points then.
