# ASGI media route integration repair

## Scope before implementation

The rebase uses upstream's default dual-protocol WebChannel. Its FastAPI router
does not register `/ws/live-voice/media`; browser upgrades receive HTTP 403
before reaching authentication. The legacy dispatcher has the media handler,
but ASGI never reaches it. The adapter also lacks the negotiated subprotocol.

Restore the existing contract: register the fixed route, require an allowed
nonempty Origin independently of the ordinary RPC Origin toggle, negotiate
`live-voice.media.v1`, and dispatch to the existing one-use ticket authenticator
and binary transport. Reserve this path against plugin/main-route collisions.
No changes to ticket authority, media schemas, providers, tasks or ordinary RPC.

Owned surfaces: web_channel_app.py, ws_connection_adapter.py and ASGI media
tests. Tier 3 transport/security integration, restoring existing authority.
Acceptance: positive handshake/binary frames; wrong Origin/protocol/ticket and
unavailable registry fail closed with zero unauthorized dispatch; existing
dual-protocol/media regressions; independent scoped review; deployed same-origin
media evidence. Existing tests own ticket replay/identity/concurrency semantics.
Physical microphone/speaker acceptance is not inferred from protocol probes.

## Reproduction

Deployment logs record five media HTTP 403 handshakes around 02:22-02:23 local.
Before repair, three new ASGI tests fail: valid media does not reach its handler,
invalid auth does not reach the authenticator, and unavailable-registry close
behavior is unreachable.

## Source verification

- ASGI media and existing dual-protocol tests: 20 passed.
- Existing dedicated media registration regressions: 185 passed, including
  ticket/ownership, provider lifecycle, replay and cleanup boundaries.
- Independent read-only review found no actionable issues in route registration,
  strict Origin, subprotocol negotiation, adapter or existing authentication.
- Source whitespace check passed. Deployment evidence is recorded externally
  after the repair commit so its source identity can be verified exactly.
