# P3-9 cumulative product acceptance evidence — 2026-09-02

## Result

**PASS — P3-9 HUMAN PRODUCT ACCEPTANCE** for the bounded one-product journey on
product source
`83fde562284e96df12f2e2546797c4703a75132b` from
`hx/0812_live_voice_w3`.

The operator completed all eight required spoken interactions and both
closeout checks in the ordinary Integrated Web surface. Task accepted/running
progress and the terminal result notification were visible and audible, the
microphone resumed after each Task announcement, the running adjustment was
truthful and applied to the result, foreground interruption left the detached
Task alive, and refresh/Exit lifecycle checks produced no duplicate or stale
effect.

This PASS closes the required P3-9 human Gate only. The final independent
Tier-3 candidate review will run in a separate Session; until it passes, P3-9
and the controlled product-readiness candidate remain **PARTIAL**. This result
does not claim feature completeness, fixed-corpus latency, broad device/network
or language generalization, D1, production authentication, multi-tenancy,
public deployment, SLOs, RC or Production readiness.

## Exact source and environment boundary

- Product source: `83fde562284e96df12f2e2546797c4703a75132b`.
- Comparison/upstream source:
  `aa9d92d42d90a0aaa105328a140c436436ca4b9b` on
  `agtai/hx/0812_live_voice_w3`.
- Product branch: `hx/0812_live_voice_w3`; the tested source was twelve local
  commits ahead of that upstream and the worktree was clean.
- Surface: ordinary installed desktop Chrome against
  `http://localhost:5173`, launched with the controlled
  `formal-web-validation` profile.
- Sanitized Session: `web_1a05f3d5c93_facee9663dcd`.
- Route: real microphone → authoritative Speech final → real JiuwenSwarm Agent
  and detached Task/Executor → TTS → browser playout, using the formal P2/P3
  presentation and ACK owners.
- Credentials, Provider/model configuration, audio-device identity, private
  runtime logs/databases and isolated project path remain machine-private and
  outside Git.

## Human journey

The operator used the frozen safe acceptance wording and reported that all
eight interactions and both checks passed:

1. `请帮我介绍杭州。` — ordinary foreground speech and audible answer.
2. `帮我在后台制定一份三天杭州行程。` — detached Task creation; accepted and
   running were each visible and audible, followed by resumed listening.
3. `杭州有什么特色菜？` — foreground dialogue continued while the Task ran.
4. During answer playout, `请帮我介绍杭州。` — only the current foreground
   playout was interrupted; the Task was not cancelled or changed.
5. `第二天下午改成西湖还是灵隐寺。` — the bounded ambiguous variant produced
   no running adjustment or Task mutation.
6. `把第二天下午改成西湖，晚上给我留出自由时间。` — the exact adjustment was
   queued without a false early-applied or completed claim.
7. `刚才的修改加进去了吗？` — the reply followed authoritative pending/applied
   state rather than dialogue acknowledgement.
8. After the one terminal notification, `第二天最早的固定安排是什么？` — the
   answer was grounded in the immutable result, and `itinerary.md` contained
   the requested second-afternoon West Lake change and free evening.

Closeout checks:

- One refresh did not repeat the terminal announcement or recreate the Task.
- Exit followed by one re-enable created a new generation that listened
  normally, with no stale playout or retained old-generation notification.

## Authority and forbidden-effect observations

- `accepted`, `running`, terminal/result and adjustment truth remained distinct;
  no delivery acknowledgement was treated as Task completion.
- The terminal notification was presented once through the current P2 owner and
  consumed only after its exact presentation ACK.
- Voice fallback, capture suspension and activation rotation did not lose,
  duplicate or mis-target the Task presentation.
- The safe ambiguous utterance produced zero adjustment side effect.
- Foreground barge-in, refresh and Exit produced zero Task cancellation, silent
  rerun, duplicate terminal presentation or cross-generation resurrection.

## Automated and build evidence

- The migrated P3-9 source beneath this repair overlay passed Formal Web
  `483/483`, the affected Python set `488 passed / 3 skipped`, the complete Live
  Voice Python set `2936 passed / 5 skipped`, TypeScript, the production build,
  Ruff/compile and repository checks. See the
  [W3 migration evidence](P3_9_W3_MIGRATION_EVIDENCE_20260825.md).
- At final product source `83fde5622`, the focused Integrated Route panel suite
  passed `65/65` and `npm run build:live-voice` passed. The broad 499-case
  frontend diagnostic reported `493 passed / 5 failed / 1 skipped`; the five
  mounted timing failures were outside the focused repair boundary, and a
  representative stale Task-TEXT case was reproduced against the unmodified
  comparison source. They are not counted as repair regressions or silently
  relabelled as passes.
- `git diff --check` and local-link checks pass for this closeout.

## Latency finding disposition

The earlier 44–45 second ordinary-answer samples were not evidence that server
batching was disabled. Web requested the bounded batch of 16, but each
`chat.delta`/`chat.reasoning` stream observer in a returned batch incorrectly
inherited the 500 ms “no useful Task notification” repoll delay whenever a
foreground response and an outstanding voice Task overlapped. Sixteen observer
items therefore added about eight seconds per batch, and repeated batches
created the observed post-Agent tail.

`83fde5622` excludes stream observers from that repoll delay while retaining the
delay for an actual empty/progress-only Task poll. The accepted P3-9 journey did
not reproduce the prior listening/notification failure. This is a code-fact
repair and one product-journey observation, not a fixed-corpus p50/p95 or general
latency claim.

## Closeout

The human acceptance Gate is closed on the exact product source above. The
separate final independent Tier-3 review remains the only P3-9 Gate. Later
source changes that can affect presentation, capture, Task truth, result
projection, adjustment or lifecycle ownership require affected revalidation;
documentation-only changes do not inherit or alter this human result.
