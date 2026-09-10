# Native business instruction integration — 2026-09-10

Source baseline: `87eba08a130b50ac138e4cf8bd6bc9a7eda58006`. The containing commit
owns this Tier 1 prompt change under [D-125](../decisions/DECISIONS.md#d-125-unify-native-business-instructions-for-prompt-feedback-and-complete-execution).
This is an offline implementation review, not a real Provider or user acceptance.

## Scope and review

The supplied `session-instructions-candidate.txt` and all seven text blocks in
`instructions-final-candidate.md` were treated as candidate product content.
The session matches exactly except its final newline. Four response variants
prepend the supplied shared rules; two correction suffixes append to the effective
base. The Markdown's separately referenced tool-description JSON was not supplied;
the existing 13 descriptions were revised against the user's ten rules and actual
schemas. References render with the actual bound or legacy catalog names.

The complete scoped diff was reviewed: a new instruction module, Engine imports
and three receipt-variant selections, tool wording/name substitution, affected
assertions and nine new contract/seam cases. No unresolved finding was introduced
in this wording boundary. The review retained these limits:

- A short preamble does not truncate the executable request. Existing admission
  can emit the complete Task call while its preamble has neither finished
  generation nor obtained presentation ACK.
- Receipt-only responses still exist. The new wording allows omission of redundant
  waiting speech, and silent terminal delivery settles without claiming heard
  audio. This does not deterministically suppress creation of redundant responses.
- Existing input, generation, playback, turn, freshness and notification identity
  checks remain. No new semantic classifier or cross-response merge/delivery
  protocol was added. Avoiding a second notification after a follow-up uses the
  same result remains an unaccepted model/runtime behavior.
- Full schemas, parsing, context binding, correction limits and tool restrictions
  are unchanged. Models/VAD, transport, private deployment, non-business delegate
  instructions and the deferred M01–M17 observations are outside this change.

Tested production Git blob IDs:

| Source under `jiuwenswarm/server/live_voice/` | Blob |
|---|---|
| `native_business_instructions.py` | `4fb706696cd4cc6730df11d4bbbd171450e34fc5` |
| `native_business_tools.py` | `065c62755772847ef5bffd615ec12f78b11660d9` |
| `openai_realtime_native_engine.py` | `c0e6d1050fb8aeedcefb118169694cc7aeec42cc` |

## Verification

Executed with the existing workspace `.venv`, without provider calls or service
restarts:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -o addopts='' -o log_cli=false -q tests/unit_tests/live_voice/test_native_business_instructions.py tests/unit_tests/live_voice/test_openai_realtime_native_engine.py tests/unit_tests/live_voice/test_native_acceptance_fast_path.py tests/unit_tests/live_voice/test_native_business_tools.py tests/unit_tests/live_voice/test_native_bound_business_tools.py tests/unit_tests/live_voice/test_native_named_tools_engine.py tests/unit_tests/live_voice/test_native_continuation_preparation.py tests/unit_tests/live_voice/test_native_notification_wake.py
```

Result: **540 passed, 5 failed**. New prompt composition/catalog cases and both
runtime seams passed. Existing checks cover local argument rejection/recovery,
forbidden receipt-only mutations, stale feedback, interruption and notification
arbitration. The five failures all belong to `test_native_acceptance_fast_path.py`:

- `test_acceptance_speech_does_not_wait_and_dependent_steps_require_fresh_context`:
  four `fresh_context` cases with projection off, status/adjust and both tool
  naming modes. The old assertion expects no refresh; a refresh occurs.
- `test_work_feature_off_retains_actual_router_context_without_restricted_tools`:
  the fixture forbids refresh because its receipt already carries context;
  the existing refresh path instead causes an engine operational-state failure.

All five were reproduced using the baseline Engine and tool modules loaded from
`git show 87eba08a:<path>` into an isolated Python process and the original baseline
fast-path test file in a temporary directory. The other production code is
unchanged. The original node IDs were selected with `pytest.main`, `-c pytest.ini`,
`-o addopts=`, `-o log_cli=false`, `--show-capture=no`, `--tb=short` and `-q`.
Result: **the same 5 failed**. The refresh-due predicate in `_send_response_request`
does not depend on projection being enabled. No assertions were weakened or
failures hidden. The projection-off compatibility gap remains for later triage;
the prompt change receives no full-green claim.

```powershell
.\.venv\Scripts\python.exe -X utf8 -m pytest -o addopts='' -o log_cli=false --show-capture=no --tb=short -q tests/unit_tests/gateway/test_dedicated_media_registration.py::test_silent_terminal_ack_waits_for_runtime_while_provider_control_remains_live tests/unit_tests/gateway/test_native_notification_wake_gateway.py
```

Result: **5 passed**. Gateway waits for accepted terminal admission before delivery
settlement, fences rejection, keeps Provider control live, and does not fabricate
heard ACK or delegate results; notification wake checks also pass.

Additional executed audits passed: all supplied text-block compositions match;
both 13-tool catalogs equal the baseline recursively after removing only
`description` fields; the entire Engine class AST equals the baseline after
normalizing only `instructions` assignment values. Scoped diff/Markdown-link
checks complete the repository review.

## Remaining acceptance

The user performs real conversation tests. Separately measure acknowledgment first
sound, real tool dispatch and substantive-result first sound, plus completeness,
status truth, explicit long recaps, and delayed-result overlap with a new question.
In particular, check repeated waiting speech and repeat notifications after a
follow-up. The new text's size/structure and an earlier “好的” do not prove a faster
substantive answer. No deployment, new voice session or repair of the reproduced
projection-off failures was performed.
