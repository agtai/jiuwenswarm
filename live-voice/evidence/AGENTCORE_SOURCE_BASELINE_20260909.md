# AgentCore source baseline — 2026-09-09

This is the Task 1 source-install/direct-reuse boundary of the
[accepted execution plan](../reviews/AGENTCORE_UNIFIED_EXECUTION_20260909.md).
It grants no new unified-capability, code-retirement, Provider or physical credit.

## Source and installation

- JiuwenSwarm baseline: `80d06b95fa8a2e4c58b551a56cd1bd61dce71ebe`.
  The candidate is the coherent commit containing this record.
- AgentCore upstream base: `94e10cb6102c36fe78a64547957c0def97299273`.
- Paired AgentCore commit: `dec128e525198a16e19a0a737e1b0889d936e715`,
  `fix: preserve Responses context in pinned JiuwenSwarm source`.
- Reviewed content tree: `d55cd0baeea72c1219231b355ad8069ecd73bd1c`.
  `scripts/sdk_patches/agentcore-source.json` and the carried patch reconstruct
  this tree without depending on a local commit timestamp.
- New checkout: `.deps/agent-core`, independently cloned from the local Git
  mirror containing that upstream object, on `codex/live-voice-unified`.
  The unrelated source repository/worktrees were preserved.
- The installer explicitly uninstalled the old
  `0.1.16+jiuwenswarm.responses2` wheel distribution, then used
  `uv pip install --python .venv/Scripts/python.exe --no-deps --editable .deps/agent-core`.
  Fresh-interpreter inspection found exactly one AgentCore distribution, editable
  `direct_url.json` pointing to this source, and the actual module origin at
  `.deps/agent-core/openjiuwen/__init__.py`.
- `uv lock --offline` changed only AgentCore's source/version and corresponding
  local-source metadata; resolved package versions elsewhere were preserved.
  `uv sync --frozen --inexact --dry-run` proposed refreshing only the JiuwenSwarm
  editable root, with no AgentCore replacement.

## Checks and review

Commands used the project's `.venv/Scripts/python.exe`, with pytest flags
`-q -o addopts= -o log_cli=false --asyncio-mode=auto` to avoid unrelated
coverage/report generation during the scoped checks.

| Check | Result and limit |
|---|---|
| Actual new AgentCore source prepended to `sys.path`; `test_agentcore_source.py`, `test_openai_agentmodel_compatibility.py`, `test_debug_launcher.py` | 93 passed, 5 platform skips. Includes 40 real SDK Responses/Agent/tool compatibility cases with simulated HTTP, not a live Provider claim. |
| G0/G1 execution conformance after updating exact-source guards | 14 passed, 13 strict expected gap failures. Existing cancellation/identity/atomic-admission gaps remain explicit; source guards now verify reviewed tree and actual import instead of expecting obsolete wheel/VCS metadata. |
| Final affected source/installer/launcher files: `test_agentcore_source.py`, `test_install_agentcore_source.py`, `test_debug_launcher.py` | 59 passed, 5 platform skips. Proves clean-source reconstruction, Windows patch transport, added files, idempotent preparation, retention of existing edits, uninstall-before-install ordering, source/import mismatch rejection and zero service launch on failure. |
| `scripts/install_agentcore_source.py --check` in a fresh interpreter | Passed against the installed editable source. |
| Actual alternate audit checkout prepended to `sys.path` | Rejected with `AgentCoreSourceError`; the normal source still passed afterward. |
| `git diff --check`; changed Markdown file targets | Passed; 11 added/changed local link targets resolved before this evidence link was added. |

The first reconstruction fixture failed because Python's default Windows newline
translation committed CRLF test blobs while its generated patch used LF. The
fixture now explicitly models the pinned upstream's LF blobs and delivers a CRLF
patch. Only affected source/installer/launcher checks were repeated; the failure
was not erased or treated as product behavior. A stdlib link-check helper also
needed explicit UTF-8 decoding for Chinese paths before it passed.

One independent scoped code review found two necessary fixes: actual module
origin was not checked, and current first-install/recovery documents omitted
source preparation. Both were repaired. Origin verification checks both module
resolution and an already-loaded module's file; post-install verification uses a
fresh interpreter so its new editable finder is active. README, the Live Voice
runbook and both install guides now include source preparation. Main reviewed
the complete scoped diff and the fixes. No further blocking finding remained.

## Direct reuse conclusion

Production Formal Agent/Tools already call the configured AgentCore
`DeepAgent.attach_output/send_input`; the project Executor already calls the
configured Code Agent. The independent design check found no equivalent direct
replacement for the surrounding exact-round, Work or durable Task owners.
The common/controller/team Task managers, Checkpointer and AsyncToolRuntime
have different lifecycle/persistence responsibilities.

Task 1 therefore establishes verifiable source use and preserves existing direct
execution. It removes the obsolete standalone-wheel builder, but makes no claim
of reducing Live Voice runtime code. Actual capability sharing and corresponding
runtime deletion remain Task 2; demonstrated generic gaps and consumer cutover
remain Task 3. Complete automated and real-scenario verification is reserved for
their final integrated candidate.
