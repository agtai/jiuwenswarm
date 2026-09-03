# Foreground and requirement-continuity functional repair

Date: 2026-09-03. This is bounded follow-up evidence under D-109/D-110 and the
user's minimal-verification instruction. It does not close the complete business
journey, cumulative review, latency or physical acceptance.

## Source and changes

HEAD: `87248911fde2220be6a97f72f8c0210ac67d5b67`, branch
`hx/0812_live_voice_w3`; this run used the inherited working candidate plus the
listed repairs. No commit, history rewrite or remote update was performed.

- The formal foreground Agent treats the committed current request as the only
  current instruction. Historical delegation remains context, including failed
  Tasks; analysis-only turns must not resume their work or write deliverables.
  Selected context retains its original content and identity, with a usage label.
- The same semantic model may identify exact authenticated user-requirement
  sources independently of accepting a narrower offered deliverable. The server
  keeps their chronological original text with the current delegation; unknown,
  assistant, duplicate and inapplicable source claims fail before authority effects.
  Legacy frozen outputs remain readable without adding fields to their replay.
- Recorded-input probes can reproduce read-only Task facts; the authority envelope
  is reconstructed, so this is not a byte-identical authority-envelope replay.
- Test-only repairs admit the coordinated prohibition `或者` while retaining
  contrary-effect rejection, and publish browser command/result JSON atomically.
  The last two fixes were made after the final product build; no product source
  changed after that build.

The final isolated runtime source manifest is in the machine-private Temp run
`live-voice-functional-runtime-20260903-f2/source.json`, SHA-256
`bff76fc942fba3ddc75c884581232a530878d3256c6e093857aa3768b70f8e3d`.
Key product hashes:

| File | SHA-256 |
|---|---|
| `jiuwenswarm/server/runtime/agent_adapter/formal_live_voice.py` | `e56ed2dfdcb014aa6275a1b07090d29e21e4ee35730043c64146f4fbfc7871a8` |
| `jiuwenswarm/server/live_voice/task_semantics.py` | `1f26f14291879eb2c68818a0d8096b8faabf83738c9547ccc6d60c674e6f4a5c` |

## Focused verification

Commands below use the repository `.venv/Scripts/python.exe`; all pytest commands
include `--no-cov -q --disable-warnings --maxfail=1`.

1. Four focused adapter/Registry tests passed (49.63 seconds):
   `test_p2_text_submit_notification_and_exact_presentation_ack`,
   `test_spoken_presentation_is_generic_and_does_not_remove_task_authority`,
   `test_formal_deep_seam_uses_narrow_dispatch_and_non_aborting_detach`, and
   `test_formal_task_result_policy_removes_and_hard_denies_tools`.
2. Eight semantic/Registry tests passed (26.39 seconds), from
   `test_task_semantics.py` and `test_semantic_registry.py`, with
   `-k 'requirement_sources or unowned_requirement_source or frozen_semantics_replay_exact or explicit_local_delegation_creates_once or local_delegation_keeps_referenced'`.
   These check original requirement retention, independent work, invalid sources,
   exact frozen replay, one creation, and zero Core/Agent effects on rejected input.
3. Two test-oracle checks passed (0.42 seconds):
   `test_spoken_coordinated_prohibition_keeps_message_constraint` and
   `test_forbidden_effect_cannot_be_hidden_after_a_valid_prohibition`.
4. Three configured real-model cases passed: `independent-new-objective` (39.922s),
   `same-problem-independent-work` (18.359s), and the recorded failed delegation
   `recorded-refined-delegation` (42.797s). The latter selected the exact original
   user sources and retained all eight flight constraints. Raw report:
   `live-voice-requirement-sources-model-20260903/model-probe-20260903T091107379700.json`.
5. Final isolated Vite build passed in 68 seconds. Ruff passed for the changed
   Python product and test surfaces. No full suite or independent review ran.

