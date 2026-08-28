#!/usr/bin/env python3
"""Fetch evidence for multi-window GitHub project intelligence."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import statistics
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

_USER_AGENT = "jiuwenswarm-repository-activity-digest/2.0"
_API_VERSION = "2022-11-28"
_BODY_LIMIT = 400
_COMMENT_LIMIT = 300
_SUMMARY_LIMIT = 8
_SUMMARY_EXCERPT_LIMIT = 120
_MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})

# Which issue events are worth naming individually rather than counting.
_NOTABLE_EVENTS = frozenset(
    {"closed", "reopened", "merged", "referenced", "review_requested"}
)

# The keys ``_augment_payload`` adds. They are excluded when it recounts, so
# running it over an already-augmented payload gives the same answer as running
# it over a fresh one -- a count of the counts is not a count of anything.
_DERIVED_DAILY_KEYS = frozenset(
    {"counts", "issue_event_counts", "repository_event_counts", "notable_events"}
)
_DERIVED_TREND_KEYS = frozenset(
    {
        "record_counts",
        "open_items",
        "top_labels",
        "top_item_authors",
        "top_commit_authors",
        "most_discussed",
        "revert_commits",
        "merge_commits",
    }
)

# The only keys stdout carries that the raw file does not, and each describes
# the summary rather than the run. Everything else stdout names is written to
# the raw file under the same name and the same nesting, because the summary is
# what gets read and the raw file is what gets filtered afterwards: a name that
# exists in one and not the other produces a filter that matches nothing,
# returns an empty result, and exits 0 with no error to read.
_SUMMARY_ONLY_KEYS = frozenset(
    {"summary_format", "notes", "template", "paths.raw_output_bytes"}
)


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return _parse_utc(value)
    except ValueError:
        return None


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _excerpt(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _login(value: Any) -> str:
    return str(value.get("login") or "") if isinstance(value, dict) else ""


def _with_optional(record: dict[str, Any], optional: dict[str, Any]) -> dict[str, Any]:
    """Add only the optional fields that carry a value.

    Every record is repeated up to a thousand times per run, so a key that is
    almost always empty costs more than it explains.
    """
    record.update({key: value for key, value in optional.items() if value})
    return record


def _runtime_data_dir() -> Path:
    """Return the runtime data root that owns the agent workspace.

    Mirrors the runtime's own resolution order: the ``JIUWENSWARM_DATA_DIR``
    environment variable when it names an absolute directory, otherwise the
    default data root under the user's home directory.
    """
    configured = os.environ.get("JIUWENSWARM_DATA_DIR", "").strip()
    if configured:
        candidate = Path(os.path.expanduser(configured))
        if candidate.is_absolute():
            return candidate
    return Path.home() / ".jiuwenswarm"


def _relative_path_base() -> Path:
    """Return the directory that relative output paths are anchored to.

    Scheduled runs and manual runs start in different working directories, so
    anchoring to the working directory makes one relative path name several
    different files. The default project workspace is a stable anchor that both
    kinds of run agree on.
    """
    return _runtime_data_dir() / "agent" / "workspace" / "projects"


def _resolve_output_path(value: Path | None) -> Path | None:
    """Resolve a path argument to an absolute path independent of the cwd."""
    if value is None:
        return None
    path = Path(os.path.expanduser(str(value)))
    if not path.is_absolute():
        path = _relative_path_base() / path
    return path.resolve()


def names_held_open_in(directory: Path) -> list[str]:
    """Entries under ``directory`` that some still-running process holds open.

    This is the exact condition under which emptying the directory would destroy
    a write that has not finished, and it is deliberately not a timestamp
    comparison. A file left behind by a run that ended a second ago is still a
    leftover and still has to go; a file a concurrent redirect created is held
    open for as long as the write lasts. Only the open descriptor separates the
    two, so only the open descriptor is consulted.

    What it catches is a command line that empties the directory and writes into
    it at the same time::

        <the command below> ... | some-filter > <run directory>/extract.json

    The shell creates ``extract.json`` while it is setting the pipeline up,
    before this program has run a line. This program then deletes the directory
    underneath it. The filter's output lands, seconds later, in a file that no
    longer has a name, so nothing reports an error and the run only finds out
    much later, when reading the file back says it does not exist.

    Best effort by construction: ``/proc`` where there is one, this process's own
    streams where there is not. A miss leaves the previous behaviour rather than
    a worse one.
    """
    prefix = f"{directory}{os.sep}"

    def entry_name(target: str) -> str | None:
        # A file whose name is already gone reads back as "<path> (deleted)".
        if target.endswith(" (deleted)"):
            target = target[: -len(" (deleted)")]
        if not target.startswith(prefix):
            return None
        return target[len(prefix) :].split(os.sep, 1)[0] or None

    try:
        processes = [item for item in Path("/proc").iterdir() if item.name.isdigit()]
    except OSError:
        processes = []
    held: set[str] = set()
    for process in processes:
        try:
            descriptors = list((process / "fd").iterdir())
        except OSError:
            # Exited between the two calls, or belongs to another user. Neither
            # is this run's business and neither is worth failing over.
            continue
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            name = entry_name(target)
            if name is not None:
                held.add(name)
    if not processes:
        # No /proc to read. This process's own streams are still checkable, and
        # a command whose own stdout was redirected into the directory it is
        # about to empty is the simplest form of the same mistake.
        for stream in (sys.stdout, sys.stderr):
            try:
                status = os.fstat(stream.fileno())
                children = list(directory.iterdir())
            except (AttributeError, OSError, ValueError):
                continue
            for child in children:
                try:
                    if os.path.samestat(status, child.stat()):
                        held.add(child.name)
                except OSError:
                    continue
    return sorted(held)


def run_dir_for(anchor: Path) -> Path:
    """Return the run directory a state file (or a raw-output file) implies.

    Public because it is the whole reason a later step needs no path of its own:
    the state file is the one string the prompt supplies, so anything derived
    from it can be recomputed instead of copied.
    """
    return anchor.parent / f"{anchor.stem}.run"


def _prepare_run_dir(state_path: Path | None, raw_path: Path) -> Path:
    """Return this run's scratch directory, derived so any step can re-derive it.

    Shell state does not survive between one command and the next, so a random
    `mktemp -d` directory is unrecoverable the moment the command that made it
    returns. Deriving the path from the state file instead keeps it stable for
    the whole run, distinct per caller, and outside the working directory.

    It is cleared on entry rather than on exit. A run that fails never reaches a
    cleanup step, and leftover working files are precisely what a later run
    finds and follows instead of its own workflow.

    Clearing on entry is kept exactly as it was, and made safe by refusing
    instead of clearing when the directory is being written to at that moment.
    A leftover is still deleted -- that property is what the timing of the clear
    is for -- and the one case that used to be destroyed silently now stops the
    run with something to act on.
    """
    anchor = state_path if state_path is not None else raw_path
    run_dir = run_dir_for(anchor)
    if run_dir.is_dir():
        held = names_held_open_in(run_dir)
        if held:
            raise SystemExit(
                f"the run directory is being written to right now: {run_dir}\n"
                f"Held open by a command that is still running: "
                f"{', '.join(held)}.\n"
                "\n"
                "The fetch empties that directory as its first action, so "
                "anything a redirect on the same command line writes there is "
                "deleted while it is still being written. That is why the file "
                "cannot be found afterwards, and why issuing the same command "
                "line again cannot help.\n"
                "\n"
                "Run the fetch on its own instead: no pipe into another "
                "program, and no `>` into the run directory. Its stdout is the "
                "finished summary and the whole answer -- nothing has to be "
                "extracted from it, parsed out of it or saved out of it -- and "
                "the same document is written to summary.json inside the run "
                "directory for a later step to read. Working files of your own "
                "belong there only after the fetch has returned."
            )
        shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    # Record where this run's raw output lives, so a later step can reach it
    # from the run directory alone. Every long absolute path a step has to
    # reproduce by hand is one it can mistype, and a mistyped path produces a
    # command that fails, gets retried unchanged, and takes the run with it.
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "raw_output": str(raw_path),
                "summary": str(run_dir / "summary.json"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


def _read_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, data: Any, *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=sort_keys)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def _write_state(path: Path, data: dict[str, Any]) -> None:
    _write_json_file(path, data, sort_keys=True)


def _request_json(url: str, token: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
        "X-GitHub-Api-Version": _API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API request failed: {exc.reason}") from exc


def _repo_url(api_base: str, repo: str, path: str, query: dict[str, Any]) -> str:
    encoded_repo = "/".join(
        urllib.parse.quote(part, safe="") for part in repo.split("/")
    )
    encoded_query = urllib.parse.urlencode(query)
    base = f"{api_base.rstrip('/')}/repos/{encoded_repo}/{path.lstrip('/')}"
    return f"{base}?{encoded_query}" if encoded_query else base


def _fetch_pages(
    *,
    api_base: str,
    repo: str,
    path: str,
    query: dict[str, Any],
    token: str,
    max_pages: int,
    start: datetime | None,
    timestamp: Callable[[dict[str, Any]], datetime | None],
    warnings: list[str],
    required: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    results: list[dict[str, Any]] = []
    pages = 0
    reached_start = start is None
    for page in range(1, max_pages + 1):
        page_query = {**query, "per_page": 100, "page": page}
        try:
            payload = _request_json(
                _repo_url(api_base, repo, path, page_query),
                token,
            )
        except RuntimeError as exc:
            if required:
                raise
            warnings.append(f"{path}: {exc}")
            break
        if not isinstance(payload, list):
            message = f"{path}: unexpected non-list response"
            if required:
                raise RuntimeError(message)
            warnings.append(message)
            break
        page_items = [item for item in payload if isinstance(item, dict)]
        if not page_items:
            reached_start = True
            break
        pages += 1
        results.extend(page_items)
        times = [item_time for item in page_items if (item_time := timestamp(item))]
        if start is not None and times and min(times) < start:
            reached_start = True
            break
        if len(page_items) < 100:
            reached_start = True
            break
    if start is not None and pages == max_pages and not reached_start:
        warnings.append(
            f"{path}: pagination stopped at {max_pages} pages before the "
            "requested history boundary"
        )
    return results, pages


def _compact_issue(item: dict[str, Any], mode: str) -> dict[str, Any]:
    raw_labels = item.get("labels")
    labels = [
        str(label.get("name"))
        for label in (raw_labels if isinstance(raw_labels, list) else [])
        if isinstance(label, dict) and label.get("name")
    ]
    is_pr = isinstance(item.get("pull_request"), dict)
    activity_at = item.get("created_at" if mode == "created" else "updated_at")
    return _with_optional(
        {
            "kind": "pull_request" if is_pr else "issue",
            "number": int(item.get("number") or 0),
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("html_url") or "").strip(),
            "state": str(item.get("state") or "").strip(),
            "author": _login(item.get("user")),
            "labels": labels,
            "comments": int(item.get("comments") or 0),
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
            "activity_at": str(activity_at or ""),
        },
        {
            "state_reason": str(item.get("state_reason") or "").strip(),
            "author_association": str(item.get("author_association") or ""),
            "closed_at": str(item.get("closed_at") or ""),
            "body_excerpt": _excerpt(item.get("body"), _BODY_LIMIT),
            "draft": bool(item.get("draft")),
        },
    )


def _compact_issue_event(item: dict[str, Any]) -> dict[str, Any]:
    issue = item.get("issue") if isinstance(item.get("issue"), dict) else {}
    label = item.get("label") if isinstance(item.get("label"), dict) else {}
    return _with_optional(
        {
            "id": int(item.get("id") or 0),
            "event": str(item.get("event") or ""),
            "created_at": str(item.get("created_at") or ""),
            "actor": _login(item.get("actor")),
            "issue_kind": (
                "pull_request"
                if isinstance(issue.get("pull_request"), dict)
                else "issue"
            ),
            "number": int(issue.get("number") or 0),
            "title": str(issue.get("title") or ""),
            "url": str(issue.get("html_url") or ""),
        },
        {
            "commit_id": str(item.get("commit_id") or ""),
            "label": str(label.get("name") or ""),
            "assignee": _login(item.get("assignee")),
            "requested_reviewer": _login(item.get("requested_reviewer")),
        },
    )


def _compact_repo_event(item: dict[str, Any]) -> dict[str, Any]:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    issue = payload.get("issue") if isinstance(payload.get("issue"), dict) else {}
    pull = (
        payload.get("pull_request")
        if isinstance(payload.get("pull_request"), dict)
        else {}
    )
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    release = payload.get("release") if isinstance(payload.get("release"), dict) else {}
    subject = pull or issue
    return _with_optional(
        {
            "id": str(item.get("id") or ""),
            "type": str(item.get("type") or ""),
            "action": str(payload.get("action") or ""),
            "created_at": str(item.get("created_at") or ""),
            "actor": _login(item.get("actor")),
        },
        {
            "number": int(subject.get("number") or 0),
            "title": str(subject.get("title") or ""),
            "url": str(subject.get("html_url") or ""),
            "state": str(subject.get("state") or ""),
            "merged": bool(pull.get("merged")),
            "review_state": str(review.get("state") or ""),
            "review_url": str(review.get("html_url") or ""),
            "review_body_excerpt": _excerpt(review.get("body"), _COMMENT_LIMIT),
            "release_name": str(release.get("name") or release.get("tag_name") or ""),
            "release_url": str(release.get("html_url") or ""),
            "ref": str(payload.get("ref") or ""),
            "push_size": int(payload.get("size") or 0),
        },
    )


def _commit_time(item: dict[str, Any]) -> datetime | None:
    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
    committer = (
        commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
    )
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    return _optional_utc(committer.get("date") or author.get("date"))


def _compact_commit(item: dict[str, Any]) -> dict[str, Any]:
    commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
    author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
    committer = (
        commit.get("committer") if isinstance(commit.get("committer"), dict) else {}
    )
    message = str(commit.get("message") or "").strip()
    parents = item.get("parents") if isinstance(item.get("parents"), list) else []
    title = message.splitlines()[0] if message else ""
    body_excerpt = _excerpt(message, _BODY_LIMIT)
    return _with_optional(
        {
            "sha": str(item.get("sha") or ""),
            "title": title,
            "url": str(item.get("html_url") or ""),
            "author": _login(item.get("author")) or str(author.get("name") or ""),
            "committed_at": str(committer.get("date") or author.get("date") or ""),
        },
        {
            "committer": (
                _login(item.get("committer")) or str(committer.get("name") or "")
            ),
            "message_excerpt": body_excerpt if body_excerpt != title else "",
            "is_merge": len(parents) > 1,
            "is_revert": bool(re.match(r"(?i)^revert\b", message)),
        },
    )


def _compact_release(item: dict[str, Any]) -> dict[str, Any]:
    return _with_optional(
        {
            "id": int(item.get("id") or 0),
            "tag": str(item.get("tag_name") or ""),
            "name": str(item.get("name") or ""),
            "url": str(item.get("html_url") or ""),
            "author": _login(item.get("author")),
            "created_at": str(item.get("created_at") or ""),
            "published_at": str(item.get("published_at") or ""),
        },
        {
            "draft": bool(item.get("draft")),
            "prerelease": bool(item.get("prerelease")),
            "body_excerpt": _excerpt(item.get("body"), _BODY_LIMIT),
        },
    )


def _optional_list(
    *,
    api_base: str,
    repo: str,
    path: str,
    token: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    try:
        payload = _request_json(
            _repo_url(api_base, repo, path, {"per_page": 100}),
            token,
        )
    except RuntimeError as exc:
        warnings.append(f"{path}: {exc}")
        return []
    if not isinstance(payload, list):
        warnings.append(f"{path}: unexpected non-list response")
        return []
    records = [item for item in payload if isinstance(item, dict)]
    if len(records) == 100:
        warnings.append(f"{path}: detail sample may be truncated at 100 records")
    return records


def _compact_comment(item: dict[str, Any], kind: str) -> dict[str, Any]:
    return _with_optional(
        {
            "kind": kind,
            "url": str(item.get("html_url") or ""),
            "author": _login(item.get("user")),
            "created_at": str(item.get("created_at") or ""),
        },
        {
            "author_association": str(item.get("author_association") or ""),
            "path": str(item.get("path") or ""),
            "line": item.get("line") or item.get("original_line"),
            "body_excerpt": _excerpt(item.get("body"), _COMMENT_LIMIT),
        },
    )


def _compact_review(item: dict[str, Any]) -> dict[str, Any]:
    return _with_optional(
        {
            "url": str(item.get("html_url") or ""),
            "author": _login(item.get("user")),
            "state": str(item.get("state") or ""),
            "submitted_at": str(item.get("submitted_at") or ""),
        },
        {
            "author_association": str(item.get("author_association") or ""),
            "body_excerpt": _excerpt(item.get("body"), _COMMENT_LIMIT),
        },
    )


def _fetch_item_details(
    *,
    item: dict[str, Any],
    api_base: str,
    repo: str,
    token: str,
    warnings: list[str],
) -> dict[str, Any]:
    number = int(item["number"])
    issue_comments = _optional_list(
        api_base=api_base,
        repo=repo,
        path=f"issues/{number}/comments",
        token=token,
        warnings=warnings,
    )
    details: dict[str, Any] = {
        "issue_comments": [
            _compact_comment(comment, "issue_comment") for comment in issue_comments
        ]
    }
    if item["kind"] != "pull_request":
        return details

    try:
        pull = _request_json(
            _repo_url(api_base, repo, f"pulls/{number}", {}),
            token,
        )
    except RuntimeError as exc:
        warnings.append(f"pulls/{number}: {exc}")
        return details
    if not isinstance(pull, dict):
        warnings.append(f"pulls/{number}: unexpected non-object response")
        return details

    reviews = _optional_list(
        api_base=api_base,
        repo=repo,
        path=f"pulls/{number}/reviews",
        token=token,
        warnings=warnings,
    )
    review_comments = _optional_list(
        api_base=api_base,
        repo=repo,
        path=f"pulls/{number}/comments",
        token=token,
        warnings=warnings,
    )
    files = _optional_list(
        api_base=api_base,
        repo=repo,
        path=f"pulls/{number}/files",
        token=token,
        warnings=warnings,
    )
    head = pull.get("head") if isinstance(pull.get("head"), dict) else {}
    check_runs: list[dict[str, Any]] = []
    head_sha = str(head.get("sha") or "")
    if head_sha:
        try:
            checks = _request_json(
                _repo_url(
                    api_base,
                    repo,
                    f"commits/{urllib.parse.quote(head_sha, safe='')}/check-runs",
                    {"per_page": 100},
                ),
                token,
            )
            if isinstance(checks, dict) and isinstance(checks.get("check_runs"), list):
                check_runs = [
                    {
                        "name": str(check.get("name") or ""),
                        "status": str(check.get("status") or ""),
                        "conclusion": str(check.get("conclusion") or ""),
                        "url": str(check.get("html_url") or ""),
                        "started_at": str(check.get("started_at") or ""),
                        "completed_at": str(check.get("completed_at") or ""),
                    }
                    for check in checks["check_runs"]
                    if isinstance(check, dict)
                ]
        except RuntimeError as exc:
            warnings.append(f"commits/{head_sha}/check-runs: {exc}")

    base = pull.get("base") if isinstance(pull.get("base"), dict) else {}
    raw_requested_reviewers = pull.get("requested_reviewers")
    compact_reviews = [_compact_review(review) for review in reviews]
    submitted = [
        value
        for review in compact_reviews
        if (value := _optional_utc(review["submitted_at"]))
    ]
    details.update(
        {
            "merged": bool(pull.get("merged")),
            "merged_at": str(pull.get("merged_at") or ""),
            "merge_commit_sha": str(pull.get("merge_commit_sha") or ""),
            "mergeable_state": str(pull.get("mergeable_state") or ""),
            "draft": bool(pull.get("draft")),
            "additions": int(pull.get("additions") or 0),
            "deletions": int(pull.get("deletions") or 0),
            "changed_files": int(pull.get("changed_files") or 0),
            "commit_count": int(pull.get("commits") or 0),
            "review_comment_count": int(pull.get("review_comments") or 0),
            "base_ref": str(base.get("ref") or ""),
            "head_ref": str(head.get("ref") or ""),
            "head_sha": head_sha,
            "requested_reviewers": [
                _login(reviewer)
                for reviewer in (
                    raw_requested_reviewers
                    if isinstance(raw_requested_reviewers, list)
                    else []
                )
                if isinstance(reviewer, dict)
            ],
            "reviews": compact_reviews,
            "first_review_at": _format_utc(min(submitted)) if submitted else "",
            "review_comments": [
                _compact_comment(comment, "review_comment")
                for comment in review_comments
            ],
            "files": [
                {
                    "filename": str(file.get("filename") or ""),
                    "status": str(file.get("status") or ""),
                    "additions": int(file.get("additions") or 0),
                    "deletions": int(file.get("deletions") or 0),
                    "changes": int(file.get("changes") or 0),
                }
                for file in files
            ],
            "check_runs": check_runs,
        }
    )
    return details


def _is_in_window(value: Any, start: datetime, end: datetime) -> bool:
    parsed = _optional_utc(value)
    return parsed is not None and start <= parsed <= end


def _window_counts(
    *,
    start: datetime,
    end: datetime,
    items: list[dict[str, Any]],
    issue_events: list[dict[str, Any]],
    repo_events: list[dict[str, Any]],
    commits: list[dict[str, Any]],
    releases: list[dict[str, Any]],
) -> dict[str, Any]:
    event_counts = Counter(
        event["event"]
        for event in issue_events
        if _is_in_window(event["created_at"], start, end)
    )
    repo_event_counts = Counter(
        event["type"]
        for event in repo_events
        if _is_in_window(event["created_at"], start, end)
    )
    return {
        "issues_created": sum(
            item["kind"] == "issue" and _is_in_window(item["created_at"], start, end)
            for item in items
        ),
        "issues_updated": sum(
            item["kind"] == "issue" and _is_in_window(item["updated_at"], start, end)
            for item in items
        ),
        "pull_requests_created": sum(
            item["kind"] == "pull_request"
            and _is_in_window(item["created_at"], start, end)
            for item in items
        ),
        "pull_requests_updated": sum(
            item["kind"] == "pull_request"
            and _is_in_window(item["updated_at"], start, end)
            for item in items
        ),
        "closed_events": event_counts["closed"],
        "reopened_events": event_counts["reopened"],
        "merged_events": event_counts["merged"],
        "review_events": repo_event_counts["PullRequestReviewEvent"],
        "commits": sum(
            _is_in_window(commit["committed_at"], start, end) for commit in commits
        ),
        "revert_commits": sum(
            bool(commit.get("is_revert"))
            and _is_in_window(commit["committed_at"], start, end)
            for commit in commits
        ),
        "releases": sum(
            _is_in_window(
                release.get("published_at") or release.get("created_at"),
                start,
                end,
            )
            for release in releases
        ),
        "issue_event_types": dict(event_counts.most_common()),
        "repository_event_types": dict(repo_event_counts.most_common()),
    }


def _health_samples(items: list[dict[str, Any]]) -> dict[str, Any]:
    review_hours: list[float] = []
    merge_hours: list[float] = []
    files: Counter[str] = Counter()
    contributors: Counter[str] = Counter()
    detailed_prs = 0
    for item in items:
        if item["author"]:
            contributors[item["author"]] += 1
        details = item.get("details")
        if item["kind"] != "pull_request" or not isinstance(details, dict):
            continue
        detailed_prs += 1
        created = _optional_utc(item["created_at"])
        first_review = _optional_utc(details.get("first_review_at"))
        merged = _optional_utc(details.get("merged_at"))
        if created and first_review and first_review >= created:
            review_hours.append((first_review - created).total_seconds() / 3600)
        if created and merged and merged >= created:
            merge_hours.append((merged - created).total_seconds() / 3600)
        for file in details.get("files", []):
            if isinstance(file, dict) and file.get("filename"):
                files[str(file["filename"])] += 1
        for review in details.get("reviews", []):
            if isinstance(review, dict) and review.get("author"):
                contributors[str(review["author"])] += 1

    def sample(values: list[float]) -> dict[str, Any]:
        return {
            "sample_size": len(values),
            "median_hours": round(statistics.median(values), 2) if values else None,
        }

    return {
        "detailed_pull_request_sample_size": detailed_prs,
        "first_review_time": sample(review_hours),
        "merge_cycle_time": sample(merge_hours),
        "frequently_changed_files_in_detail_sample": [
            {"path": path, "pull_request_count": count}
            for path, count in files.most_common(20)
        ],
        "active_participants_in_detail_sample": [
            {"login": login, "activity_count": count}
            for login, count in contributors.most_common(20)
        ],
    }


def _fresh_records(
    records: list[dict[str, Any]],
    *,
    start: datetime,
    end: datetime,
    seen: set[str],
    key: Callable[[dict[str, Any]], str],
    timestamp: Callable[[dict[str, Any]], Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    fresh: list[dict[str, Any]] = []
    fresh_keys: list[str] = []
    for record in records:
        record_key = key(record)
        if (
            record_key
            and record_key not in seen
            and _is_in_window(timestamp(record), start, end)
        ):
            fresh.append(record)
            fresh_keys.append(record_key)
    return fresh, fresh_keys


def _cap(records: list[Any], limit: int) -> tuple[list[Any], int]:
    """Return at most ``limit`` records together with the full population size."""
    return records[:limit], len(records)


def _summary_item(item: dict[str, Any], excerpt_limit: int) -> dict[str, Any]:
    """Reduce an Issue or pull-request record to the fields a report cites."""
    activity_at = str(item.get("activity_at") or "")
    record: dict[str, Any] = {
        "kind": item.get("kind", ""),
        "number": item.get("number", 0),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "state": item.get("state", ""),
        "author": item.get("author", ""),
        "comments": item.get("comments", 0),
        "created_at": item.get("created_at", ""),
        "activity_at": activity_at,
    }
    labels = [str(label) for label in item.get("labels") or [] if str(label)]
    if labels:
        record["labels"] = ", ".join(labels)
    if item.get("updated_at") and item["updated_at"] != activity_at:
        record["updated_at"] = item["updated_at"]
    for optional in ("state_reason", "closed_at"):
        if item.get(optional):
            record[optional] = item[optional]
    if str(item.get("author_association") or "") in _MAINTAINER_ASSOCIATIONS:
        record["author_association"] = item["author_association"]
    if item.get("draft"):
        record["draft"] = True
    if excerpt_limit > 0:
        excerpt = _excerpt(item.get("body_excerpt"), excerpt_limit)
        if excerpt:
            record["body_excerpt"] = excerpt
    return record


def _summary_reference(item: dict[str, Any]) -> dict[str, Any]:
    """Reduce an item to a citable reference for cross-window signal lists."""
    record = {
        "kind": item.get("kind", ""),
        "number": item.get("number", 0),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "state": item.get("state", ""),
        "comments": item.get("comments", 0),
        "created_at": item.get("created_at", ""),
        "activity_at": item.get("activity_at", ""),
    }
    labels = [str(label) for label in item.get("labels") or [] if str(label)]
    if labels:
        record["labels"] = ", ".join(labels)
    return record


def _summary_commit(commit: dict[str, Any]) -> dict[str, Any]:
    record = {
        "sha": str(commit.get("sha", ""))[:12],
        "title": commit.get("title", ""),
        "url": commit.get("url", ""),
        "author": commit.get("author", ""),
        "committed_at": commit.get("committed_at", ""),
    }
    if commit.get("is_merge"):
        record["is_merge"] = True
    if commit.get("is_revert"):
        record["is_revert"] = True
    return record


def _summary_release(release: dict[str, Any]) -> dict[str, Any]:
    return {
        "tag": release.get("tag", ""),
        "name": release.get("name", ""),
        "url": release.get("url", ""),
        "author": release.get("author", ""),
        "published_at": release.get("published_at") or release.get("created_at", ""),
        "prerelease": bool(release.get("prerelease")),
    }


def _summary_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event": event.get("event") or event.get("type", ""),
        "created_at": event.get("created_at", ""),
        "actor": event.get("actor", ""),
        "number": event.get("number", 0),
        "title": event.get("title", ""),
        "url": event.get("url", ""),
    }


def _rank_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order items so the strongest digest candidates survive truncation."""
    return sorted(
        items,
        key=lambda item: (
            isinstance(item.get("details"), dict),
            int(item.get("comments") or 0),
            str(item.get("activity_at") or ""),
        ),
        reverse=True,
    )


