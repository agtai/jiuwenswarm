# LVL-10 Authoritative-Final Chunked TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a no-Browser real-Provider A1/B/A2 screen comparing current one-request full-final SSE TTS with bounded chunked TTS after authoritative `chat.final`.

**Architecture:** Phase 1 adds one validation runner and one frozen corpus/test module; it does not change product Runtime, Gateway, P2, Browser or Provider source. A1/A2 send the complete final text once. B sends one independent SSE TTS request per manifest-bound text chunk, prefetches at most one successor and releases PCM in original order.

**Tech Stack:** Python 3.11, asyncio, `OpenAIStreamingSpeechProvider`, pytest, portalocker, JSON/JSONL, SHA-256.

**Spec:** `live-voice/roadmap/AUTHORITATIVE_FINAL_SEGMENTED_TTS_MATERIALITY_SPEC_2026-08-24.md`

## Global Constraints

- Base every worktree on the same clean plan commit.
- No product source, Runtime, P2, Gateway media, Browser or UI modification.
- Synthesis starts only after complete immutable final text is supplied.
- B uses 1–4 exact text chunks, at most 2 concurrent requests and prefetch depth 1.
- PCM is mono signed 16-bit at 48,000 Hz; playable reserve is 12,000 samples / 250 ms.
- Automatic Provider retries are zero.
- Real Provider attempts are serialized by `/tmp/jiuwenswarm-lvl10-provider.lock`.
- Raw output goes under `/home/renan/openJiuwen-ai/live-voice-latency-runs/lvl10/$SOURCE_COMMIT/$RUN_ID/`.
- Main alone integrates history and edits shared documentation. No worker pushes.

## File map and ownership

| Owner | Exact files |
|---|---|
| Writer A, pane `1:0.0` | `scripts/live_voice/lvl10_segmented_tts_screen.py` |
| Writer B, pane `1:1.0` | `tests/fixtures/live_voice_lvl10_tts_v1/manifest.json`; `tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py` |
| Reviewer A, pane `0:0.0` | Read-only; `/tmp/lvl10-reviews/provider/review.md` |
| Reviewer B, pane `0:1.0` | Read-only; `/tmp/lvl10-reviews/oracles/review.md` |
| Main | Worktree creation, cherry-picks, integration, Provider run and documentation |

---

### Task 1: Create isolated worktrees and bootstrap panes

**Files:** No repository files.

- [ ] **Step 1: Record the plan commit and verify integration state**

```bash
cd /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-w3
PLAN_COMMIT=$(git rev-parse HEAD)
git diff --quiet
git diff --cached --quiet
git show "$PLAN_COMMIT:live-voice/roadmap/AUTHORITATIVE_FINAL_CHUNKED_TTS_MATERIALITY_IMPLEMENTATION_PLAN_2026-08-24.md" >/dev/null
```

- [ ] **Step 2: Use `superpowers:using-git-worktrees`, then create sibling worktrees**

```bash
git worktree add /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-validation -b latency/lvl10-validation "$PLAN_COMMIT"
git worktree add /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-provider-screen -b latency/lvl10-provider-screen "$PLAN_COMMIT"
```

- [ ] **Step 3: Verify isolation**

```bash
git -C /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-validation status --short --branch
git -C /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-provider-screen status --short --branch
git worktree list
```

Expected: different branches, identical HEAD, clean worker trees.

- [ ] **Step 4: Bootstrap pairwise communication**

Send each pane its worktree, owned files, peer target and the `REQUEST`, `RESULT`, `BLOCKED`, `OWNERSHIP_REQUEST`, `ACK` protocol from spec §12. Reviewers receive explicit read-only instructions. Writers must stop on any ownership collision.

### Task 2: Write the frozen corpus and RED contract tests

**Files:**
- Create: `tests/fixtures/live_voice_lvl10_tts_v1/manifest.json`
- Create: `tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py`

**Interfaces:**
- Consumes: normative corpus from spec §6.
- Produces: failing tests for `PopulationRole`, `Lvl10Fixture`, `AttemptIdentity`, `AttemptRecord`, `load_fixture_manifest`, `run_attempt`, `derive_ordered_release_stall_ns`, `reduce_records`, and `main`.

- [ ] **Step 1: Create the exact manifest**

Use schema `live-voice.lvl10-corpus.v1` with these exact values:

```json
{
  "schema_version": "live-voice.lvl10-corpus.v1",
  "fixtures": [
    {"fixture_id":"short","final_text":"Paris is the capital of France.","offsets":[0,31],"sha256":"557be7eca214f1889cdb6dfa348eb7c937648c9d6be72bfc1b8204adf7552a43"},
    {"fixture_id":"medium","final_text":"The water cycle moves water continuously between Earth's surface and atmosphere. Evaporation and transpiration lift water vapor, which cools and condenses into clouds. Precipitation returns water as rain or snow, and runoff or infiltration carries it back to rivers, soil, and oceans.","offsets":[0,80,167,284],"sha256":"549d6140de0f261ff081c905b66b73b16a69bf016334e57805ac2919ed632d26"},
    {"fixture_id":"long","final_text":"Planning a three-day visit to Washington, D.C., works best when each day focuses on one area, because the U.S. capital has major sites spread across several neighborhoods. On the first day, walk from the Capitol and Library of Congress toward the museums of the National Mall, allowing enough time for security lines and indoor exhibits. On the second day, explore the memorials and the Tidal Basin; a 3.14-mile walking loop gives you a useful planning estimate without forcing a rushed pace. On the final day, visit Georgetown and Rock Creek Park, then leave a flexible evening window for weather changes, restaurant waits, or one museum you wanted to revisit.","offsets":[0,171,337,492,661],"sha256":"4dea077a8786e1ca01383b5ad60204629200c3047dbb98a8008c8f701db48c53"}
  ]
}
```

- [ ] **Step 2: Write manifest RED tests**

```python
def test_manifest_preserves_exact_chunks(manifest_path: Path) -> None:
    fixtures = load_fixture_manifest(manifest_path)
    assert [item.fixture_id for item in fixtures] == ["short", "medium", "long"]
    assert [len(item.chunks) for item in fixtures] == [1, 3, 4]
    assert all("".join(item.chunks) == item.final_text for item in fixtures)

@pytest.mark.parametrize("offsets", ([1, 31], [0, 0, 31], [0, 30], [0, 31, 32, 33, 34, 35]))
def test_manifest_rejects_invalid_offsets(tmp_path: Path, offsets: list[int]) -> None:
    path = write_manifest(tmp_path, offsets=offsets)
    with pytest.raises(ValueError, match="LVL10_CORPUS_INVALID"):
        load_fixture_manifest(path)
```

- [ ] **Step 3: Write Provider-route RED tests with a scripted SSE factory**

The test factory must capture `payload["input"]`, track active/max-active requests, emit `STARTED`, known PCM deltas and `COMPLETED`, and support blocking/failure/cancellation. Required tests:

```python
async def test_a1_sends_one_full_final_request(...):
    record = await run_attempt(provider, fixture, PopulationRole.A1, identity, monotonic_ns=clock)
    assert factory.inputs == [fixture.final_text]
    assert record.provider_request_count == 1

async def test_b_sends_one_request_per_chunk_and_releases_in_order(...):
    record = await run_attempt(provider, fixture, PopulationRole.B, identity, monotonic_ns=clock)
    assert factory.inputs == list(fixture.chunks)
    assert factory.max_active == 2
    assert record.released_chunk_indexes == tuple(range(len(fixture.chunks)))

async def test_b_cancellation_releases_zero_pcm_after_fence(...):
    record = await cancel_during_successor(provider, fixture, identity)
    assert record.post_fence_sample_count == 0
    assert record.group_completed is False
    assert record.forbidden_effects == ZERO_FORBIDDEN_EFFECTS

async def test_b_provider_failure_discards_unreleased_successor(...):
    record = await fail_second_chunk(provider, fixture, identity)
    assert record.terminal_outcome == "failed"
    assert record.group_completed is False
    assert record.post_fence_sample_count == 0
```

- [ ] **Step 4: Write reducer and CLI RED tests**

Assert A1/A2 drift, 100 ms + 10% B gate, completion regression, request bounds, short parity, stall p95, exclusive output creation, no secret serialization and non-blocking lock rejection.

- [ ] **Step 5: Run and confirm RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py -q
```

Expected: collection/import failure because the runner does not exist.

- [ ] **Step 6: Commit Writer B return**

```bash
git add tests/fixtures/live_voice_lvl10_tts_v1/manifest.json tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py
git commit -m "test(live-voice): specify LVL-10 chunked TTS screen"
```

Return `RESULT LVL10-TESTS-RED` with commit and failing command output.

### Task 3: Hand RED tests to Writer A

**Files:** Existing Writer B commit only.

- [ ] **Step 1: Main verifies Writer B ownership and RED result**

```bash
PLAN_COMMIT=$(git -C /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/live-voice-w3 rev-parse HEAD)
WRITER_B_COMMIT=$(git -C /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-validation rev-parse HEAD)
git show --stat --oneline "$WRITER_B_COMMIT"
git diff --name-only "$PLAN_COMMIT..$WRITER_B_COMMIT"
```

Expected: only Writer B's two owned paths.

- [ ] **Step 2: Main cherry-picks the RED test commit into Writer A's branch**

```bash
git -C /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-provider-screen cherry-pick "$WRITER_B_COMMIT"
```

- [ ] **Step 3: Reconfirm RED in Writer A's worktree**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py -q
```