The earlier prompt-only recorded replay remains failed: one Provider timeout and
one response omitting the association and meeting constraint. Those records were
not relabelled or overwritten.

## Real audio and Task evidence

Business input was cached WAV audio through the browser MediaStream, real STT,
committed-input admission, configured semantic model, real Agent and project
file tools. Only setup text created the empty conversation. No business transcript
RPC, structured Task button or direct Task command was used by the test driver.

The first foreground repair run (`f1`) produced one successful real Task result,
but its actual spec missed the meeting requirement. Its creation case remains
FAIL. A subsequent analysis-only utterance carried four context references,
including the exact prior delegation; it produced audible analysis without a new
Task/control command or changing the sealed file. That bounded no-reexecution
property passes. The encompassing analysis case remains FAIL because auxiliary
proposal extraction did not settle; the model call ran for approximately 45s.
Proof: `live-voice-foreground-no-reexecution-proof-20260903.json`.

The final product source used a new isolated project `proj_e12303ab`:

- Analysis commit `web-commit-1788427102776-1`: PASS, actual materials read and
  answer played, proposal retained, zero Tasks and no project-file changes.
- Delegation commit `web-commit-1788427338804-2`: one recognized input, one
  `task.create`, no second confirmation utterance; the actual Task spec includes
  the prior source `web-commit-1788427102776-1`, the exact new transcript and all
  eight required constraints. Actual output playback and listening recovery were
  observed (1,717 non-silent rendered buffers in the delegation interval).
- Canonical Task: `task-c4b4df4648c84923a5e342e90c462de6`; Attempt:
  `attempt-27679f98b2e1448b9f50fb81d02b7ffc`. Core reached terminal/completed with
  one sealed result and one real file, SHA-256
  `f066dd57fe2241b23424a5f6b0b06975b6b05e125f10e723636e1ac9e1d48f19`.

The initial final-run harness report remains FAIL: a concurrently written JSON
response was read before completion. The original artifact watcher also failed
because its lexical oracle did not recognize `或者` in the exact user prohibition.
After fixing the test tooling, only the postconditions of the already-created
Task were resumed. No second business audio submission or duplicate Task was
created. The resumed checks retained all constraint, contrary-effect, exact Task,
Core command, playback and sealed-file assertions. The atomic producer change
has not been exercised by a fresh full browser run.

Machine-private raw records under Temp:

- `live-voice-final-functional-audio-20260903.json` (original, unchanged);
- `live-voice-final-functional-audio-postconditions-20260903.json` (same-input
  resumed postconditions, PASS);
- `live-voice-final-functional-task-result-20260903.json` (execution/integrity PASS);
- `live-voice-final-functional-browser-20260903/events.jsonl` (actual PCM render);
- `live-voice-functional-runtime-20260903-f2/` (source, build, logs, database and
  isolated project).

## Important acceptance limits

The software path reaches a real Task and file; the business artifact is not
accepted. Its actual filename is `《出行方案.md》`, including the book-title marks.
It preserves the meeting, budget, separate refund, hotel and no-external-action
requirements in text, but recommends F03 as feasible while its buffered hotel
arrival is 02:05 against a 02:00 retention cutoff, dependent on an unverified
hotel exception. Presence of the words is not proof that the plan satisfies them.
Neither the filename nor this feasibility judgement was repaired by editing the
sealed result or its file.

The complete A/B/A2, adjustment/cancel, offline/ACK/refresh journey, non-travel
execution, Native business audio, cumulative hardcode/review and final human
microphone/speaker acceptance remain unproved on this candidate. Latency work
remains deferred. Scoped production repairs and execution/integrity PASS must
not be reported as all business results correct or only physical acceptance left.

At handoff the owned headless browser was closed through Exit and browser cleanup.
The final isolated runtime remains available for operator verification; the
previous `f1` runtime was fully stopped. Source configuration hashes are unchanged,
and every product-file hash still matches the final build manifest. These checks
are recorded in `live-voice-functional-followup-disposition-20260903.json`.
