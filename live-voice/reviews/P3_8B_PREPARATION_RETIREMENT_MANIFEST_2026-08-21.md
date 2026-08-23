# P3-8B preparation and retirement manifest review — 2026-08-21

## Result

`PREPARATION CANDIDATE / FINAL INDEPENDENT REVIEW PASS` on baseline
`965fc827fb409b97d791f64febc7d32f0aaf71d3`.
This B1 packet is add-only. It does not claim P3-8B closure, P3-7 integration,
external-backend composition, physical acceptance or deletion authority.

The accepted P3-8A codec, product adapter, exporter, fault harness and privacy
conformance assets remain unchanged inputs. B1 adds two pure contracts and a
machine-checked retirement inventory; it does not edit a runtime composition or
package export surface.

## Exact scope

- `jiuwenswarm/server/live_voice/observability_correlation_contract.py`
- `jiuwenswarm/server/live_voice/live_voice_configuration_declaration.py`
- `tests/unit_tests/live_voice/test_observability_correlation_contract.py`
- `tests/unit_tests/live_voice/test_live_voice_configuration_declaration.py`
- `tests/fixtures/live_voice_retirement_manifest_v1/manifest.json`
- `tests/unit_tests/live_voice/test_live_voice_retirement_manifest.py`
- this review

No existing file is modified. In particular, `__init__.py`, `STATUS.md`,
`DECISIONS.md`, P3-7-owned surfaces and final evidence are excluded.

## Contract truth

The correlation contract is frozen, immutable, content-free and bounded. Every
high-cardinality identity must be a field-scoped public token of the form
`lvpub:<kind>:v1:<16-lowercase-hex-scope>:<64-lowercase-hex-HMAC>`. The trusted
upstream identity-projection owner must create keyed-HMAC tokens and issue an
exact receipt that attests the issuer, method, shared scope, complete token-set
digest and absence of raw identity. A receipt structure is only a transport
assertion: it cannot make a map ready. B1 requires an independently injected,
trusted owner receipt-verifier seam to authenticate the keyed MAC over the
exact receipt/token set. Missing verifier, false or non-boolean verification,
verifier exception and a matching-digest receipt self-signed with another key
all fail closed with zero product effects. Thus provenance is established only
relative to the B2-injected trust anchor; B1 neither receives raw identity nor
hashes raw PII itself, and makes no bare-hash public-safety claim. An email,
phone number, transcript marker, unverified token or token from another scope
is rejected. Mandatory subject-to-project-to-session causation roots bind the
map scope, and every other causation link binds identities from that exact map.
High-cardinality tokens are returned only by the trace correlation projection.
Metric dimensions use seven closed keys and P3-8A values; arbitrary identity
dimensions are rejected.

The configuration contract accepts only an already-validated, immutable input
record and revalidates that record before declaring exact capabilities. It does
not read environment variables, start a Provider/backend/worker, perform I/O,
or weaken authentication/durability truth. Ordinary production remains
explicitly default-off. Impossible profile, authentication, Executor,
durability and Provider combinations fail closed. A declaration retains its
complete normalized configuration projection plus a canonical SHA-256
fingerprint and rechecks every auth, Executor, Provider, receipt and capability
mapping. It is explicitly `authoritative=false` and
`authorization_granted=false`; no caller may use it as authority. Exact replay
is idempotent, while the same configuration id/digest with another projection
fingerprint is a configuration conflict.

## D-032 Tier-3 evidence map

| Dimension | Evidence or scoped inapplicability |
| --- | --- |
| `P` Positive | Exact formal/ordinary declaration and full 19-link/7-dimension public-token correlation maps succeed. |
| `N` Negative | PII, bare-SHA self-signed substitution, missing/false/non-boolean/raising trust verifier, missing/wrong receipt, malformed/cross-scope tokens, open metric values, missing parents, invalid auth/Executor/Provider/durability mappings and direct declaration forgery fail closed. |
| `B` Bounds | Exact public-token length, 63/65-hex malformed tokens, max generation, 19 links, 7 dimensions, 128-character configuration id and 8 Providers are exercised; one-over values reject. Empty metric/optional correlation sets and ordinary empty declaration are valid. |
| `S` State | The B1 contracts own no lifecycle or terminal state and cannot authorize/mutate one; state transition/tombstone scenarios are therefore inapplicable here and remain P3-7-owned. Result/declaration immutability is tested. |
| `T` Time/order | Canonical metric/link order, duplicate/reordered links and exact replay ordering are tested. The contracts own no clock, timeout or delayed event queue, so timeout fencing is inapplicable. |
| `C` Concurrency | The evaluators are pure over frozen inputs, have no shared mutable state and cannot linearize an effect. Runtime races are inapplicable; every result enforces zero effects. |
| `R` Retry/recovery | Exact correlation/config replay is idempotent; identity mismatch and same-identity changed-projection conflicts reject. Restart, partial I/O and unknown outcome are inapplicable because B1 performs no I/O or lifecycle work. |
| `I` Identity/isolation | Owner-receipted field/scope tokens, mandatory root and same-map causation, every missing-parent form, cross-scope token rejection and exact configuration identity/fingerprint binding are tested. |
| `F` Feature/failure/fallback | Feature-off touches neither poison input nor runtime and every effect stays zero. There is no fallback path or capability downgrade. |
| `K` Compatibility/regression | No existing module or package export is edited; the exact accepted P3-8A 207-case suite passes. Manifest paths/locators revalidate current source. |
| `X` Cross-module/real path | Deliberately inapplicable to B1: no P3-7 or external-backend composition is claimed. The exact frozen seams and B2 dependency gate are recorded for second-stage real-path verification. |

