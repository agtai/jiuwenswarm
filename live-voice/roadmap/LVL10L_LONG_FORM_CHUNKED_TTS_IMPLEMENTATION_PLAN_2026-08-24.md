# LVL-10L Long-Form Chunked TTS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute a no-Browser real-Provider screen that determines whether two or four ordered TTS chunks materially reduce 2,150-character authoritative-final synthesis completion and locates the smallest demonstrated break-even bucket.

**Architecture:** Add an independent LVL-10L runner, corpus schema and test module; do not modify the completed LVL-10 runner or product source. Revision 2 retains the v1 pilot corpus as history, adds a nested 600/1200/2100 v2 corpus and uses four role-owned Provider adapters for five interleaved A1/B2/B4/A2 rounds. The reducer uses time-interpolated bracket controls, completion-primary gates and exact integrity/request accounting.

**Tech Stack:** Python 3.11, asyncio, `NativeStreamingSpeechProvider`, `OpenAIStreamingSpeechProvider`, pytest, portalocker, JSON/JSONL, SHA-256.

**Spec:** `live-voice/roadmap/LVL10L_LONG_FORM_CHUNKED_TTS_COMPLETION_SPEC_2026-08-24.md`

## Global Constraints

- Do not modify `scripts/live_voice/lvl10_segmented_tts_screen.py`, its v1 fixture, tests, reducer, artifacts or historical result.
- Do not modify product Runtime, Gateway, P1/P2/P3, Provider implementation, Browser or UI source.
- Every attempt starts after a complete immutable authoritative final exists.
- A1/A2 use one request; B2 uses two; B4 uses four; max active requests are two; retries are zero.
- Use mono signed 16-bit PCM at 48,000 Hz and a 12,000-sample / 250 ms source reserve.
- First PCM means chunk-0 PCM. Earliest successor PCM is diagnostic only.
- Use the shared `/tmp/jiuwenswarm-lvl10-provider.lock` and create no Provider preflight calls.
- Pilot is exactly 12 attempts / 24 Provider requests; formal is exactly 60 attempts / 120 requests.
- Raw output goes under `/home/renan/openJiuwen-ai/live-voice-latency-runs/lvl10l/$SOURCE_COMMIT/$RUN_ID/`.
- Main is the only writer in the integration worktree and the only history integrator. Review agents remain read-only. No worker pushes.

## File map

| File | Responsibility |
|---|---|
| `tests/fixtures/live_voice_lvl10l_tts_v1/manifest.json` | Immutable revision-1 pilot corpus; never edit |
| `tests/fixtures/live_voice_lvl10l_tts_v2/manifest.json` | Frozen nested 600/1200/2100 corpus, unit hashes and exact B2/B4 offsets |
| `scripts/live_voice/lvl10l_long_form_tts_screen.py` | Corpus validation, role scheduling, Provider orchestration, measurements, reduction and artifacts |
| `tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py` | Tier-2 deterministic contract, failure, ordering, reducer and CLI coverage |
| `live-voice/evidence/LVL10L_LONG_FORM_CHUNKED_TTS_RESULT_2026-08-24.md` | Sanitized immutable result and artifact hashes |
| `live-voice/STATUS.md` | Mutable packet/capability disposition after the result |
| `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md` | Candidate status and measured headroom |
| `live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md` | Experiment route and artifact ledger |

---

### Task 1: Freeze and validate the nested corpus

**Files:**
- Create: `tests/fixtures/live_voice_lvl10l_tts_v2/manifest.json`
- Create: `tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py`
- Create: `scripts/live_voice/lvl10l_long_form_tts_screen.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class Lvl10lFixture:
    fixture_id: str
    final_text: str
    unit_offsets: tuple[int, ...]
    b2_offsets: tuple[int, ...]
    b4_offsets: tuple[int, ...]
    sha256: str

    def chunks_for(self, role: PopulationRole) -> tuple[str, ...]: ...

def load_fixture_manifest(path: Path) -> tuple[Lvl10lFixture, ...]: ...
```

- [ ] **Step 1: Write the RED manifest tests**

