# Functional repair minimal checkpoint — 2026-09-03

This is a progress snapshot, not module, candidate or human acceptance.
The user deferred 58/69-second performance work and broad/full testing.
Current mutable scope and next action remain in [STATUS](../STATUS.md).

## Source and implemented boundaries

Base HEAD: `87248911fde2220be6a97f72f8c0210ac67d5b67`, branch
`hx/0812_live_voice_w3`, with the inherited working candidate preserved.
No staging, commit or remote update was performed at this checkpoint.
Private source manifests are `live-voice-semantic-handoff-20260903-0707/
source-and-handoff.json`, `live-voice-functional-runtime-20260903-f1/source.json`
and `live-voice-functional-closeout-20260903/candidate-source.json` under the
machine's temporary directory. Seven changed production files were rehashed
against the running f1 manifest and matched.

- D-109 local-artifact delegation retains the current committed input, exact
  semantic/context binding and existing file-only Direct capability. It consumes
  the existing durable confirmation claim and reaches the normal final authority
  reread/Core path without another spoken confirmation.
- Server pending kind/id/version constrain continuation stage and immutable
  confirmation arguments. Local delegation retains the exact associated prior
  user requirements plus the current utterance in its executable instruction.
- Generation interruption verifies the current capture/session/interaction;
  empty/failed replacement recognition after an authoritative fence has explicit
  feedback. A delayed fence cannot falsely claim cancellation early or publish
  into another Session. These changes do not establish whether the earlier
  physical trigger was real speech or noise.

## Focused checks

Using `.venv/Scripts/python.exe`:

```text
-m pytest tests/unit_tests/live_voice/test_task_semantics.py tests/unit_tests/live_voice/test_semantic_registry.py -q -k "pending_confirmation_schema or local_delegation or analysis_cannot_claim or model_create_and_natural_confirmation or controlled_semantic_negative" --disable-warnings --maxfail=2
```

Final result: 14 passed, 110 deselected. The first run had two test-fixture
attribute errors (`formal_calls` versus `get_calls`), corrected before that pass.
This is not the complete Registry suite. The default coverage made this command
slower than necessary; subsequent focused checks should use `--no-cov`.

Frontend mounted tests selected `retains feedback after|ignores the cancelled
predecessor|in-flight interruption from a retired Session`: four passed. The two
failure-feedback cases were rerun after strengthening the delayed-fence race,
and both passed; they are the same two cases, not additional coverage. The initial
empty-transcript test double was corrected to use the actual failure envelope.
TypeScript `tsc --noEmit`, the isolated Vite build, affected Python Ruff and
`git diff --check` passed. Existing duplicate-i18n/chunk-size warnings remain.
Logs use the `live-voice-functional-python`, `-web`, `-web-race`, `-typescript`
20260903 names in the private temporary directory.

## Real digital audio attempts

Runtime f1 uses Cascade, an owned headless browser, real recognition, semantic
model, JiuwenSwarm Agent/Tools and rendered non-silent audio. Its registered
disposable project is `proj_d5e2d010`. No transcript business RPC or structured
Task creation button was used. Physical microphone/speaker experience is untested.

1. `live-voice-functional-audio-20260903-f1.json`: analysis/read-and-answer passed
   with no Task or project-file mutation. Explicit delegation then created exactly
   one Core Task/command, retaining all eight checked flight constraints. The
   Task `task-0904cf4ea10c4cedb5b9f55e84b1816d` ran and failed with
   `PROJECT_WORKTREE_BASELINE_MISMATCH`; there is no immutable Task result.
   The test oracle also incorrectly expected the internal `dispatched` status
   at the frontend `round_accepted` boundary. Rechecking the retained observation
   with the corrected round status plus exact successful Core receipt passes
   creation-only assertions; the original failed report remains unchanged.
2. The fixture copied an LF file while inheriting host `core.autocrlf=true`, so
   its task checkout had different bytes. Only this owned disposable project and
   future fixture initialization now use `core.autocrlf=false`. The Executor's
   byte-baseline guard was not weakened; general mixed-EOL support is unverified.
3. `live-voice-functional-audio-20260903-f2.json`: rerunning analysis in the same
   conversation failed the no-file-effect assertion. The frontend Agent wrote
   `出行方案.md` while answering the fresh analysis-only request using older
   delegated requirements. There was still only the earlier failed Task and zero
   Task results. The file SHA-256 is
   `1ad7cc4b71a1cb73ee363e2ae634ff1e19b3ec0b573bce7e8c4acea4bb33ad66`.
   It is a foreground side effect, never a successful background artifact.
   The dependent delegation step did not run in this second attempt.

Therefore the small analysis → delegation → successful Task → file loop is
**INCOMPLETE**. The newly exposed foreground current-turn/context boundary needs
repair. A/B controls, offline completion/recovery, A2, non-travel generalization,
current-source Realtime audio and cumulative independent review are not proved
by this checkpoint. No full Demo, full suite or physical acceptance was run.
