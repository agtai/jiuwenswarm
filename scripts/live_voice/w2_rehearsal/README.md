# W2 product diagnostics

The signed W2 evidence Gate, Replacement Ledger, rehearsal controller, fault
runner, signing/evaluation CLI, policy/manifest scaffolds and their dedicated
tests were removed under D-072. Nothing in this directory creates Gate credit
or participates in W2/Alpha completion.

Two evidence-free product validation aids remain:

- `w2_d069_runtime_diagnostic.py` exercises the real bounded P3 same-task
  A→B→C and restart topology plus a real P2 smoke, without signatures, evidence
  owners or injected Gate faults.
- `w2_wav_speech_preflight.py` and `assets/` provide a deterministic WAV
  for real Speech-provider readiness checks. This is repeatability input, not a
  substitute for physical microphone or audible human acceptance.

Current product acceptance is defined by
[`live-voice/validation/INTEGRATED_DEMO_ACCEPTANCE.md`](../../../live-voice/validation/INTEGRATED_DEMO_ACCEPTANCE.md)
and the live next action is owned only by
[`live-voice/STATUS.md`](../../../live-voice/STATUS.md).
