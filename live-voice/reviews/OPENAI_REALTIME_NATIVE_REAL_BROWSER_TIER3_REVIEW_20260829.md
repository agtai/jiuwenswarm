# OpenAI Realtime Native real-browser Tier-3 review — 2026-08-29

> Status: **PASS — `C0/I0/M0` after one bounded independent finding and
> repair.** This closes the source/automation/ordinary-Chrome prerecorded
> foreground boundary for scope marker `306894062`. It does not grant a
> physical microphone/headset, human-acoustic, background Task, W3,
> Production, deployment or remote-ref claim.

## 1. Authority and reviewed boundary

- Branch: `codex/openai-realtime-native-interaction-engine`.
- Review baseline: `55d8a4fbb2b8d8eb763fa391d5bd93bbfa2162fe`.
- Reviewed repair commit:
  `268c806340f8a64418fdf2ab8946d7f73a681014`.
- Risk: Tier 3 across Native Runtime presentation truth, Gateway dedicated
  media and Provider truncate ownership.
- Intended scope: replace only foreground Cascade STT/EOT/TTS/barge-in with
  one OpenAI Realtime Native session using `gpt-realtime-2.1-mini`.
- Excluded: Agent/Tool/Task authority changes, background/W3 work, public wire
  expansion, fallback-policy changes, physical acceptance and remote updates.

## 2. Independent finding and repair

The independent complete-diff review initially returned `C0/I1/M0`.
Runtime correctly retained response-global PresentationUnit source spans, but
Gateway reused the response-global `source_end_utf8` as OpenAI's
`conversation.item.truncate.audio_end_ms`. A later Provider item could
therefore present 20 ms locally while being truncated at 40 ms, and a
zero-padded final frame could overstate actual Provider duration. OpenAI
rejects truncate positions beyond the audio item's actual duration.

The repair preserves response-global Runtime/PresentationLedger spans and
derives a separate Provider item-local cursor in the downlink source. Engine
output and the existing Native audio observation now carry the actual Provider
sample count; zero padding remains only a transport-frame detail. Gateway
validates Runtime span length against those actual samples and constructs STOP
from the per-media-sequence item-local end. No method, wire key, public schema,
media-frame shape, Agent, Tool, Task or W3 boundary changed.

The same reviewer then performed one fix-only read-only re-review of
`55d8a4fb..268c8063` and returned `C0/I0/M0 — PASS`. It specifically confirmed
the response-global Runtime/item-local Gateway layering, later and interleaved
item barge-in, partial-frame padding semantics and unchanged exclusions. No
additional review loop was opened.

## 3. Red/green and cumulative automation

The seven focused regression cases first failed on the pre-fix tree, with the
first failure showing the missing actual Provider sample count. An attempted
item-local Runtime span implementation also failed the PresentationLedger's
required response-global continuity, which established the final two-layer
design.

| Gate | Result |
| --- | ---: |
| Focused cursor/sample regression set | 7/7 passed |
| Affected Native group | 217/217 passed |
| Exact eight-file backend cumulative group | 470/470 passed |
| Ruff on exact changed Python files | passed |
| Gateway/server Live Voice compile check | passed |
| Mypy on six Native files with skipped imports | 0 issues |
| `git diff --check` | passed |

The backend cumulative group covered Web Symphony status, dedicated media,
Runtime client/downlink, Agent conversation Runtime, Native Runtime/Engine and
product composition. It completed in 133.29 seconds. Existing SQLite
ResourceWarnings were emitted, but the suite exited successfully with no test
failure.

No frontend source changed in this repair. The exact parent candidate already
passed the unchanged frontend Native suite `106/106`, integrated Web suite
`494/494`, Browser Gateway Media `40/40`, Browser Dedicated Media `30/30` and
`build:live-voice` with 4,650 modules transformed.

## 4. Real Browser result

Ordinary installed Chrome, the isolated registered Code-project session and a
fixed prerecorded capture corpus ran the exact repair commit. Warm-up,
first-audio `20/20` and barge-in `20/20` completed with zero Browser drops.
Browser EOT-to-WebAudio-start latency was p50/p95
`2468.167/3057.833 ms`, reductions of `48.95%/45.43%` from the accepted
Cascade warm baseline.

One uncredited successor response exceeded the intentional 4,096-record
active-response audio ledger, failed closed as `NATIVE_AUDIO_LEDGER_FULL`, and
caused one zero-record `browser_timeout`. Activation generation 3 recovered
without a Task or background side effect, and the coordinator then completed
all 40 eligible scenarios. The exact facts and non-claims are recorded in the
[post-review Chrome evidence](../evidence/OPENAI_REALTIME_NATIVE_POST_REVIEW_ORDINARY_CHROME_EVIDENCE_20260829.md).

## 5. Verdict

The reviewed foreground replacement boundary is correct and independently
review-clean at `C0/I0/M0`. The real Browser run proves integration through
the actual product path and also proves bounded recovery from one overlong
Provider response; it is not presented as a zero-anomaly run. Further capacity
or response-length policy would be a new product packet, not a defect fix
silently added here. Physical microphone/headset and human acoustic acceptance
remain the only foreground acceptance class not run in this packet.

