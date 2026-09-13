# Native notification sequence recovery

Baseline: `f5d4a3aacda75c58d66bb28296548c01eef09e76`.

## Scope and acceptance

The user authorizes repair of same-activation recovery after Gateway authority
TTL expiry. Host retains its admitted notification sequence; Gateway currently
recreates its fence at zero and cannot serve queued native audio.

Tier 3: extend the process-private Host activation descriptor with a bounded
authoritative notification cursor. The Gateway client validates and consumes it;
the media registry restores its fence only for the exact retained activation and
socket. Keep cursor snapshots separate from activation identity, never rewind a
live fence, and preserve neutral local notification delivery and retry semantics.
No browser schema, model, buffer, timeout, business policy or persisted data change.

Owned surfaces: Host product composition descriptor, Gateway native client,
dedicated media registry and their tests. Cross-module evidence must exercise
the real descriptor decoder and registry; physical audibility remains user
acceptance after local redeployment, not a claim made by deterministic tests.

Applicable matrix: P/R expired and fresh registry recovery; N/B malformed cursor;
S/T/C duplicate, delayed snapshot and concurrent forwarded request ownership;
I wrong session/socket/activation cannot consume audio; F/K descriptor without the
optional cursor retains old behavior; X Host descriptor to client to registry.
Agent/Tool/Task/history writes are excluded from this repair and must not be
introduced. No remote update is authorized.

## Review-driven scope refinement

Independent review identified a reachable race: refresh snapshot 3 can be built
before an unfenced poll 4 reaches Host, then be observed after that admission.
Taking max with an expired local fence is insufficient. Include the browser P2
owner and its tests (Tier 2 concurrency within the Tier 3 shared repair): settle
the existing notification poll before requesting refresh, gate new polls until
refresh settles, and recheck closure before requesting activation. This applies
only to the negotiated Native engine; Cascade does not use the private cursor.
A prior ambiguous failure is retried with its retained request ID before refresh;
the first result is queued ahead of any batch tail for the presentation consumer.
A retry error aborts refresh with existing cleanup semantics and preserves its
retry identity; it cannot publish an apparently synchronized activation.

## Evidence

Verified Gateway client/registry/downlink/wake suites: 250 passed; the additional
fresh-registry cases then passed in the six-case recovery group. Host activation,
real serialized Host-to-Gateway recovery, serial notification admission, keepalive
and cursor bounds: 5 passed. Web routing and exact-socket compensation: 87 passed.
The first Host seam test used an invalid transport fixture, corrected to reject
any unexpected RPC; the passing test makes zero Agent calls.

Browser regressions first failed on the old overlapping refresh behavior.
The broad run initially exposed unintended Cascade waiting; limiting the gate
to negotiated Native restored the existing Cascade behavior without weakening
or changing its tests. Final `npm run test:live-voice-integrated-web` run:
711 passed, zero failures, one existing skip; includes TypeScript checks,
bundling, the five new recovery scenarios and mounted component regressions.
`git diff --check` passed. Local logs use the `notification-recovery-` prefix.

Independent read-only review identified both the snapshot race and a previously
failed notification's retained request ID. Both are addressed. Final review
reported no remaining actionable findings. No physical microphone or 40-minute
human session was claimed by these deterministic checks.

Incident logs omit the precise notification sequence: the deterministic defect
matches the incident lifecycle but is not a field-by-field proof of that incident.