def _summary_highlight(item: dict[str, Any], excerpt_limit: int) -> dict[str, Any]:
    """Condense a fully detailed item into review, CI, and code-change signals."""
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    reviews = [r for r in details.get("reviews") or [] if isinstance(r, dict)]
    checks = [c for c in details.get("check_runs") or [] if isinstance(c, dict)]
    files = [f for f in details.get("files") or [] if isinstance(f, dict)]
    issue_comments = [
        c for c in details.get("issue_comments") or [] if isinstance(c, dict)
    ]
    review_comments = [
        c for c in details.get("review_comments") or [] if isinstance(c, dict)
    ]

    record = _summary_item(item, excerpt_limit)
    record.update(
        {
            "merged": bool(details.get("merged")),
            "additions": details.get("additions", 0),
            "deletions": details.get("deletions", 0),
            "changed_files": details.get("changed_files", 0),
            "commit_count": details.get("commit_count", 0),
            "comment_counts": {
                "issue_comments": len(issue_comments),
                "review_comments": len(review_comments),
            },
        }
    )
    for optional in (
        "merged_at",
        "mergeable_state",
        "first_review_at",
        "base_ref",
        "head_ref",
    ):
        if details.get(optional):
            record[optional] = details[optional]
    if details.get("requested_reviewers"):
        record["requested_reviewers"] = details["requested_reviewers"]
    if reviews:
        record["review_states"] = dict(
            Counter(str(review.get("state") or "") for review in reviews).most_common()
        )
    if checks:
        record["check_conclusions"] = dict(
            Counter(
                str(check.get("conclusion") or check.get("status") or "")
                for check in checks
            ).most_common()
        )
        failing = [
            str(check.get("name") or "")
            for check in checks
            if str(check.get("conclusion") or "")
            in {"failure", "timed_out", "cancelled", "action_required", "stale"}
        ]
        if failing:
            record["failing_checks"] = failing[:10]
    if files:
        top_files = sorted(
            files,
            key=lambda file: int(file.get("changes") or 0),
            reverse=True,
        )[:6]
        record["top_files"] = [
            f"{file.get('filename') or ''} (+/-{int(file.get('changes') or 0)})"
            for file in top_files
        ]
    discussion = sorted(
        issue_comments + review_comments,
        key=lambda comment: str(comment.get("created_at") or ""),
        reverse=True,
    )[:2]
    if discussion:
        record["latest_comments"] = [
            {
                "author": str(comment.get("author") or ""),
                "created_at": str(comment.get("created_at") or ""),
                "excerpt": _excerpt(comment.get("body_excerpt"), excerpt_limit),
            }
            for comment in discussion
        ]
    return record


