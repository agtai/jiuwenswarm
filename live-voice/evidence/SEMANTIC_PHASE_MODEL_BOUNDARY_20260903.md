# Phase-specific semantic model boundary — 2026-09-03

Scope baseline: `478102789de5d24c1702c896fae81f68e405fb9a`. This is a
coherent model-adapter/parser module, not the complete production cutover.
Main owns writes; `checkpoint_review` performed independent read-only review.
No remote ref update, account/configuration write or business execution occurs
in this boundary. D-107 records the choices; root TESTING owns its Tier-3 scope.

## Intended behaviour and source

The configured model remains the only semantic decision implementation. Its
strict schema is generated for committed-input or assistant-analysis phase;
target/extraction/message/reference conditions match deterministic decoding.
Detailed acceptance continues a unique applicable proposal; independent new
work does not inherit unrelated work. This is generic model instruction, not a
phrase parser, business fixture, output repair or authorization grant.

The existing Provider capability adapter supplies a per-call low reasoning
option only for the verified matching provider capability. Ordinary Agent
construction and saved settings do not change. The exact invocation options
are included in semantic configuration identity. One empty-final retry shares
the original 45-second deadline and repeats authority validation; tool requests,
malformed nonempty output and cancellation do not acquire that retry.

| Product file | SHA-256 of tested formatted working source |
|---|---|
| `task_semantics.py` | `389e7f50bcd83786d6925eb2c89be4f5c770dae6094de1847436f716577ba688` |
| `p3_model_resolution.py` | `263deb42cb5bead9308eb6637f0611c523621ff15d895eb85323f52c204f4f03` |
| `reasoning_injector.py` | `6877ac4baf06e2bd121769ef40ec5abc3526b86202fd944dae8fa4d2810718df` |
| `live_voice_operation_budgets.py` | `c940a2059285929e54590e65f727874e00c32ea792ee9fdb52d825909cb44304` |

The first two are under `jiuwenswarm/server/live_voice/`; the last two are
under `jiuwenswarm/common/`. Constants are an included dependency, not a new
workflow or semantic route. The containing commit identifies the module source;
the broader in-progress cutover is not part of this module's completion credit.

## Verification and retained failures

Actual command, with the repository's existing virtual environment:

```powershell
python -m pytest --no-cov tests/unit_tests/live_voice/test_task_semantics.py tests/unit_tests/common/test_semantic_reasoning_options.py tests/unit_tests/live_voice/test_p3_authenticated_composition.py -k 'semantic or server_model or model_catalog or model_binding or model_identity' -q
```

Result: **83 passed**, both before and after formatting. Ruff checks, Ruff
format check and Python compilation pass on all seven model/tool/test files.
Logs remain in the task's private temporary evidence as
`semantic-model-module-closure-formatted.log` and related scoped logs.
An isolated export of staged tree `01394bfc8111a5ad35d0661f1a131d40a18d9e1a`
also passes the same **83 tests** without the uncommitted cutover, using the
existing interpreter but the export as working directory. Its log is
`semantic-model-isolated-index.log`. Only this evidence paragraph was added
after that tree export; product/test sources are unchanged.

The fixed model-only probe is executable as:

```powershell
python -m scripts.live_voice.semantic_model_probe --config-dir <existing-private-config> --output-dir <new-isolated-evidence-directory>
```

It reads configuration in place, invokes the actual configured model without
tools, preserves all case outcomes and returns nonzero on any failed case.
The test-side corpus covers analysis, Chinese/English creation, missing
proposal, negation, missing target, real concrete versus generic offers,
detailed acceptance with retained constraints and independent new work.

Retained sequence (all results remain, none overwritten):

- Earlier high-effort and non-thinking probes failed; they were not promoted.
  Low-effort v6 passed 8/8, but a 41.6-second proposal response grants no latency
  acceptance. Original digital audio attempts 12/13 exposed semantic timeouts.
- Original digital audio attempt 14 passed actual recognition, file reading,
  output playback and proposal extraction. Detailed delegation omitted its
  proposal reference, so that step **failed** and created no Task.
- The new continuation cases passed v7 2/2. The complete v8 probe passed 9/10:
  a committed-input acceptance returned route `proposal`, allowed by the old
  shown schema but correctly rejected by decoding. This prompted the phase
  schema correction, not a changed user utterance or relaxed assertion.
- v9 `model-probe-20260903T060716033244.json` passed **10/10**. Elapsed times
  ranged from 4.08 to 14.03 seconds. It uses actual model output with no repair;
  it is **not browser audio, Task execution or physical acceptance**.

Applicable scenario coverage: positive creation/analysis/continuation; negative
malformed/unknown/duplicate fields and tools; bounds and exact identity/digests;
deadline, cancellation, repeated authorization and exact empty retry; legacy
frozen-record compatibility; configured-model and capability failures. Schema
does not authorize side effects. Store/Executor/media concurrency belongs to
the cutover's own regression, not this pure decision module. Retired semantic
feature flags are not restored for a feature-off matrix row.

## Independent review and exclusions

Independent review is **C0/I0/M0** for this complete model-module diff.
The reviewer checked actual logs and additionally exercised in-memory
schema/decoder agreement, unchanged real catalog construction/identity, and
legacy frozen records without `source_span_bounds`. It did not run a physical
or audio journey. Earlier Web ACK and closed-replay reviews are separate
boundaries and are not being committed as part of this model module.

Remaining: full Registry/Web cutover and old-oracle migration, original-audio
positive replay, both routes' full digital minimum, exact clean final-candidate
regression/review and operator-observed physical Demo. This evidence grants none
of those missing layers or Production-ready status. Historical evidence files
retain their original source and outcome.