```python
def test_manifest_is_nested_and_preserves_exact_b2_b4_coverage(manifest_path: Path) -> None:
    fixtures = load_fixture_manifest(manifest_path)
    assert [row.fixture_id for row in fixtures] == ["long_600", "long_1200", "long_2100"]
    assert [len(row.chunks_for(PopulationRole.B2)) for row in fixtures] == [2, 2, 2]
    assert [len(row.chunks_for(PopulationRole.B4)) for row in fixtures] == [4, 4, 4]
    assert fixtures[1].final_text.startswith(fixtures[0].final_text)
    assert fixtures[2].final_text.startswith(fixtures[1].final_text)
    assert all("".join(row.chunks_for(PopulationRole.B4)) == row.final_text for row in fixtures)

@pytest.mark.parametrize("mutation", ["hash", "overlap", "gap", "inside_unit", "not_nested", "unknown_field"])
def test_manifest_rejects_every_frozen_contract_violation(tmp_path: Path, mutation: str) -> None:
    path = write_mutated_manifest(tmp_path, mutation)
    with pytest.raises(ValueError, match="LVL10L_CORPUS_INVALID"):
        load_fixture_manifest(path)
```

- [ ] **Step 2: Run the tests and confirm RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py -q -k manifest
```

Expected: import/collection failure because the LVL-10L runner does not exist.

- [ ] **Step 3: Commit the exact corpus**

Reuse exactly the first 12 units of the immutable v1 explanatory topic.
Concatenate units 1–4, 1–8 and 1–12 for the three nested fixtures. Record exact unit hashes,
text hashes, character/byte counts and equal contiguous B2/B4 unit boundaries.
Generate hashes once, paste them into the manifest, then treat the file as
immutable before any Provider call.

- [ ] **Step 4: Implement strict manifest loading**

Accept only schema `live-voice.lvl10l-corpus.v2` and exact fields. Reject wrong
fixture IDs/order, sizes outside 550–750 / 1100–1500 / 2000–2250 characters,
wrong hashes, broken nesting, boundaries inside units, empty ranges, gaps,
overlap or extra fields with stable `LVL10L_CORPUS_INVALID:<reason>` errors.
The largest fixture contains exactly 2,150 characters and remains within the
spec's 2,000–2,250 bound. The v1 manifest remains byte-identical.

- [ ] **Step 5: Run GREEN and commit**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py -q -k manifest
git add tests/fixtures/live_voice_lvl10l_tts_v2/manifest.json tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py scripts/live_voice/lvl10l_long_form_tts_screen.py
git commit -m "test(live-voice): freeze LVL-10L long-form corpus"
```

### Task 2: Implement exact role identities and ordered chunk orchestration

**Files:**
- Modify: `scripts/live_voice/lvl10l_long_form_tts_screen.py`
- Modify: `tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py`

**Interfaces:**

```python
class PopulationRole(StrEnum):
    A1 = "LVL-10L-A1"
    B2 = "LVL-10L-B2"
    B4 = "LVL-10L-B4"
    A2 = "LVL-10L-A2"

@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    run_id: str
    role: PopulationRole
    fixture_id: str
    round_index: int

@dataclass(frozen=True, slots=True)
class ChunkTimeline:
    chunk_index: int
    opened_ns: int
    first_pcm_ns: int | None
    completed_ns: int | None
    released_ns: int | None
    sample_count: int
    terminal_outcome: str

async def run_attempt(provider: NativeStreamingSpeechProvider, fixture: Lvl10lFixture, identity: AttemptIdentity, *, monotonic_ns: Callable[[], int] = time.monotonic_ns) -> AttemptRecord: ...
```

- [ ] **Step 1: Write RED orchestration tests**

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "expected"), [(PopulationRole.A1, 1), (PopulationRole.B2, 2), (PopulationRole.B4, 4), (PopulationRole.A2, 1)])
async def test_roles_open_exact_requests_and_cover_text(role: PopulationRole, expected: int) -> None:
    record, factory, fixture = await scripted_attempt(role)
    assert record.provider_request_count == expected
    assert "".join(factory.inputs) == fixture.final_text
    assert factory.max_active <= 2
    assert record.released_chunk_indexes == tuple(range(expected))

