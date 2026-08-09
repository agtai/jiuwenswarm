from __future__ import annotations

from pathlib import Path


_BUNDLE = Path(__file__).resolve().parents[1]


def test_fresh_attempt_uses_candidate_bound_helpers_and_default_wav() -> None:
    script = (_BUNDLE / "new_w2_rehearsal_attempt.ps1").read_text(encoding="utf-8")

    assert "$candidateBundle = Join-Path $candidateRoot" in script
    assert "& $Python $candidateScaffoldScript" in script
    assert "& $Python $candidatePlanScript" in script
    assert (
        "Join-Path $candidateBundle 'assets\\voice-command-48k-mono-pcm16.wav'"
        in script
    )


def test_runtime_entrypoint_delegates_to_candidate_bound_python() -> None:
    script = (_BUNDLE / "start_w2_rehearsal.ps1").read_text(encoding="utf-8")

    assert "Join-Path ([string] $configValue.candidate_root)" in script
    assert "Join-Path $candidateBundle 'w2_rehearsal_runtime_controller.py'" in script
    assert "Join-Path $candidateBundle 'w2_wav_speech_preflight.py'" in script