### Task 4: Implement manifest, chunk group, metrics and reports

**Files:**
- Create: `scripts/live_voice/lvl10_segmented_tts_screen.py`
- Test: `tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py`

**Interfaces:**

```python
class PopulationRole(StrEnum):
    A1 = "LVL-10-A1"
    B = "LVL-10-B"
    A2 = "LVL-10-A2"

@dataclass(frozen=True, slots=True)
class Lvl10Fixture:
    fixture_id: str
    final_text: str
    offsets: tuple[int, ...]
    sha256: str
    @property
    def chunks(self) -> tuple[str, ...]: ...

@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    run_id: str
    role: PopulationRole
    fixture_id: str
    attempt_index: int

async def run_attempt(provider: NativeStreamingSpeechProvider, fixture: Lvl10Fixture, role: PopulationRole, identity: AttemptIdentity, *, monotonic_ns: Callable[[], int] = time.monotonic_ns) -> AttemptRecord: ...
def load_fixture_manifest(path: Path) -> tuple[Lvl10Fixture, ...]: ...
def derive_ordered_release_stall_ns(events: Sequence[ReleaseEvent], *, reserve_samples: int = 12_000, sample_rate_hz: int = 48_000) -> int: ...
def reduce_records(records: Sequence[AttemptRecord]) -> Lvl10Report: ...
```

- [ ] **Step 1: Implement strict manifest loading and immutable result types**

Reject unknown/missing fields, wrong hashes, wrong fixture IDs/order, non-contiguous offsets, >4 chunks, empty slices and text over Provider limits with stable `LVL10_CORPUS_INVALID` errors.

- [ ] **Step 2: Run manifest tests GREEN**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py -q -k manifest
```

- [ ] **Step 3: Implement A1/A2 full-final consumption**

Create an exact `ResponseRef`, activate it in Provider conformance, create one `SynthesisStreamRequest`, drain through `COMPLETED`, count first PCM/reserve/completion and assert zero business effects.

- [ ] **Step 4: Implement B chunk orchestration**

Start chunk 0 and at most one successor, keep successor PCM private until all prior chunks complete, release chunks in exact order, open the next request only when the two-request bound permits, and retain release timestamps/sample counts.

- [ ] **Step 5: Implement one linearized fence**

Cancellation/failure sets `fenced=True` once, cancels all live streams, drains cleanup, clears unreleased PCM and prevents group completion or post-fence release.

- [ ] **Step 6: Implement metrics and decision reducer**

Use `time.monotonic_ns()`, 12,000-sample reserve, exact request/error counts, nearest-rank p95 and the spec §8 validity/PASS/NO_MATERIAL_GAIN/REJECTED/INCONCLUSIVE gates.

- [ ] **Step 7: Implement CLI and exclusive artifacts**

Commands:

```bash
MANIFEST=$(realpath tests/fixtures/live_voice_lvl10_tts_v1/manifest.json)
SOURCE_COMMIT=$(git rev-parse HEAD)
AGENT_CORE_COMMIT=$(git -C /home/renan/openJiuwen-ai/agent-core rev-parse HEAD)
uv run python scripts/live_voice/lvl10_segmented_tts_screen.py validate-corpus --manifest "$MANIFEST"
uv run python scripts/live_voice/lvl10_segmented_tts_screen.py run --manifest "$MANIFEST" --output-root /tmp/lvl10-runner-smoke --run-id lvl10-smoke --source-commit "$SOURCE_COMMIT" --source-state clean --agent-core-commit "$AGENT_CORE_COMMIT" --environment-profile deterministic-test --attempts 1
```

Use `select_environment_streaming_speech(batch_available=False)`, require streaming tier, use `portalocker.Lock(..., timeout=0)`, create output with exclusive semantics and never serialize credentials or text into logs.

- [ ] **Step 8: Run all new tests GREEN**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py -q
```

- [ ] **Step 9: Run affected Provider regressions and static checks**

```bash
uv run pytest tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/live_voice/test_streaming_speech.py -q
uv run ruff check scripts/live_voice/lvl10_segmented_tts_screen.py tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py
```

- [ ] **Step 10: Commit Writer A return**

