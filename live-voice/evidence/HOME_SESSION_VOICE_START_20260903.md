# Home-page Session allocation for Live Voice — 2026-09-03

User-authorized Integrated Web entry improvement; no semantic, Provider,
latency, C019, Task protocol or backend configuration change.

## Contract and scope

Tier 2 owns the async click/Session/activation boundary. A connected Agent-mode
home page with a selected Code project may create an empty conversation through the existing server-owned
`session.create` and its `create_token` retry protocol. It preserves the chosen
model/project and unsent composer settings, registers an idle conversation,
then requests the existing browser-owned voice lifecycle only when that exact
Session's formal P2 route is ready. An existing Session is reused.

Repeated clicks allocate once. Cancel, unmount, Session navigation, changed
project/model, failure and late readiness cannot start voice for another
Session. Allocation sends no chat request, invents no user message and creates
no background Task. Formal readiness has a bounded wait and visible retryable
failure. Original disabled flags/modes and ordinary text-first creation remain.
The existing formal backend requires a registered, authorized Code project:
projectless/Work entry now gives immediate project-selection feedback with zero
allocation, rather than creating a default Session that cannot activate.
This is a reflection of the existing backend prerequisite, not a new grant.

Owned surfaces: App creation callback, ChatPanel start coordinator and launch
feedback, empty-conversation registration, three locale entries and focused tests.
Exclusions: a global button on non-chat tools/settings pages, browser permission
bypass, audio-device policy, complete business/physical acceptance, performance
work and broad regression. Universal projectless/Work voice requires a separate
session/project authority design; it is not implemented or claimed here.

## Verification

- `node --test tests/liveVoiceHomeStart.test.mjs`: 11/11. Covers one allocation,
  exact readiness, cancellation/navigation/unmount/disconnect, error/retry,
  activation timeout, existing/disabled paths, real store preservation and zero
  chat/history/Task dispatch; projectless rejection and failure cleanup on navigation.
  Timeout retry uses the same create token.
- `npm run test:create-conversation-session`: 5/5 existing protocol regressions.
- `node --test --test-name-pattern='mounted production ChatPanel ownership lifecycle' tests/liveVoiceIntegratedRoutePanelMounted.test.mjs`: 1/1.
- `npx tsc --noEmit`: PASS. Vite controlled-profile production build: PASS.
- Initial two new-test failures were missing draft-runtime setup in the test;
  fixtures now initialize the same runtime as App, and the whole focused file passes.

The complete scoped diff was reread against the pre-turn workspace snapshot.
No independent review tool was available for this batch; this self-review is
not independent-review credit. Full cumulative and physical business acceptance
remain open. Machine-private snapshots, focused diff and deployment manifest are
under `live-voice-home-start-20260903` in the local temporary directory.

## Deployment and browser observation

Browser observation on 6175 verified the enabled project-home button, one empty
Session allocation, navigation to that exact Session, authoritative project/mode
metadata, and automatic entry into the existing voice lifecycle. No text was
submitted and no background Task was created. The browser showed the active
voice surface in recovery; microphone capture and audible response were not
proved by this entry test. Exit was used to stop the test.

An initial projectless test created a `default`/Work Session and the backend
rejected activation with `FORMAL_TASK_AUTHORIZATION_DENIED`. This exposed an
existing backend constraint in `ServerSessionProjectAuthorityResolver._snapshot`: a registered
Code project with a matching directory/revision is required. The follow-up early
feedback prevents this futile allocation. Authorization was not relaxed and no
Demo project is selected by code. Both initial empty test Sessions are retained
as local test data; neither has conversation history.
On the final served bundle, a real projectless click immediately displayed the
project-selection message and stayed on `/chat/new`; no Session was allocated.

The deployment is a frontend-only overlay; backend processes/configuration are
preserved. Before/after snapshots agree on all eight Task rows, 24 command rows,
zero live Tasks and both project-file digests. Exact served bundle and source
digests are recorded privately. Changes remain in the inherited dirty candidate;
there is no isolated commit or remote update for this bounded entry change.
