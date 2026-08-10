from __future__ import annotations

import argparse
from pathlib import Path

from jiuwenswarm.server.runtime.session.project_store import get_project_by_id
from jiuwenswarm.server.runtime.session.session_metadata import (
    get_session_metadata,
    init_session_metadata,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create candidate-bound W2 sessions before any evidence owner starts."
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--title", default="W2 portable rehearsal")
    parser.add_argument("--model", required=True)
    return parser


def _create(
    *,
    session_id: str,
    title: str,
    model: str,
    project_id: str,
    project_dir: Path,
) -> None:
    registered_project = get_project_by_id(project_id, cache_bust=True)
    if registered_project is None:
        raise RuntimeError(
            "project is not registered in the current JIUWENSWARM_DATA_DIR: "
            f"{project_id}"
        )
    if registered_project.hidden:
        raise RuntimeError(f"registered project is hidden: {project_id}")
    if registered_project.work_mode != "code":
        raise RuntimeError(
            f"registered project work mode must be code: {project_id}"
        )
    registered_dir = Path(registered_project.project_dir).resolve()
    if registered_dir != project_dir.resolve():
        raise RuntimeError(
            "registered project path mismatch: "
            f"{project_id} uses {registered_dir}, requested {project_dir.resolve()}"
        )
    existing = get_session_metadata(session_id, cache_bust=True)
    if existing:
        raise RuntimeError(f"refusing to replace existing session: {session_id}")
    init_session_metadata(
        session_id=session_id,
        channel_id="web",
        user_id="",
        title=title,
        mode="agent",
        project_dir=str(project_dir),
        project_id=project_id,
        model=model,
        work_mode="code",
    )
    created = get_session_metadata(session_id, cache_bust=True)
    if created is None:
        raise RuntimeError(f"session was not persisted: {session_id}")
    if created.get("session_id") != session_id:
        raise RuntimeError(f"session identity mismatch: {session_id}")
    if created.get("project_id") != project_id:
        raise RuntimeError(f"session project identity mismatch: {session_id}")
    if Path(str(created.get("project_dir", ""))).resolve() != project_dir.resolve():
        raise RuntimeError(f"session project path mismatch: {session_id}")
    if created.get("work_mode") != "code":
        raise RuntimeError(f"session work mode mismatch: {session_id}")
    print(f"SESSION_READY={session_id}")


def main() -> int:
    args = _parser().parse_args()
    if not args.session_id.startswith("sess_"):
        raise RuntimeError("session ID must be a persisted product Session label")
    if not args.project_id.startswith("proj_"):
        raise RuntimeError("project ID must be a registered product Project label")
    if not args.title.strip() or not args.model.strip():
        raise RuntimeError("session title and model must be non-empty")
    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        raise RuntimeError(f"project directory does not exist: {project_dir}")
    _create(
        session_id=args.session_id,
        title=args.title,
        model=args.model,
        project_id=args.project_id,
        project_dir=project_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