def _trend_summary(
    trend: dict[str, Any], *, limit: int, excerpt_limit: int
) -> dict[str, Any]:
    """Replace the 30-day record dump with the aggregates a trend table needs."""
    records = {
        key: value
        for key, value in trend.items()
        if key not in _DERIVED_TREND_KEYS and isinstance(value, list)
    }
    issues = [i for i in trend.get("issues") or [] if isinstance(i, dict)]
    pull_requests = [p for p in trend.get("pull_requests") or [] if isinstance(p, dict)]
    commits = [c for c in trend.get("commits") or [] if isinstance(c, dict)]
    releases = [r for r in trend.get("releases") or [] if isinstance(r, dict)]
    tracked = issues + pull_requests

    labels = Counter(
        str(label)
        for item in tracked
        for label in (item.get("labels") or [])
        if str(label)
    )
    authors = Counter(
        str(item.get("author")) for item in tracked if str(item.get("author") or "")
    )
    commit_authors = Counter(
        str(commit.get("author"))
        for commit in commits
        if str(commit.get("author") or "")
    )
    most_discussed = sorted(
        tracked,
        key=lambda item: int(item.get("comments") or 0),
        reverse=True,
    )[:limit]
    reverts = [commit for commit in commits if commit.get("is_revert")][:limit]

    return {
        "record_counts": {key: len(value) for key, value in records.items()},
        "open_items": {
            "issues": sum(item.get("state") == "open" for item in issues),
            "pull_requests": sum(item.get("state") == "open" for item in pull_requests),
        },
        "top_labels": [
            {"label": label, "count": count} for label, count in labels.most_common(15)
        ],
        "top_item_authors": [
            {"login": login, "count": count} for login, count in authors.most_common(10)
        ],
        "top_commit_authors": [
            {"login": login, "count": count}
            for login, count in commit_authors.most_common(10)
        ],
        "most_discussed": [_summary_reference(item) for item in most_discussed],
        "revert_commits": [_summary_commit(commit) for commit in reverts],
        "merge_commits": sum(bool(commit.get("is_merge")) for commit in commits),
        "releases": [_summary_release(release) for release in releases[:limit]],
    }