All evaluator results assert zero Agent, Tool, Task, audio and history effects;
the relevant pure-contract results additionally assert zero exporter,
environment, Provider, backend, worker, network, persistence, lifecycle,
downgrade and business-result effects.

## Retirement inventory sources

The manifest has 35 source-locator mappings back to the branch-content and
duplication audits, including retained and local-only exclusions. Tests prove
every locator still occurs in its frozen source and every referenced path/test
exists. The complete S7 runner/support/five probes/two units, S8 unit/CLI,
`product_p2_readiness.py`, P2/Web activation binding equality and frontend
`productCompositionContract` trust boundary are explicit.

The document rebaseline compares Batch A's completed 19 paths, Batch B's 12 and
Batch C's 43 paths directly with the Markdown audit. All 55 current B/C paths
are individually present in the manifest. The 20 later documents and five
pre-B1 post-note documents are frozen as exact path sets with canonical digests
and verified directly in baseline `965fc827` by Git object lookup. The B1 review
is separately frozen under `b1_added_paths`, proven absent from that baseline
and present in the candidate `HEAD`; it is never falsely attributed to the
baseline. Every item has an explicit disposition and no deletion authority.
The audit-time retained 20-file working set is also recorded.

Shared files are never whole-file targets. The manifest names candidate and
retained symbols for `project_code_executor.py`, both dedicated-media/WebChannel
files, `product_p3_text_adapter.py`, `dotenv_early.py`, `voice_task_bridge.py`,
`batch_speech.py`, authenticated composition and the product registry. In the
P3 text adapter only `_QUERY_OPERATIONS` and `_MUTATION_OPERATIONS` are named
consolidation candidates; `ProductP3TextAdapter` query, mutation rejection,
activation, progress and cleanup authority remains retained. Generic scheduling,
current fixed-route media registry/WebChannel authority, formal Speech/
composition/Task/Direct Executor, independent trust validation and accepted
P3-8A assets remain explicit retained/excluded owners.

## Independent review finding closure

| Finding | Closure |
| --- | --- |
| Declaration mapping could be forged | Full normalized projection and canonical fingerprint are bound into every declaration; direct Provider/capability/receipt/auth/Executor forgeries reject; declaration and result cannot grant authority; configuration replay conflict is explicit. |
| Correlation accepted ordinary PII | A field/scope-bound token set becomes ready only when its keyed-MAC receipt validates relative to the injected trusted owner verifier; email/phone/private markers, a matching-digest receipt self-signed over bare SHA, wrong-scope and malformed tokens reject while identical authenticated tokens remain stable and locatable. |
| Audit inventory was hand-selected | Frozen audit locator mapping, full missing code/script/test objects, 55-file B/C source comparison, baseline 20+5 plus separate B1 candidate provenance and retained/excluded records are machine checked. |
| Shared files looked like deletion targets | Exact candidate/retained symbols and `whole_file_deletion_target=false` are mandatory and source-validated for every shared boundary. |
| D-032 matrix incomplete | Complete `P/N/B/S/T/C/R/I/F/K/X` applicability is recorded above with max/one-over, parent, isolation, replay/conflict, feature-off and affected-regression automation. |

The subsequent independent cold review reported `0 Critical / 6 Important`
before amend. Those findings are closed as follows:

| Cold-review finding | Closure |
| --- | --- |
| Nested duck/poison values could be touched | Every nested receipt/dimension/link/auth/Executor/Provider/capability object and tuple is exact-type checked before any nested attribute or iterator access; poison-getter tests assert zero touches. |
| Bare SHA-shaped identities could encode low-entropy PII | Receipt shape no longer grants readiness. The evaluator requires an injected trusted-owner verifier to authenticate the exact keyed-MAC receipt/token set; missing/false/non-boolean/exception and a matching-digest bare-SHA set self-signed with an attacker key reject. The review makes no bare-hash public-safety claim. |
| Same-kind root identities could cross scopes | Every map token must share the receipt scope and exact token-set binding; subject-to-project and project-to-session root links are mandatory. |
| Current media authority looked removable | `handle_registered_media_socket` and `_is_dedicated_media_route` are retained symbols; only the named prefix/compatibility seams remain candidates. |
| Direct Executor owner was misnamed | The replacement owner and source check now name the actual `DirectProjectCodeExecutorAdapter`; its retained symbols remain explicit. |
| Later documents lacked provenance | The later 20 and pre-B1 post-note five are frozen as exact baseline path sets and verified with `git cat-file`; the B1-added review is separately digested, absent at baseline and present in candidate `HEAD`. |

The trust-anchor repair previously passed an independent read-only re-review at
`0 Critical / 0 Important`. A subsequent final retirement audit reported
`0 Critical / 3 Important`; the three repairs below require final re-review:

| Final-audit finding | Repair |
| --- | --- |
| Legacy ticket-media replacement owner/oracle was wrong | Only `MEDIA_ROUTE_PREFIX`, `legacy_path_ticket_compat` and `_DEDICATED_MEDIA_ROUTE_PREFIX` remain candidates. Fixed `MEDIA_ROUTE_PATH`, `DedicatedMediaProductRegistry`, `handle_registered_media_socket`, `_is_dedicated_media_route` and `WebChannel` are retained under the current fixed-route media/WebChannel owner with both dedicated-route and WebChannel route tests. |
| `product_p3_text_adapter.py` was not protected as shared authority | A whole-file-false boundary names only `_QUERY_OPERATIONS` and `_MUTATION_OPERATIONS` as candidates and retains `ProductP3TextAdapter` plus query, mutation-rejection, prepared-query and progress activation seams. The duplicate entry is explicitly symbol-scoped. |
| B1 review was falsely attributed to the baseline | The baseline path set is now 20+5 with direct Git object verification. The B1 review has separate candidate provenance, is asserted absent from `965fc827`, present in `HEAD`, and retains its own canonical digest. |

The final independent read-only re-review of these three repairs reports
`0 Critical / 0 Important`; the preparation candidate is reviewable for local
integration. This is not P3-8B product closure or deletion authority.

## Frozen interface requirements and B2 integration manifest

B2 waits for P3-7 Gate PASS and these frozen owners:

1. Formal panel route: selected route, committed text, interaction/response
   generation and presentation acknowledgement.
2. Registry/AgentServer composition: authenticated subject/project/session,
   the trusted identity-projection-owner keyed-HMAC receipt-verifier trust
   anchor and formal route composition, without changing generic scheduling.
   Public correlation/export readiness stays unavailable until that verifier is
   injected; a receipt assertion by itself is never authority.
3. Task lifecycle: task/attempt/command/event/outbox/executor/checkpoint/effect
   identities and causation.
4. Feature profile: fail-closed ordinary-production default-off and exact
   formal profile selection.

After that freeze, B2 may map those identities into correlation, adapt validated
configuration into capability declarations, and compose accepted P3-8A assets
through the selected external-backend boundary. Retirement execution remains a
later candidate only after each replacement oracle passes.

## A-line requirements recorded only

The four frozen requirements above are requirements on P3-7/A-owned surfaces.
B1 neither requests nor proposes an edit to them. Any need to change their
schema, operation vocabulary, classifier or runtime authority is an expansion
requiring re-scope and re-tier before implementation.

## Verification

| Check | Result |
| --- | --- |
| Three new test files | **59 passed** |
| Accepted P3-8A affected suite (the exact eight-file command recorded by P3-8A) | **207 passed** |
| Scoped Ruff check | **PASS** |
| Scoped Ruff format check | **PASS** |
| Python compile of both new product modules and three tests | **PASS** |
| JSON/audit locators, Batch A/B/C source comparison, Git-verified/digested baseline 20+5 plus separate B1 candidate provenance, retained symbols and every inventory/test/review link | **PASS** (part of the 59 tests) |
| `git diff --check` and add-only name-status review against the recorded baseline | **PASS** |
| Final independent read-only Tier-3 re-review | **PASS — 0 Critical / 0 Important** |

No broader repository, frontend runtime or physical browser/device suite was run;
those are outside this pure add-only preparation packet.
