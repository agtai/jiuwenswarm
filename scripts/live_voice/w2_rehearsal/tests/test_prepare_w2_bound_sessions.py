from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.live_voice.w2_rehearsal import prepare_w2_bound_sessions


def _project(
    project_dir: Path,
    *,
    hidden: bool = False,
    work_mode: str = "code",
) -> SimpleNamespace:
    return SimpleNamespace(
        project_dir=str(project_dir),
        hidden=hidden,
        work_mode=work_mode,
    )


@pytest.mark.parametrize(
    ("registered_project", "expected_error"),
    [
        (None, "project is not registered"),
        ("hidden", "registered project is hidden"),
        ("work", "registered project work mode must be code"),
        ("wrong-path", "registered project path mismatch"),
    ],
)
def test_create_rejects_invalid_project_registration_before_session_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    registered_project: object,
    expected_error: str,
) -> None:
    requested_dir = tmp_path / "requested"
    requested_dir.mkdir()
    projects = {
        None: None,
        "hidden": _project(requested_dir, hidden=True),
        "work": _project(requested_dir, work_mode="work"),
        "wrong-path": _project(tmp_path / "other"),
    }
    writes: list[dict[str, object]] = []
    monkeypatch.setattr(
        prepare_w2_bound_sessions,
        "get_project_by_id",
        lambda project_id, *, cache_bust: projects[registered_project],
    )
    monkeypatch.setattr(
        prepare_w2_bound_sessions,
        "init_session_metadata",
        lambda **kwargs: writes.append(kwargs),
    )

    with pytest.raises(RuntimeError, match=expected_error):
        prepare_w2_bound_sessions._create(
            session_id="sess_candidate",
            title="W2 test",
            model="test-model",
            project_id="proj_candidate",
            project_dir=requested_dir,
        )

    assert writes == []


def test_create_persists_session_for_exact_visible_code_project(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    created: dict[str, object] = {}

    monkeypatch.setattr(
        prepare_w2_bound_sessions,
        "get_project_by_id",
        lambda project_id, *, cache_bust: _project(project_dir),
    )
    monkeypatch.setattr(
        prepare_w2_bound_sessions,
        "get_session_metadata",
        lambda session_id, *, cache_bust: created or None,
    )

    def persist(**kwargs: object) -> None:
        created.update(kwargs)

    monkeypatch.setattr(
        prepare_w2_bound_sessions,
        "init_session_metadata",
        persist,
    )

    prepare_w2_bound_sessions._create(
        session_id="sess_candidate",
        title="W2 test",
        model="test-model",
        project_id="proj_candidate",
        project_dir=project_dir,
    )

    assert created["project_id"] == "proj_candidate"
    assert created["project_dir"] == str(project_dir)
    assert created["work_mode"] == "code"
    assert capsys.readouterr().out == "SESSION_READY=sess_candidate\n"