@pytest.mark.asyncio
async def test_first_pcm_credits_chunk_zero_not_early_successor() -> None:
    record, _ = await scripted_attempt(PopulationRole.B2, successor_pcm_first=True)
    assert record.request_to_any_chunk_pcm_ns < record.request_to_first_pcm_ns
    assert record.chunk_timelines[0].first_pcm_ns - record.started_ns == record.request_to_first_pcm_ns

@pytest.mark.asyncio
async def test_rotated_fixture_order_never_creates_stale_generation() -> None:
    provider = scripted_provider()
    for fixture in (fixture_2100, fixture_600, fixture_1200):
        assert (await run_attempt(provider, fixture, identity(fixture, round_index=3))).group_completed
```

- [ ] **Step 2: Confirm RED**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py -q -k "roles or first_pcm or rotated"
```

- [ ] **Step 3: Implement identities and request construction**

Use interaction `lvl10l-{run_id}-{role}-{fixture_id}`, generation
`round_index`, and response/stream/unit IDs containing role, fixture, round and
chunk. Activate each exact response before opening synthesis.

- [ ] **Step 4: Implement B2/B4 concurrency and ordered release**

Open chunk 0 and one successor, never exceed two active requests, replenish B4
only after the ordered frontier advances, buffer successor output and expose
released indexes only in original order. Record per-chunk open/first/complete/
release times and sample counts.

- [ ] **Step 5: Implement one fail-closed group fence**

```python
async def fence_group(reason: str) -> None:
    # Idempotently mark the group fenced, cancel every live synthesis stream,
    # await cleanup, discard unreleased PCM and prohibit false completion.
```

Test Provider open failure, mid-stream failure, timeout, caller cancellation,
late successor completion and repeated fence. Each must have zero post-fence
samples and `ZERO_FORBIDDEN_EFFECTS`.

- [ ] **Step 6: Run GREEN and affected conformance regressions**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py -q -k "attempt or role or first_pcm or failure or cancel or fence or identity"
uv run pytest tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py -q
```

- [ ] **Step 7: Commit**

```bash
git add scripts/live_voice/lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py
git commit -m "test(live-voice): add LVL-10L ordered synthesis runner"
```

### Task 3: Implement interleaving, paired reduction and immutable artifacts

**Files:**
- Modify: `scripts/live_voice/lvl10l_long_form_tts_screen.py`
- Modify: `tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py`

**Interfaces:**

```python
def scheduled_cells(round_index: int) -> tuple[tuple[PopulationRole, str], ...]: ...
def interpolate_reference(candidate: AttemptRecord, a1: AttemptRecord, a2: AttemptRecord, metric: str) -> float: ...
def reduce_records(records: Sequence[AttemptRecord], *, expected_rounds: int) -> Lvl10lReport: ...
async def run_population(args: argparse.Namespace, fixtures: tuple[Lvl10lFixture, ...]) -> Lvl10lReport: ...
```

- [ ] **Step 1: Write RED schedule and interpolation tests**

```python
def test_schedule_rotates_fixtures_and_alternates_candidates() -> None:
    assert roles_for(scheduled_cells(0), "long_600") == [A1, B2, B4, A2]
    assert roles_for(scheduled_cells(1), "long_1200") == [A1, B4, B2, A2]
    assert fixture_order(scheduled_cells(2)) == ["long_2100", "long_600", "long_1200"]

def test_reference_is_interpolated_at_candidate_start() -> None:
    assert interpolate_reference(candidate_at_25, a1_at_0_value_1000, a2_at_100_value_2000, "request_to_complete_ns") == 1250
