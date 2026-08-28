#!/usr/bin/env python3
"""Run a digest as two subcommands over one path: the state file.

    digest.py fetch  --repo owner/name --state-file <path> [fetch options]
    digest.py render --state-file <path> [--check-language] --findings - <<'JSON'
    { … }
    JSON

Both halves of the run are anchored to the same string, and it is the one string
the caller was given rather than one it read back out of output. That is the
whole purpose of this file. The render step used to name the run directory, the
activity file and the findings file, each an absolute path around a hundred
characters, copied by hand from the fetch's own stdout; and a path copied by hand
is a path that can lose a character. The resulting command does not fail
politely. It fails for a reason nothing in it shows, looks correct on inspection,
gets reissued unchanged, and the reissue is what ends the run -- while a mistyped
directory near the caller's home has meanwhile been created rather than refused.

Deriving instead of copying removes that surface: the run directory is a
function of the state file, so ``render`` recomputes what ``fetch`` computed and
neither of them has a path of its own to get wrong.

Nothing here is new behaviour. ``fetch`` is ``fetch_repository_activity.py`` and
``render`` is ``render_report.py``, both still runnable directly and still
accepting every option they did, including ``--run-dir``, ``--activity`` and
``--findings``. This file only removes the need to name them.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

_HERE = Path(__file__).resolve().parent
_COMMANDS = ("fetch", "render")


def _sibling(name: str) -> ModuleType:
    """Load a sibling script as a module, by path rather than by import name.

    The scripts directory is not a package and is not on ``sys.path`` when this
    file is run as a script, which is how it is always run.
    """
    path = _HERE / name
    spec = importlib.util.spec_from_file_location(f"_digest_{path.stem}", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"{name} could not be loaded from this Skill's scripts")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _take_option(argv: list[str], name: str) -> str | None:
    """Remove ``--name value`` (or ``--name=value``) from argv and return the value."""
    value: str | None = None
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == name:
            if index + 1 >= len(argv):
                raise RuntimeError(f"{name} needs a value")
            value = argv[index + 1]
            index += 2
            continue
        if item.startswith(f"{name}="):
            value = item.split("=", 1)[1]
            index += 1
            continue
        remaining.append(item)
        index += 1
    argv[:] = remaining
    return value


def _fetch(argv: list[str]) -> int:
    fetcher = _sibling("fetch_repository_activity.py")
    previous = sys.argv
    sys.argv = ["fetch_repository_activity.py", *argv]
    try:
        return int(fetcher.main())
    finally:
        sys.argv = previous


def _render(argv: list[str]) -> int:
    """Turn ``--state-file`` into the run directory the fetch already derived."""
    rest = list(argv)
    state_file = _take_option(rest, "--state-file")
    given_run_dir = any(
        item == "--run-dir" or item.startswith("--run-dir=") for item in rest
    )
    if state_file is not None and not given_run_dir:
        fetcher = _sibling("fetch_repository_activity.py")
        anchor = fetcher._resolve_output_path(Path(state_file))
        if anchor is None:  # pragma: no cover - _take_option returned a string
            raise RuntimeError("--state-file needs a value")
        run_dir = fetcher.run_dir_for(anchor)
        if not run_dir.is_dir():
            print(
                f"render failed: no run directory for that state file "
                f"({run_dir.name}). The fetch creates it, so run "
                "`digest.py fetch` first, or point --run-dir at an existing one.",
                file=sys.stderr,
            )
            return 2
        rest = ["--run-dir", str(run_dir), *rest]
    renderer = _sibling("render_report.py")
    return int(renderer.main(rest))


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0 if arguments else 2
    command, rest = arguments[0], arguments[1:]
    if command not in _COMMANDS:
        print(
            f"digest.py: unknown command {command!r}. "
            f"Expected one of: {', '.join(_COMMANDS)}.",
            file=sys.stderr,
        )
        return 2
    return _fetch(rest) if command == "fetch" else _render(rest)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except AttributeError:  # pragma: no cover - very old interpreters
        pass
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stderr, ensure_ascii=False)
        sys.stderr.write("\n")
        raise SystemExit(1) from exc
