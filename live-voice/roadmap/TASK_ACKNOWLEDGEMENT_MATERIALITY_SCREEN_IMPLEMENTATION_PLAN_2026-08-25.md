# Task acknowledgement materiality screen implementation plan

Date: 2026-08-25

Branch: `latency/task-ack-latency-experiment`

## Recorded boundary

Implement only a strict offline reader of the canonical latency report. Do not
modify Task, PresentationUnit, TTS, ACK, Browser or product configuration.

## Task 1 — RED contract tests

Files:

- Create `tests/unit_tests/live_voice/test_task_ack_materiality_screen.py`.

Cover a complete eligible report plus invalid schema, missing Task profile,
missing segment, insufficient samples, nonzero failed/cancelled/fallback/
underrun/rebuffer counts and sub-threshold headroom. Assert deterministic
closed statuses and no input/output overwrite.

## Task 2 — Minimal screen implementation

Files:

- Create `scripts/live_voice/task_ack_materiality_screen.py`.

Reuse the strict canonical report loader from `latency_probe_report`. Accept:

```text
--report <canonical-report.json>
--output <new-screen.json>
--minimum-successful-samples 5
--minimum-p50-opportunity-ms 500
```

Create output exclusively with mode 600. Serialize no prompt, transcript,
credentials, raw marks or private paths.

## Task 3 — Verification and operational command

Run:

```bash
uv run pytest tests/unit_tests/live_voice/test_task_ack_materiality_screen.py -q --no-cov
uv run ruff check scripts/live_voice/task_ack_materiality_screen.py tests/unit_tests/live_voice/test_task_ack_materiality_screen.py
uv run python -m py_compile scripts/live_voice/task_ack_materiality_screen.py
git diff --check
```

After the repaired manual driver produces a valid Task population:

```bash
uv run python scripts/live_voice/task_ack_materiality_screen.py \
  --report /home/renan/openJiuwen-ai/live-voice-latency-runs/<run-id>/report.json \
  --output /home/renan/openJiuwen-ai/live-voice-latency-runs/task-ack/<run-id>/materiality.json
```

Do not use the cancelled 2026-08-24 Task batches for eligibility. Preserve any
screen output immutably; a rerun requires a fresh output path.

## Task 4 — Review and next gate

Perform scoped diff review and link checks. If and only if the screen is
eligible, create a new Tier-3 candidate spec that freezes the exact early-unit
content source, feature-off route, final-unit ACK independence, cancellation,
duplicate/stale fencing and deployed Browser validation.
