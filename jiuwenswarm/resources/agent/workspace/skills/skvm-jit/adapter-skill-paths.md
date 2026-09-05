# Resolving the original skill directory

Use the exact skill path already returned by the host or user. Only when absent,
look up the relevant convention below and verify the directory contains the
intended `SKILL.md`. Do not scan unrelated private roots or assume the first
same-named file is the version that ran.

| Host | Conditional locations |
|---|---|
| Claude Code | Project `.claude/skills/<name>/`, user `~/.claude/skills/<name>/`, or a plugin path exposed by the host |
| opencode | Project `.opencode/skills/<name>/`; user paths require host configuration |
| openclaw | Use the installed skill location exposed by the host; a `/tmp/skvm-openclaw/...` benchmark workspace is not a persistent installation |
| hermes | Common user location `~/.hermes/skills/<name>/`; verify the loaded version |
| JiuwenSwarm | Use the runtime-provided skill directory; normal installed skills live under the configured agent workspace's `skills/` tree. Do not confuse this with a SkVM adapter's inject-only benchmark input. |
| bare-agent / SkVM benchmark | The benchmark owns optimization; do not launch another post-task loop |

When a run used injected content without a persistent source directory, an actual
source skill is needed for `--skill=<dir>`. Do not manufacture a path or assume a
private installation. If the original cannot be resolved from available context,
ask for that missing source location and continue independent analysis meanwhile.
