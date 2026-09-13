# SDK Task cold-start deployment repair

Scope: restore persisted Native tasks through the AgentServer P3 factory with
AgentCore 13493418 (0.1.17+livevoice.1). Tier 2 recovery/order repair; no source
schema, authority, Work, SDK or executor behavior changes. Register the Host
source codec explicitly before SQLite Store construction. Unknown or malformed
source evidence must continue to fail closed; never delete stored tasks.

The deployed startup failed with TASK_SOURCE_CODEC_UNAVAILABLE. Existing tests
imported NativeTaskSource before opening their Store and hid the startup order.
A fresh-process regression using a persisted real registry Task reproduced that
same error. Acceptance: the actual factory restores the populated Store with
unchanged task/attempt/event/outbox counts, affected source/factory regressions
pass, then the normal deployment checks succeed against the existing database.
Physical microphone/product acceptance remains the user's next step.

Verification: source, SDK integration and P3 composition suites: 199 passed.
Independent read-only review: no actionable findings. Scoped diff check passed;
Ruff's nine E701 findings are unchanged pre-existing fixture formatting (verified
against HEAD), with no new findings. Runtime deployment validation follows this
repair commit; unit evidence alone does not establish deployment success.