# Every value in the template carries this. It is the renderer's contract as much
# as this file's: no value carrying it is ever published, so an example can be
# shipped in the material without becoming a finding. ``render_report.py`` holds
# the same constant and a test pins the two together; the two files are edited
# apart, and a marker that drifted would silently turn the examples into
# publishable text.
_FINDINGS_PLACEHOLDER = "PLACEHOLDER-REPLACE-THIS"

# Every field the renderer accepts a fixed set of words for, and the words. Held
# here for the same reason the marker above is: the two files are edited apart
# and neither imports the other, so a test pins this to ``render_report.py``'s
# own ``_SEVERITY_MARKS``, ``_LABELS``, ``_DIRECTION_MARKS`` and ``_CONFIDENCE``.
# That test is the whole of why this copy is allowed to exist. A list that
# drifted would be worse than no list at all: it would teach, in the one artefact
# runs reliably read, a word the renderer then refuses.
#
# It exists because naming the fields was not enough. With every field present
# and one example value each, runs stopped inventing field names and started
# guessing values instead -- `medium` for a severity, from an example reading
# `stable` -- and the renderer, which cannot substitute a rating nobody wrote,
# published the item unrated. One example of a closed set does not show the set.
#
# The words are in the renderer's own order, which is the ranked one everywhere
# it matters, so the list reads as a scale rather than as an alphabetised bag.
_FINDINGS_VOCABULARIES: dict[str, tuple[str, ...]] = {
    "severity": ("critical", "major", "stable"),
    "label": ("fact", "inference", "recommendation"),
    "direction": ("rising", "stable", "cooling"),
    "confidence": ("high", "medium", "low"),
}


