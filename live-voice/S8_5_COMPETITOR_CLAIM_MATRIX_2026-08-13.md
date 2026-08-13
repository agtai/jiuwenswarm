# S8.5 competitor and claim matrix

> Snapshot date: 2026-08-13. This is positioning input, not proof of competitor
> internals or permanence. Recheck linked primary sources before publication.

## 1. Publicly documented reference points

| Product/project | Publicly documented capability relevant here | Boundary for our comparison |
|---|---|---|
| OpenAI GPT-live / ChatGPT Voice with Codex | Full-duplex/background delegation and the ability to start, prioritize, interrupt or redirect work are publicly described by [OpenAI](https://openai.com/index/introducing-gpt-live/) and the current [ChatGPT Voice guide](https://help.openai.com/en/articles/20001274). | Do not claim S8.5 uniquely supports voice redirection or interruption. Compare only visible revision lineage and Executor proof observed in our run. |
| Qwen Audio Agent | Its [architecture](https://github.com/QwenAudio/qwen-audio-agent/blob/main/docs/architecture.md) documents receipts, backend sessions, status/cancel and permission boundaries. | Do not reduce it to ASR/TTS or imply it lacks task control. Our claim is the exact code-task revision/fence/verifier slice demonstrated here. |
| LiveKit Agents | [AgentTask/TaskGroup](https://docs.livekit.io/agents/logic/tasks/) provide structured session workflow tasks. | Session workflow structure is not the same comparison as a durable code-task revision, but neither is evidence of product inferiority. |
| Hermes Agent | Its [messaging guide](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/messaging/index.md) and [slash commands](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/slash-commands.md) describe background work, queueing and steering. | Do not claim steering itself is novel. Compare audited identity, isolation and verifier facts only. |

## 2. Claims permitted after S8.5 PASS

| Permitted, when directly observed | Not permitted |
|---|---|
| “A committed voice command revised one running JiuwenSwarm code task while retaining the same task ID.” | “Industry first”, “only product” or “competitors cannot do this”. |
| “The product showed immutable revision and predecessor/successor attempt lineage.” | “Arbitrary live steer” or “the same Agent attempt changed course in place”. |
| “The old attempt was fenced and acknowledged before a clean successor was dispatched.” | “All irreversible side effects were rolled back” or external exactly-once. |
| “The Executor reported changed paths, a sanitized diff summary and an allowlisted verifier result.” | “The Agent proved its own work”, “all tests passed” without the named verifier, or general autonomous coding correctness. |
| “Flag-off, stale, ambiguous, wrong-scope and failure cases produced zero forbidden mutation in the accepted matrix.” | Production safety, general user-repository safety, D1/D2, public deployment or complete P3. |
| “Voice, Task Core, Executor and Web UI presented one traceable revision journey.” | A platform-wide generic interaction layer, durable preferences, approval handling, pause/resume/reprioritize or broad multi-agent orchestration. |

## 3. Presentation rule

Lead with the observed trace, not a superlative:

> “Watch one committed voice correction become revision 2 of the same task: the
> old attempt is fenced, a clean successor runs, and the Executor—not the model's
> prose—reports the diff and verifier result.”

If any identity, cleanup ACK, clean-base proof, verifier result or zero-side-effect
check is missing, remove that clause and record `PARTIAL` or `BLOCKED`; do not
replace evidence with comparative rhetoric.
