# Rehearsal interruption and query diagnosis — 2026-09-03

Read-only runtime diagnosis for session `web_1a0674671e3_bf74d8d92290` on the
retained 6175 environment. Times below are the local log timestamps (UTC+02).
No production code was changed, no live request replayed, and no service restarted.

## Source and evidence boundary

HEAD remains `87248911fde2220be6a97f72f8c0210ac67d5b67` with the inherited working
candidate. Deployed/current `task_semantics.py` SHA-256 is
`a44324ea8708e2958cb61441ded578265aee8d14bf21e16dabbf6df7fb585217`.
Thus the previous bounded regeneration repair was loaded during this incident.
Sources are runtime `agent.log`, `gateway.log`, session `history.jsonl`, read-only
formal Task and unified-input SQLite records, and current product code.
No model reasoning content or credentials were included in this diagnosis.

## Confirmed query failure

Request `live-voice-unified-1788439618779-10` arrived at 14:46:58.806 and failed at
14:47:02.499 (3.693 seconds). Agent log lines 32687 and 32692 preserve these final
model objects:

- First: `task.status`, `arguments={}`, null target, but extraction claims
  `arguments.query_kind`. Status requires `query_kind=status`.
- Second: `task.list`, still `arguments={}` and the same phantom extraction.
  List requires `query_kind=list` and `limit`.

Both continuation tuples were correctly null. This is a different malformed
output from the prior null-reference `accept_proposal` failure. The previous
repair made its permitted second attempt; the model still omitted required
arguments. The decoder correctly rejected both. The Provider receives a JSON
format request plus a textual schema, not enforced operation-specific decoding;
the retry feedback is generic and emphasizes continuation fields, without naming
the actual missing query fields. Required-argument reliability remains open.

The question has two visible Tasks in scope. A valid collection query or useful
target clarification is required; neither selecting an arbitrary Task nor
creating another Task is an acceptable fallback.

## Confirmed interruption context loss

| Time | Observed event |
|---|---|
| 14:42:36.677 | Final 7 submitted: compare flights, trains and rental cars |
| 14:42:39.560–39.721 | Exact generation-interruption RPC received and completed |
| 14:42:46.181 | Final 8 submitted: exclude rental cars, compare flights and trains |
| 14:42:53.150 | Replacement assistant text persisted: acknowledgment of excluding cars only |
| 14:43:00.604–00.726 | A presentation ACK RPC received and completed |

Finals 7 and 8 were both routed as dialogue. Final 8's frozen semantic history
does not contain final 7; its latest user/assistant pair is the earlier airline
contact question. `SemanticContinuity.history()` builds only pairs from presented
analysis records. `AgentConversationRuntime.select_formal_context()` likewise
skips an output with no presented TEXT units, removing its committed user question
along with the unpresented answer. The isolated formal Agent uses that selected
context rather than ordinary chat history. Generation interruption therefore
loses the unresolved comparison request. The replacement acknowledges the changed
constraint but does not complete the comparison. This is distinct from ASR failing
to hear the correction, and from the later query schema failure.

## Listening stall: localized, exact owner not yet proven

Gateway logged the replacement downlink attachment at 14:42:53.883 and successor
uplink first-frame/ACK at 14:42:54.013–54.015. At 14:43:00.603–00.881 it recorded
media cleanup, a connection close and streaming-recognition degradation. A further
streaming recognition timeout appeared at 14:43:20.760. No new media handshake is
logged until 14:46:04.064, after P2 activation at 14:46:02.945. Meanwhile AgentServer
continued answering notification polls, generally about once per second.

This localizes the reported persistent stall after the replacement answer to
capture/presentation/notification settlement, rather than one Agent generation
still running for minutes. The UI's `thinking` label is ambiguous: it represents
text submitting/waiting, P1 starting/recognizing, or non-idle Task-announcement
state. The capture scheduler refuses restart behind retained foreground,
presentation or Task-announcement barriers; the notification loop has narrowly
guarded release from `fetching` and can otherwise keep polling.

However, the server logs do not preserve the frontend state/owner snapshot or
the exact response identity for that ACK. Both accessible browser bindings had
no tabs. The specific retained frontend owner cannot be uniquely established
from these records. Treat notification/capture arbitration as an investigation
target, not a proven final root cause. A bounded reproduction with state-transition
and exact response/capture identity evidence is still required; do not call this
stall fixed or fully diagnosed.

## Additional observed issues

- Foreground analysis still contains wrong arithmetic: F01 departs 19:10 and
  requires 90 minutes at the airport, but the answer says arrive by 18:40 rather
  than 17:40. Its 17:10 departure recommendation consequently conflicts with the
  90-minute transfer. This is grounded-answer calculation failure, not ASR.
- Client draft says the traveler has already changed to another service, although
  the supplied snapshot says unbooked and no execution was authorized. This is
  unsupported completed-action wording inside the generated draft.
- Task notices remain English despite the Chinese interaction. Registry and Web
  fallback paths contain fixed English presentation strings, outside ordinary
  Agent response-language guidance. This is a presentation-localization defect,
  not evidence of a domain-specific intent classifier.
- Six streaming-recognition timeout fallback entries, one protocol fallback and
  one later route-aborted fallback occur in this session. The coarser degradation
  messages also appear near intentional capture retirement, so they cannot all
  be classified as independent Provider/network outages. Existing logs do not
  expose enough lifecycle detail to identify every upstream exception.

## Authoritative Task and artifact outcome

| Task | Created | Terminal completed |
|---|---|---|
| A `task-ff19a68970184f9c86a39880abd41c2d` | 14:40:18.909 | 14:43:56.605 |
| B `task-56ff40c0f42b4ad28fe8802caf0db37d` | 14:41:11.913 | 14:45:54.335 |

Both actual files exist and match their result manifest hashes:
`行程调整方案.md` and `给客户的说明草稿.md`. The total Task count is six including four
prior Tasks. For A/B the command journal contains create and event acknowledgments,
with no adjustment, update or cancellation. No duplicate Task resulted from either
the interruption or failed query. A's completion is not shown in this session's
assistant history; its voice event ACK remains at running sequence 3, while B's
completion received a text ACK. A's unpresented completion remains an open
notification-delivery observation, not proof that A failed to finish.