def _choices(*fields: str) -> str:
    """Say what the named fields accept, for the example text they sit beside."""
    return "; ".join(
        f"{field} takes one of {', '.join(_FINDINGS_VOCABULARIES[field])}"
        for field in fields
    )


def _vocabularies() -> str:
    """Every closed vocabulary in one line, for the notes beside the template."""
    return "; ".join(
        f"{field}: {', '.join(words)}"
        for field, words in _FINDINGS_VOCABULARIES.items()
    )


def _example(what: str) -> str:
    return f"{_FINDINGS_PLACEHOLDER} — {what}"


def _example_evidence(what: str) -> list[dict[str, str]]:
    return [
        {
            "label": _example(f"a short caption, e.g. {what}"),
            "url": f"https://example.invalid/{_FINDINGS_PLACEHOLDER}",
        }
    ]


def _findings_template() -> dict[str, Any]:
    """Return the exact envelope the renderer accepts, with one example per key.

    It is printed on stdout beside the evidence rather than left to be looked up.
    The dominant render failure was not a wrong value in a right shape: it was an
    invented wrapper around the whole document, rewritten byte-identically on
    every retry because nothing in the error named the shape that was wanted. A
    reference file answers that only for a run that thinks to open it, and a run
    that already believes it knows the format has no reason to. A skeleton in the
    material cannot go unread the same way, and copying it is less work than
    inventing one.

    The examples are here for the second half of that same argument. Empty arrays
    named the eight sections and never named a single field inside one, so a
    writer still had to guess what an item's own keys are called -- and the guess
    was observed live, as a whole invented item vocabulary (`label`, `link`,
    `number`, `state`, `kind`, `author`, `highlights`, `confidence`) spread across
    every section, none of it read and all of it dropped. The runs that got the
    shape right first time were the ones that opened
    ``references/findings-schema.md``, and the ones that failed did not open it at
    all. This template is the artefact they do read, so the field names have to be
    in it.

    Shipping an example is the risk this skill has already paid for once: its
    worst failure was per-theme figures copied out of a template and published as
    measured. An example is therefore only safe if it cannot be published, and
    every value below carries ``_FINDINGS_PLACEHOLDER`` for that reason. The
    renderer drops any finding still holding it and refuses outright if one ever
    reaches the rendered text, so a copied example costs its own item and can
    never cost the reader a false statement.

    The four closed fields are the deliberate exception, and the exception has to
    go this way round. Their example values are real, legal words carrying no
    marker, and the set each belongs to is spelled out in the marked value beside
    it. Marking them instead would force a writer to replace the one thing they
    have no way to guess -- which is the defect this addition exists to close --
    and would cost far more than the rating: ``_holds_placeholder`` reads a whole
    entry, so a marker left on a severity discards the finding around it, turning
    an item published unrated into an item not published at all. Left legal, a
    copied word is a conservative default on an item whose claim its writer did
    write, and the entry is still droppable as a whole, because every entry keeps
    the marker on the prose no copy can leave untouched.
    """
    return {
        "tldr": [
            {
                "severity": "stable",
                "text": _example(
                    "one sentence on what this run found, in the output language"
                    f" ({_choices('severity')})"
                ),
                "original": _example(
                    "the source's own wording, only when the sentence above "
                    "renders it from another language"
                ),
            }
        ],
        "significant_changes": [
            {
                "title": _example("the change, named in a few words"),
                "label": "fact",
                "text": _example(
                    "what changed and why it matters"
                    f" ({_choices('label')})"
                ),
                "original": _example("the source's own wording, when it differs"),
                "evidence": _example_evidence("PR #123"),
            }
        ],
        "risks": [
            {
                "severity": "major",
                "text": _example(
                    "what is at risk, and for whom"
                    f" ({_choices('severity')})"
                ),
                "original": _example("the source's own wording, when it differs"),
                "evidence": _example_evidence("#123"),
            }
        ],
        "actions": [
            {
                "text": _example("one thing to do, stated so it can be done"),
                "original": _example("the source's own wording, when it differs"),
            }
        ],
        "trends": [
            {
                "theme": _example("the theme moving, named in a few words"),
                "direction": "rising",
                "text": _example(
                    "what the movement is, and what it rests on"
                    f" ({_choices('direction', 'confidence')})"
                ),
                "original": _example("the source's own wording, when it differs"),
                "confidence": "medium",
                "evidence": _example_evidence("#123"),
            }
        ],
        "missing_capabilities": {
            "explicit": [
                {
                    "text": _example("a capability the project says it lacks"),
                    "original": _example("the source's own wording, when it differs"),
                }
            ],
            "inferred": [
                {
                    "text": _example(
                        "a capability the evidence implies is missing"
                        f" ({_choices('confidence')})"
                    ),
                    "original": _example("the source's own wording, when it differs"),
                    "confidence": "medium",
                }
            ],
            "insufficient": [
                {
                    "text": _example("a gap the evidence cannot settle either way"),
                    "original": _example("the source's own wording, when it differs"),
                }
            ],
        },
        "opportunities": [
            {
                "title": _example("the opportunity, named in a few words"),
                "kind": _example("its field, e.g. Systems engineering"),
                "user_value": "High",
                "research_value": "Medium",
                "effort": "Medium",
                "risk": "Low",
                "recommendation": _example("what you would do about it"),
            }
        ],
        "evidence_gaps": {
            "known": [
                {
                    "text": _example("something this run could not establish"),
                    "original": _example("the source's own wording, when it differs"),
                }
            ],
            "unknown": [
                {
                    "text": _example("something the material does not cover"),
                    "original": _example("the source's own wording, when it differs"),
                }
            ],
            "needed": [
                {
                    "text": _example("what would have to be read to settle it"),
                    "original": _example("the source's own wording, when it differs"),
                }
            ],
        },
    }