```bash
git add scripts/live_voice/lvl10_segmented_tts_screen.py
git commit -m "test(live-voice): add LVL-10 Provider materiality runner"
```

Return `RESULT LVL10-RUNNER-GREEN` with commit, tests and diff summary.

### Task 5: Independent reviews and central integration

**Files:** Read-only review artifacts, then Main integration history.

- [ ] **Step 1: Provider reviewer inspects complete Writer A diff**

Check public Provider usage, conformance identities, request concurrency, cleanup, secret handling and whether current SSE A is unchanged. Write `/tmp/lvl10-reviews/provider/review.md` and return `RESULT LVL10-REVIEW-PROVIDER`.

- [ ] **Step 2: Oracle reviewer inspects complete tests and fixture**

Check exact chunk coverage, RED evidence, bounds, order, fence, failure truth, zero forbidden effects, reducer math and provenance. Write `/tmp/lvl10-reviews/oracles/review.md` and return `RESULT LVL10-REVIEW-ORACLES`.

- [ ] **Step 3: Main triages and requests bounded fixes**

Only the owning writer edits its file. Repeat affected tests after each fix.

- [ ] **Step 4: Main integrates worker commits into `latency/hx-optimizations`**

```bash
PLAN_COMMIT=$(git rev-parse HEAD)
WRITER_A_HEAD=$(git -C /home/renan/openJiuwen-ai/jiuwenswarm/.claude/worktrees/lvl10-provider-screen rev-parse HEAD)
git cherry-pick "$PLAN_COMMIT..$WRITER_A_HEAD"
```

- [ ] **Step 5: Run clean integrated verification**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py tests/unit_tests/live_voice/test_openai_streaming_speech.py tests/unit_tests/live_voice/test_streaming_speech.py -q
uv run ruff check scripts/live_voice/lvl10_segmented_tts_screen.py tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py
git diff --check HEAD~2..HEAD
```

### Task 6: Execute real-Provider preflight and A1/B/A2

**Files:** Private artifacts outside Git.

- [ ] **Step 1: Bind clean source and environment labels**

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain --untracked-files=no)"
MANIFEST=$(realpath tests/fixtures/live_voice_lvl10_tts_v1/manifest.json)
RUN_ROOT=/home/renan/openJiuwen-ai/live-voice-latency-runs/lvl10/$SOURCE_COMMIT
RUN_ID=lvl10-provider-$(date -u +%Y%m%dT%H%M%SZ)-${SOURCE_COMMIT:0:9}
```

- [ ] **Step 2: Validate corpus and run connectivity preflight**

Run `validate-corpus`, then the runner's uncredited short A/B/A preflight. Stop on fallback tier, configuration failure, lock collision or secret leakage.

- [ ] **Step 3: Run formal 45-attempt population**

```bash
uv run python scripts/live_voice/lvl10_segmented_tts_screen.py run \
  --manifest "$MANIFEST" \
  --output-root "$RUN_ROOT" \
  --run-id "$RUN_ID" \
  --source-commit "$SOURCE_COMMIT" \
  --source-state clean \
  --agent-core-commit "$(git -C /home/renan/openJiuwen-ai/agent-core rev-parse HEAD)" \
  --environment-profile wsl2-openai-real-provider \
  --attempts 5
```

- [ ] **Step 4: Verify artifacts and decision**

Require 15/15 A1, 15/15 B, 15/15 A2, exact hashes and one terminal decision. Never delete an inconclusive or rejected run.

### Task 7: Record result and close the packet

**Files:**
- Create: `live-voice/evidence/LVL10_AUTHORITATIVE_FINAL_CHUNKED_TTS_RESULT_2026-08-24.md`
- Modify: `live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_UPDATE_2026-08-23.md`
- Modify: `live-voice/STATUS.md`

- [ ] **Step 1: Write sanitized evidence**

Record exact source, commands, denominators, per-stage A1/B/A2 p50/descriptive p95, deltas, request counts, failures, decision, artifact hashes and Browser/product non-claims.

- [ ] **Step 2: Reconcile current authorities**

If PASS, open only a separate product-wiring design packet. Otherwise stop LVL-10 with `NO_MATERIAL_GAIN`, `REJECTED` or `INCONCLUSIVE` and retain LVL-08/LVL-09 as next candidates.

- [ ] **Step 3: Validate and commit documentation**

```bash
git diff --check
git add live-voice/STATUS.md live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md live-voice/evidence/LVL10_AUTHORITATIVE_FINAL_CHUNKED_TTS_RESULT_2026-08-24.md live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_UPDATE_2026-08-23.md
git commit -m "docs(live-voice): record LVL-10 Provider result"
```