```

- [ ] **Step 2: Write RED reducer tests for every terminal result**

Construct complete five-round records and assert:

- `B2_MATERIAL` only when 2100 paired p50 gain is ≥750 ms and ≥15%, 4/5
  rounds win, completion beats both A1/A2 p50, first/reserve remain within
  200 ms and 10%, and duration/sample parity is ±10%;
- B4 is preferred only with an additional ≥750 ms and ≥10% over B2;
- 1200/600 only lower the break-even after 2100 passes monotonically;
- wrong counts, errors, order, effects or duration parity produce `REJECTED`;
- missing rows or control drift produce `INCONCLUSIVE`;
- valid insufficient gain produces `NO_MATERIAL_GAIN`;
- whole-chunk availability is reported but never changes the decision.

- [ ] **Step 3: Implement the fixed five-round scheduler**

Create four adapters before attempts and close all four in `finally`. Execute
the exact rotated/interleaved schedule. Verify each adapter has 15 response
identities at formal completion and record exact role request totals
`15/30/60/15`.

- [ ] **Step 4: Implement reducer math and ordered reasons**

Use `statistics.median`, nearest-rank p90/p95 and linearly interpolated paired
references. Apply gates in this order: provenance/denominators → integrity/
reliability → control drift → 2100 materiality → B4 amplification → monotonic
break-even. Serialize an ordered `gate_reasons` list even on PASS.

- [ ] **Step 5: Implement CLI and immutable artifacts**

Commands are `validate-corpus` and `run`. `run --rounds 1` is the pilot and
`run --rounds 5` is formal. Reject every other round count, existing output
directories, fallback Provider tier and lock collision. Write `run.json`,
copied `manifest.json`, `attempts.jsonl`, `report.json` and `report.md`; hide
credentials and final-text payloads from logs/reports. Bind canonical hashes.

- [ ] **Step 6: Run GREEN, Ruff and artifact tests**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py -q
uv run ruff check scripts/live_voice/lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py
git diff --check
```

- [ ] **Step 7: Commit**

```bash
git add scripts/live_voice/lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py
git commit -m "test(live-voice): reduce LVL-10L bracketed populations"
```

### Task 4: Close Tier-2 review and integrated verification

**Files:** Read-only review artifact under `/tmp/lvl10l-reviews/`; no repository review file until result documentation.

- [ ] **Step 1: Run a cold independent complete-diff review**

Reviewer checks exact spec coverage, Provider API use, identity cap, four-
adapter lifecycle, chunk-0 first PCM, request counts, interleaving, interpolation,
duration parity, fence/cancel, zero forbidden effects, secret handling and
historical LVL-10 non-modification. Write `/tmp/lvl10l-reviews/tier2.md` with
Critical/Important/Minor findings.

- [ ] **Step 2: Fix Critical/Important findings with RED/GREEN evidence**

Only Main edits integration files. Re-run the exact affected tests after every
fix; do not defer any Critical/Important finding into the Provider run.

- [ ] **Step 3: Run cumulative affected verification**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py -q
uv run ruff check scripts/live_voice/lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py
git diff --check
```

- [ ] **Step 4: Commit review fixes if any**

```bash
git add scripts/live_voice/lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py
git commit -m "fix(live-voice): close LVL-10L Tier-2 review"
```

### Task 5: Execute the real-Provider pilot

**Files:** Private immutable artifacts outside Git.

- [ ] **Step 1: Bind a clean source and exact environment**

```bash
SOURCE_COMMIT=$(git rev-parse HEAD)
test -z "$(git status --porcelain --untracked-files=no)"
AGENT_CORE_COMMIT=$(uv run python - <<'PY'
import json
from pathlib import Path
p = next(Path('.venv/lib/python3.11/site-packages').glob('openjiuwen-*.dist-info/direct_url.json'))
print(json.loads(p.read_text())['vcs_info']['commit_id'])
PY
)
MANIFEST=$(realpath tests/fixtures/live_voice_lvl10l_tts_v2/manifest.json)
RUN_ROOT=/home/renan/openJiuwen-ai/live-voice-latency-runs/lvl10l/$SOURCE_COMMIT
RUN_ID=lvl10l-provider-pilot-$(date -u +%Y%m%dT%H%M%SZ)-${SOURCE_COMMIT:0:9}
```

- [ ] **Step 2: Validate corpus without a Provider call**

```bash
uv run python scripts/live_voice/lvl10l_long_form_tts_screen.py validate-corpus --manifest "$MANIFEST"
```

- [ ] **Step 3: Execute exactly one round**

```bash
uv run python scripts/live_voice/lvl10l_long_form_tts_screen.py run \
  --manifest "$MANIFEST" \
  --output-root "$RUN_ROOT/$RUN_ID" \
  --run-id "$RUN_ID" \
  --source-commit "$SOURCE_COMMIT" \
  --source-state clean \
  --agent-core-commit "$AGENT_CORE_COMMIT" \
  --environment-profile wsl2-openai-real-provider \
  --rounds 1