def _augment_payload(
    payload: dict[str, Any], *, limit: int, excerpt_limit: int
) -> dict[str, Any]:
    """Write into the raw payload every field stdout will show, under stdout's names.

    stdout is what gets read; the raw file is what gets filtered afterwards, with
    the names the reader just saw. So the two have to be one schema. Where they
    were not, the failure was silent rather than loud: a filter written against a
    name stdout showed and the raw file did not match nothing, returned an empty
    result, and exited 0. Nothing in that outcome says which half was wrong, so
    there is no error to read and no next command to try -- which is what turns a
    typo-sized mistake into a run that reissues variations until it is killed.

    The raw file stays the superset: it keeps every record, and stdout keeps a
    ranked extract of the same thing under the same key. Returned here are those
    extracts, so the caps and the truncation notice come from one computation
    rather than two that can drift apart.
    """
    daily = payload.get("daily_activity")
    if not isinstance(daily, dict):
        daily = {}
        payload["daily_activity"] = daily
    trend = payload.get("trend")
    if not isinstance(trend, dict):
        trend = {}
        payload["trend"] = trend

    records = {
        key: value
        for key, value in daily.items()
        if key not in _DERIVED_DAILY_KEYS and isinstance(value, list)
    }
    daily_issues = [i for i in records.get("issues") or [] if isinstance(i, dict)]
    daily_pulls = [p for p in records.get("pull_requests") or [] if isinstance(p, dict)]
    daily_commits = [c for c in records.get("commits") or [] if isinstance(c, dict)]
    daily_releases = [r for r in records.get("releases") or [] if isinstance(r, dict)]
    issue_events = [e for e in records.get("issue_events") or [] if isinstance(e, dict)]
    repo_events = [
        e for e in records.get("repository_events") or [] if isinstance(e, dict)
    ]

    shown_issues, total_issues = _cap(_rank_items(daily_issues), limit)
    shown_pulls, total_pulls = _cap(_rank_items(daily_pulls), limit)
    shown_commits, total_commits = _cap(daily_commits, limit)
    notable = [
        event
        for event in issue_events
        if str(event.get("event") or "") in _NOTABLE_EVENTS
    ]
    shown_events, total_events = _cap(notable, limit)

    daily["counts"] = {key: len(value) for key, value in records.items()}
    daily["issue_event_counts"] = dict(
        Counter(str(event.get("event") or "") for event in issue_events).most_common()
    )
    daily["repository_event_counts"] = dict(
        Counter(str(event.get("type") or "") for event in repo_events).most_common()
    )
    daily["notable_events"] = notable

    # Only the aggregates are copied in. ``_trend_summary`` also returns a capped
    # ``releases`` extract, and writing that over the raw file's own release
    # records would shrink the complete structure to the summary's size -- the
    # one direction this unification must never take.
    aggregates = _trend_summary(trend, limit=limit, excerpt_limit=excerpt_limit)
    trend.update(
        {key: value for key, value in aggregates.items() if key in _DERIVED_TREND_KEYS}
    )

    payload["highlights"] = [
        _summary_highlight(item, excerpt_limit)
        for item in daily_pulls + daily_issues
        if isinstance(item.get("details"), dict)
    ]
    # ``truncated`` records what the extract left out. It is derived from the
    # summary's caps but belongs in the raw file too, because the renderer reads
    # it from there and turns it into the report's own truncation lines -- a
    # promise that holds only if the value reaches the reader.
    payload["truncated"] = {
        name: {"shown": len(shown), "total": total}
        for name, shown, total in (
            ("daily_issues", shown_issues, total_issues),
            ("daily_pull_requests", shown_pulls, total_pulls),
            ("daily_commits", shown_commits, total_commits),
            ("daily_notable_events", shown_events, total_events),
        )
        if len(shown) < total
    }

    return {
        "issues": shown_issues,
        "pull_requests": shown_pulls,
        "commits": shown_commits,
        "notable_events": shown_events,
        "releases": daily_releases,
    }


def _build_summary(
    payload: dict[str, Any],
    shown: dict[str, Any],
    *,
    raw_output_bytes: int,
    limit: int,
    excerpt_limit: int,
) -> dict[str, Any]:
    """Build the compact digest input that is written to stdout.

    The full structure is far larger than a model context window, so stdout
    carries only what the report format cites and names the file that holds
    everything else. Every key here is one ``_augment_payload`` has already put
    in the raw file, except the three that describe this summary itself.
    """
    daily = payload.get("daily_activity") or {}
    trend = payload.get("trend") or {}
    health = dict(payload.get("health_samples") or {})
    for key in (
        "frequently_changed_files_in_detail_sample",
        "active_participants_in_detail_sample",
    ):
        if isinstance(health.get(key), list):
            health[key] = health[key][:10]

    summary = {
        "ok": payload.get("ok", True),
        "summary_format": "digest-input/1",
        "repository": payload.get("repository", ""),
        "mode": payload.get("mode", ""),
        "generated_at_utc": payload.get("generated_at_utc", ""),
        "paths": dict(payload.get("paths") or {}),
        "state": payload.get("state") or {},
        "windows": payload.get("windows") or {},
        "coverage": payload.get("coverage") or {},
        "window_counts": payload.get("window_counts") or {},
        "health_samples": health,
        "daily_activity": {
            "counts": daily.get("counts") or {},
            "issues": [
                _summary_item(item, excerpt_limit) for item in shown["issues"]
            ],
            "pull_requests": [
                _summary_item(item, excerpt_limit) for item in shown["pull_requests"]
            ],
            "commits": [_summary_commit(commit) for commit in shown["commits"]],
            "releases": [_summary_release(item) for item in shown["releases"]],
            "issue_event_counts": daily.get("issue_event_counts") or {},
            "repository_event_counts": daily.get("repository_event_counts") or {},
            "notable_events": [
                _summary_event(event) for event in shown["notable_events"]
            ],
        },
        "highlights": payload.get("highlights") or [],
        "trend": {
            **{
                key: value
                for key, value in trend.items()
                if key in _DERIVED_TREND_KEYS
            },
            "releases": [
                _summary_release(release)
                for release in (trend.get("releases") or [])[:limit]
                if isinstance(release, dict)
            ],
        },
        "stale_open_sample": [
            _summary_reference(item)
            for item in (payload.get("stale_open_sample") or [])[:limit]
            if isinstance(item, dict)
        ],
        "truncated": payload.get("truncated") or {},
    }
    summary["paths"]["raw_output_bytes"] = raw_output_bytes
    summary["template"] = _findings_template()
    summary["notes"] = [
        "This document is the answer, not a pointer to one. Nothing has to be "
        "extracted from it, parsed out of it, or saved out of it before it can "
        "be used: read it here, and read paths.summary if it has to be read "
        "again.",
        "This is a summary. paths.raw_output holds the complete structure, "
        "including every record omitted here.",
        "The raw file is far too large to read whole; filter it with a script "
        "instead, and only when this summary is insufficient.",
        "Every key below exists in paths.raw_output under the same name and the "
        "same nesting, so a filter written from what you read here matches "
        "there. Only summary_format, notes, template and paths.raw_output_bytes "
        "are this summary's own.",
        "paths.summary holds this exact document, so a filter can be written "
        "against the file that was read rather than against a memory of it.",
        "Use paths.state_file, paths.raw_output, paths.summary and paths.run_dir "
        "exactly as printed. Do not construct or guess any of them.",
        "paths.run_dir is this run's scratch directory, already created and "
        "emptied. Every working file — findings, filter scripts, the rendered "
        "report — belongs there and nowhere else, and is written by a later "
        "command, after this one has returned.",
        "Never write into paths.run_dir on the same command line as the fetch. "
        "The fetch empties that directory as its first action, so a > redirect "
        "into it — on the fetch itself, or on anything piped from it — makes a "
        "file the fetch deletes while it is still being written. The fetch "
        "refuses such a command line rather than performing it, and the refusal "
        "costs a whole fetch. There is nothing to gain either: what a pipeline "
        "like that reaches for is already here and already in paths.summary. "
        "The files this run writes are the ones named under paths; a name that "
        "is not one of them — a template.json, a raw_data.json, a saved copy of "
        "this output — is a file nothing here produces and nothing here reads. "
        "template and paths are keys of this document: read them where they "
        "are.",
        "template is the whole findings document the renderer accepts: those "
        "keys, at the top level, with nothing wrapped around them. Copy it and "
        "fill it in. A key of your own beside them — a generated_at_utc, a "
        "findings holding the rest — is read as none of the schema, and the "
        "report it renders is missing everything it says. tldr needs at least "
        "one entry. Field meanings are in references/findings-schema.md.",
        f"Four fields take a fixed word and nothing else — {_vocabularies()}. A "
        "word outside one of those lists is not read: the renderer will not "
        "substitute a rating nobody wrote, so it publishes the item without one "
        "and says so under Reporting Shortfalls. The words shown in template are "
        "real rather than marked, so keep the one there or swap it for another "
        "from the same list. No other field is a fixed list: an opportunity's "
        "kind, user_value, research_value, effort and risk are free text, printed "
        "exactly as written and printed as Unknown when unstated, so grade them "
        "from what this run found rather than leaving the example's grades in "
        "place.",
        f"Every item in template is an example, and every value in it carrying "
        f"{_FINDINGS_PLACEHOLDER} is text nobody wrote. The field names around "
        "those values are the "
        "only names the renderer reads — a sentence written as summary, an "
        "evidence url written as link, a theme written as name are all dropped. "
        "Replace each example with what this run found, and delete any example "
        "you did not replace: an item you did not write is not a finding. The "
        "renderer publishes no value still carrying that marker — it drops the "
        "item and says so in the report — so a copied example costs the item, "
        "never the reader.",
        "This summary is evidence, not a draft report. The lists below are "
        "ranked extracts, not the sections of a digest; the report is what "
        "render_report.py returns, and composing one out of these fields "
        "instead produces a differently shaped document on every run.",
    ]
    return summary


