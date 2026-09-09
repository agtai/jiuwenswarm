# Unified AgentCore final verification

Goal remains active. This record separates completed verification from pending
Host breadth, frontend build, controlled deployment and real automatic acceptance.

## Installed SDK breadth

Verified source: `ffeb1abcc5cc0bc72b5c813a3316d4334d39e15f`, tree
`6f3826983ea8c15eb182ec7761705fd5058c1235`, twelve ordered patches.
Actual editable import resolves to the retained `.deps/agent-core` source.
The SDK has no upstream tracking branch. Local `core.autocrlf=false` preserves
the reviewed checkout bytes; refreshed index metadata did not change its tree.

One broad run covered complete affected owner unit directories: Harness (except
unchanged tools), agent_teams, React Agent, core/session, core/workflow,
core/common and core/foundation/llm. Result: **5492 passed, 16 failed, 38 skipped,
3 xfailed, 4 collection errors**, 3 integration-marked cases deselected (211.42 s).
The four errors require missing optional `prompt_toolkit` for the CLI; the
configured in-process Team boundary does not use that CLI.

Only the 16 failures were investigated/replayed with shorter isolated Windows
TEMP paths. Current source and pinned original `94e10cb6` each produced **10
passed and the same 6 failures**. Those six are one Windows path-length case,
one separator assertion and four unchanged NO_PROXY/CIDR assertions. Other broad
failures involved combined-run timing/state or the temporary write-isolation
guard. Original failed evidence remains; this is not an all-green SDK claim.
No new patch regression was demonstrated by this comparison. No broad rerun
was performed, and this environment result does not establish physical behavior.

Detailed commands, actual import origins, original output, report and exact
baseline comparison remain at
`%TEMP%/agentcore-final-breadth-f4b0db14dd9b4c28948f1aaa721666ba/REPORT.md`.

## Pending candidate evidence

Core assembly scoped review is closed, including the fixed metadata ABA race.
Host breadth/build, final clean source identity,
runtime source/model binding and browser/Provider/Agent/tool automatic journeys
remain pending. The isolated candidate checkout preserves the original private
workspace files and shares only the retained reviewed SDK source. No remote ref
update is authorized or performed.