```

- [ ] **Step 4: Apply the frozen pilot gate**

Require 12/12 complete attempts, exactly 24 requests, zero errors, exact
integrity and at least one candidate faster than both controls for 1200 and
2100. Apply pilot first/reserve non-regression only to those two governing
long-form fixtures; 600 remains an overhead diagnostic. Retain a failed/
inconclusive pilot under its run ID; never overwrite it.

### Task 6: Execute formal population and document the result

**Files:**
- Private formal artifacts outside Git.
- Create: `live-voice/evidence/LVL10L_LONG_FORM_CHUNKED_TTS_RESULT_2026-08-24.md`
- Modify: `live-voice/STATUS.md`
- Modify: `live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md`
- Modify: `live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md`

- [ ] **Step 1: Run formal only after pilot PASS**

Repeat Task 5 with a new `RUN_ID` beginning `lvl10l-provider-formal-` and
`--rounds 5`. Require 60 retained attempts and exact request totals:
A1=15, B2=30, B4=60, A2=15, total=120. Require 4/5 positive paired gains
and 4/5 stable A1/A2 brackets; p90/p95 remain descriptive only.

- [ ] **Step 2: Independently verify artifact counts, hashes and reducer math**

Recompute SHA-256 for all artifacts; recompute denominators, p50, paired gains,
win counts, duration parity and drift from `attempts.jsonl` without calling the
runner reducer. Differences are `INCONCLUSIVE` and stop product follow-up.

- [ ] **Step 3: Write the sanitized result**

Record exact source/Agent-Core commits, environment boundary, corpus hash,
pilot/formal IDs, every p50 and paired delta, request/error counts, control
drift, smallest monotonic break-even, decision reasons, artifact hashes,
measured/derived labels and all Browser/product exclusions.

- [ ] **Step 4: Synchronize mutable documentation**

STATUS says either material / no gain / rejected / inconclusive without
claiming Browser or product credit. Inventory and catalog preserve LVL-10 as
inconclusive, add LVL-10L as a separate row/section and route the next action
from the actual result.

- [ ] **Step 5: Verify documentation and commit**

```bash
git diff --check
for link in \
  live-voice/roadmap/LVL10L_LONG_FORM_CHUNKED_TTS_COMPLETION_SPEC_2026-08-24.md \
  live-voice/evidence/LVL10L_LONG_FORM_CHUNKED_TTS_RESULT_2026-08-24.md; do
  test -f "$link"
done
git add live-voice/evidence/LVL10L_LONG_FORM_CHUNKED_TTS_RESULT_2026-08-24.md live-voice/STATUS.md live-voice/roadmap/LATENCY_OPTIMIZATION_INVENTORY_2026-08-21.md live-voice/evidence/LATENCY_EXPERIMENT_CATALOG_2026-08-22.md
git commit -m "docs(live-voice): record LVL-10L Provider result"
```

### Task 7: Final verification and handoff

**Files:** No new files unless a verified correction is required.

- [ ] **Step 1: Run the full affected test set and static checks again**

```bash
uv run pytest tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10_segmented_tts_screen.py tests/unit_tests/live_voice/test_streaming_speech.py tests/unit_tests/live_voice/test_openai_streaming_speech.py -q
uv run ruff check scripts/live_voice/lvl10l_long_form_tts_screen.py tests/unit_tests/live_voice/test_lvl10l_long_form_tts_screen.py
git diff --check
git status --short --branch
```

- [ ] **Step 2: Report exact closure**

Report commits/messages, source and Agent-Core hashes, test counts, Provider
attempt/request/error totals, measured timing tables, terminal decision,
independent review disposition, preserved untracked user files and explicit
non-claims. Do not push without separate exact remote/ref approval.