def _self_test() -> None:
    sample = {
        "number": 42,
        "title": "Add Slack automation",
        "html_url": "https://github.com/example/repo/pull/42",
        "state": "open",
        "user": {"login": "octocat"},
        "labels": [{"name": "enhancement"}],
        "created_at": "2026-07-25T10:00:00Z",
        "updated_at": "2026-07-25T11:00:00Z",
        "pull_request": {"url": "https://api.github.com/pulls/42"},
        "draft": True,
    }
    compact = _compact_issue(sample, "updated")
    assert compact["kind"] == "pull_request"
    assert compact["number"] == 42
    assert compact["labels"] == ["enhancement"]
    assert compact["activity_at"] == "2026-07-25T11:00:00Z"
    commit = _compact_commit(
        {
            "sha": "abc",
            "html_url": "https://github.com/example/repo/commit/abc",
            "commit": {
                "message": "Revert bad change",
                "author": {"name": "A", "date": "2026-07-25T12:00:00Z"},
                "committer": {"name": "A", "date": "2026-07-25T12:00:00Z"},
            },
            "parents": [{"sha": "parent"}],
        }
    )
    assert commit["is_revert"]

    previous_data_dir = os.environ.get("JIUWENSWARM_DATA_DIR")
    os.environ["JIUWENSWARM_DATA_DIR"] = str(
        Path(tempfile.gettempdir()).resolve() / "repository-activity-self-test"
    )
    try:
        base = _relative_path_base()
        relative = _resolve_output_path(Path("memory/state.json"))
        absolute_input = Path(tempfile.gettempdir()).resolve() / "state.json"
        absolute = _resolve_output_path(absolute_input)
    finally:
        if previous_data_dir is None:
            os.environ.pop("JIUWENSWARM_DATA_DIR", None)
        else:
            os.environ["JIUWENSWARM_DATA_DIR"] = previous_data_dir
    assert relative.is_absolute()
    assert relative == (base / "memory" / "state.json").resolve()
    assert absolute == absolute_input.resolve()
    assert _resolve_output_path(None) is None

    print("self-test: ok")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help="GitHub repository in owner/name form")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--history-days", type=float, default=30.0)
    parser.add_argument("--mode", choices=("created", "updated"), default="updated")
    parser.add_argument("--until", help="UTC ISO-8601 end time; defaults to now")
    parser.add_argument(
        "--state-file",
        type=Path,
        help=(
            "watermark file; a relative path is resolved against the default "
            "project workspace, never against the working directory"
        ),
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        help=(
            "file that receives the complete structure; a relative path is "
            "resolved like --state-file. Defaults to a per-repository file "
            "under the default project workspace."
        ),
    )
    parser.add_argument(
        "--summary-limit",
        type=int,
        default=_SUMMARY_LIMIT,
        help="maximum records per list on stdout; the rest stay in --raw-output",
    )
    parser.add_argument("--api-base", default="https://api.github.com")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--detail-limit", type=int, default=5)
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.self_test:
        _self_test()
        return 0
    if not args.repo or args.repo.count("/") != 1:
        raise SystemExit("--repo must use owner/name format")
    if args.hours <= 0 or args.history_days <= 0:
        raise SystemExit("--hours and --history-days must be positive")
    if args.history_days < 7 or args.history_days * 24 < args.hours:
        raise SystemExit("--history-days must cover at least 7 days and --hours")
    if args.max_pages <= 0 or args.detail_limit < 0:
        raise SystemExit("--max-pages must be positive and --detail-limit non-negative")

    end = _parse_utc(args.until) if args.until else datetime.now(timezone.utc)
    requested_daily_start = end - timedelta(hours=args.hours)
    seven_day_start = end - timedelta(days=7)
    history_start = end - timedelta(days=args.history_days)
    state_path = _resolve_output_path(args.state_file)
    raw_path = _resolve_output_path(
        args.raw_output
        or Path("repository-activity-raw") / f"{args.repo.replace('/', '-')}.json"
    )
    run_dir = _prepare_run_dir(state_path, raw_path)
    state = _read_state(state_path)
    last_success = _optional_utc(state.get("last_success_utc"))
    daily_start = (
        min(requested_daily_start, last_success)
        if last_success
        else requested_daily_start
    )
    seen = {str(item) for item in state.get("seen", []) if isinstance(item, (str, int))}
    token = os.environ.get(args.token_env, "").strip()
    warnings: list[str] = []
    endpoint_pages: dict[str, int] = {}

    issue_query: dict[str, Any] = {
        "state": "all",
        "sort": args.mode,
        "direction": "desc",
    }
    if args.mode == "updated":
        issue_query["since"] = _format_utc(history_start)
    raw_items, endpoint_pages["issues"] = _fetch_pages(
        api_base=args.api_base,
        repo=args.repo,
        path="issues",
        query=issue_query,
        token=token,
        max_pages=args.max_pages,
        start=history_start,
        timestamp=lambda item: _optional_utc(
            item.get("created_at" if args.mode == "created" else "updated_at")
        ),
        warnings=warnings,
        required=True,
    )
    items = [
        _compact_issue(item, args.mode)
        for item in raw_items
        if _is_in_window(
            item.get("created_at" if args.mode == "created" else "updated_at"),
            history_start,
            end,
        )
    ]

    raw_issue_events, endpoint_pages["issue_events"] = _fetch_pages(
        api_base=args.api_base,
        repo=args.repo,
        path="issues/events",
        query={},
        token=token,
        max_pages=args.max_pages,
        start=history_start,
        timestamp=lambda item: _optional_utc(item.get("created_at")),
        warnings=warnings,
    )
    issue_events = [
        _compact_issue_event(item)
        for item in raw_issue_events
        if _is_in_window(item.get("created_at"), history_start, end)
    ]

    raw_repo_events, endpoint_pages["repository_events"] = _fetch_pages(
        api_base=args.api_base,
        repo=args.repo,
        path="events",
        query={},
        token=token,
        max_pages=min(args.max_pages, 3),
        start=history_start,
        timestamp=lambda item: _optional_utc(item.get("created_at")),
        warnings=warnings,
    )
    repo_events = [
        _compact_repo_event(item)
        for item in raw_repo_events
        if _is_in_window(item.get("created_at"), history_start, end)
    ]
    if len(raw_repo_events) >= 300:
        oldest = min(
            (
                value
                for item in raw_repo_events
                if (value := _optional_utc(item.get("created_at")))
            ),
            default=None,
        )
        if oldest and oldest > history_start:
            warnings.append(
                "events: GitHub exposes at most 300 repository events; "
                "the 30-day event history is incomplete"
            )

    raw_commits, endpoint_pages["commits"] = _fetch_pages(
        api_base=args.api_base,
        repo=args.repo,
        path="commits",
        query={
            "since": _format_utc(history_start),
            "until": _format_utc(end),
        },
        token=token,
        max_pages=args.max_pages,
        start=history_start,
        timestamp=_commit_time,
        warnings=warnings,
    )
    commits = [_compact_commit(item) for item in raw_commits]

    raw_releases, endpoint_pages["releases"] = _fetch_pages(
        api_base=args.api_base,
        repo=args.repo,
        path="releases",
        query={},
        token=token,
        max_pages=args.max_pages,
        start=history_start,
        timestamp=lambda item: _optional_utc(
            item.get("published_at") or item.get("created_at")
        ),
        warnings=warnings,
    )
    releases = [
        _compact_release(item)
        for item in raw_releases
        if _is_in_window(
            item.get("published_at") or item.get("created_at"),
            history_start,
            end,
        )
    ]

    stale_raw: list[dict[str, Any]] = []
    try:
        stale_payload = _request_json(
            _repo_url(
                args.api_base,
                args.repo,
                "issues",
                {
                    "state": "open",
                    "sort": "updated",
                    "direction": "asc",
                    "per_page": 30,
                    "page": 1,
                },
            ),
            token,
        )
        if isinstance(stale_payload, list):
            stale_raw = [item for item in stale_payload if isinstance(item, dict)]
        else:
            warnings.append("stale open sample: unexpected non-list response")
    except RuntimeError as exc:
        warnings.append(f"stale open sample: {exc}")
    stale_open_sample = [_compact_issue(item, "updated") for item in stale_raw]

    detail_candidates = sorted(
        (
            item
            for item in items
            if _is_in_window(item["activity_at"], daily_start, end)
        ),
        key=lambda item: item["activity_at"],
        reverse=True,
    )[: args.detail_limit]
    detail_numbers: list[dict[str, Any]] = []
    for item in detail_candidates:
        item["details"] = _fetch_item_details(
            item=item,
            api_base=args.api_base,
            repo=args.repo,
            token=token,
            warnings=warnings,
        )
        detail_numbers.append({"kind": item["kind"], "number": item["number"]})

    fresh_items, keys_items = _fresh_records(
        items,
        start=daily_start,
        end=end,
        seen=seen,
        key=lambda item: f"item:{item['kind']}:{item['number']}:{item['activity_at']}",
        timestamp=lambda item: item["activity_at"],
    )
    fresh_issue_events, keys_issue_events = _fresh_records(
        issue_events,
        start=daily_start,
        end=end,
        seen=seen,
        key=lambda item: f"issue-event:{item['id']}",
        timestamp=lambda item: item["created_at"],
    )
    fresh_repo_events, keys_repo_events = _fresh_records(
        repo_events,
        start=daily_start,
        end=end,
        seen=seen,
        key=lambda item: f"repo-event:{item['id']}",
        timestamp=lambda item: item["created_at"],
    )
    fresh_commits, keys_commits = _fresh_records(
        commits,
        start=daily_start,
        end=end,
        seen=seen,
        key=lambda item: f"commit:{item['sha']}",
        timestamp=lambda item: item["committed_at"],
    )
    fresh_releases, keys_releases = _fresh_records(
        releases,
        start=daily_start,
        end=end,
        seen=seen,
        key=lambda item: f"release:{item['id']}",
        timestamp=lambda item: item["published_at"] or item["created_at"],
    )

    windows = {
        "daily": {
            "requested_hours": args.hours,
            "start_utc": _format_utc(daily_start),
            "end_utc": _format_utc(end),
            "catch_up_from_state": bool(
                last_success and last_success < requested_daily_start
            ),
        },
        "seven_day": {
            "start_utc": _format_utc(seven_day_start),
            "end_utc": _format_utc(end),
        },
        "history": {
            "days": args.history_days,
            "start_utc": _format_utc(history_start),
            "end_utc": _format_utc(end),
        },
    }
    output = {
        "ok": True,
        "repository": args.repo,
        "mode": args.mode,
        "generated_at_utc": _format_utc(end),
        "paths": {
            "raw_output": str(raw_path),
            "summary": str(run_dir / "summary.json"),
            "state_file": str(state_path) if state_path else "",
            "run_dir": str(run_dir),
            "relative_path_base": str(_relative_path_base()),
        },
        "windows": windows,
        "coverage": {
            "github_token_configured": bool(token),
            "endpoint_pages": endpoint_pages,
            "detail_limit": args.detail_limit,
            "detailed_items": detail_numbers,
            "daily_detail_candidates_omitted": max(
                0,
                sum(
                    _is_in_window(item["activity_at"], daily_start, end)
                    for item in items
                )
                - len(detail_candidates),
            ),
            "warnings": warnings,
        },
        "daily_activity": {
            "issues": [item for item in fresh_items if item["kind"] == "issue"],
            "pull_requests": [
                item for item in fresh_items if item["kind"] == "pull_request"
            ],
            "issue_events": fresh_issue_events,
            "repository_events": fresh_repo_events,
            "commits": fresh_commits,
            "releases": fresh_releases,
        },
        "trend": {
            "issues": [item for item in items if item["kind"] == "issue"],
            "pull_requests": [item for item in items if item["kind"] == "pull_request"],
            "issue_events": issue_events,
            "repository_events": repo_events,
            "commits": commits,
            "releases": releases,
        },
        "window_counts": {
            "daily": _window_counts(
                start=requested_daily_start,
                end=end,
                items=items,
                issue_events=issue_events,
                repo_events=repo_events,
                commits=commits,
                releases=releases,
            ),
            "seven_day": _window_counts(
                start=seven_day_start,
                end=end,
                items=items,
                issue_events=issue_events,
                repo_events=repo_events,
                commits=commits,
                releases=releases,
            ),
            "history": _window_counts(
                start=history_start,
                end=end,
                items=items,
                issue_events=issue_events,
                repo_events=repo_events,
                commits=commits,
                releases=releases,
            ),
        },
        "health_samples": _health_samples(items),
        "stale_open_sample": stale_open_sample,
    }
    if state_path is not None:
        new_seen = list(seen)
        new_seen.extend(
            keys_items
            + keys_issue_events
            + keys_repo_events
            + keys_commits
            + keys_releases
        )
        try:
            _write_state(
                state_path,
                {
                    "last_success_utc": _format_utc(end),
                    "seen": new_seen[-10000:],
                },
            )
            state_written = True
        except OSError as exc:
            warnings.append(f"state file: {exc}")
            state_written = False
        output["state"] = {
            "written": state_written,
            "previous_last_success_utc": (
                _format_utc(last_success) if last_success else ""
            ),
            "last_success_utc": _format_utc(end),
            "seen_keys": len(new_seen[-10000:]),
        }
    else:
        output["state"] = {
            "written": False,
            "reason": "no --state-file given; every run reports the full window",
        }

    limit = max(1, args.summary_limit)
    shown = _augment_payload(
        output, limit=limit, excerpt_limit=_SUMMARY_EXCERPT_LIMIT
    )
    _write_json_file(raw_path, output)
    summary = _build_summary(
        output,
        shown,
        raw_output_bytes=raw_path.stat().st_size,
        limit=limit,
        excerpt_limit=_SUMMARY_EXCERPT_LIMIT,
    )
    # The summary is persisted as well as printed. A filter is written against
    # names that were read, and re-reading them from the file that holds them
    # beats reproducing them from the part of stdout still in view.
    try:
        _write_json_file(run_dir / "summary.json", summary)
    except OSError as exc:  # pragma: no cover - defensive
        summary["notes"].append(f"summary file not written: {exc}")
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    _configure_utf8_stdio()
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stderr, ensure_ascii=False)
        sys.stderr.write("\n")
        raise SystemExit(1) from exc
