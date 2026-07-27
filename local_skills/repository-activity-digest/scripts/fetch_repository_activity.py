#!/usr/bin/env python3
"""Fetch evidence for multi-window GitHub project intelligence."""

from __future__ import annotations

import argparse
import json
import os
import re
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
_BODY_LIMIT = 2000
_COMMENT_LIMIT = 1200


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


def _read_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_state(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


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
    return {
        "kind": "pull_request" if is_pr else "issue",
        "number": int(item.get("number") or 0),
        "title": str(item.get("title") or "").strip(),
        "url": str(item.get("html_url") or "").strip(),
        "state": str(item.get("state") or "").strip(),
        "state_reason": str(item.get("state_reason") or "").strip(),
        "author": _login(item.get("user")),
        "author_association": str(item.get("author_association") or ""),
        "labels": labels,
        "comments": int(item.get("comments") or 0),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "closed_at": str(item.get("closed_at") or ""),
        "activity_at": str(activity_at or ""),
        "body_excerpt": _excerpt(item.get("body"), _BODY_LIMIT),
        "draft": bool(item["draft"]) if "draft" in item else None,
    }


def _compact_issue_event(item: dict[str, Any]) -> dict[str, Any]:
    issue = item.get("issue") if isinstance(item.get("issue"), dict) else {}
    label = item.get("label") if isinstance(item.get("label"), dict) else {}
    rename = item.get("rename") if isinstance(item.get("rename"), dict) else {}
    return {
        "id": int(item.get("id") or 0),
        "event": str(item.get("event") or ""),
        "created_at": str(item.get("created_at") or ""),
        "actor": _login(item.get("actor")),
        "commit_id": str(item.get("commit_id") or ""),
        "commit_url": str(item.get("commit_url") or ""),
        "issue_kind": (
            "pull_request" if isinstance(issue.get("pull_request"), dict) else "issue"
        ),
        "number": int(issue.get("number") or 0),
        "title": str(issue.get("title") or ""),
        "url": str(issue.get("html_url") or ""),
        "label": str(label.get("name") or ""),
        "assignee": _login(item.get("assignee")),
        "requested_reviewer": _login(item.get("requested_reviewer")),
        "rename": {
            "from": str(rename.get("from") or ""),
            "to": str(rename.get("to") or ""),
        },
    }


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
    return {
        "id": str(item.get("id") or ""),
        "type": str(item.get("type") or ""),
        "action": str(payload.get("action") or ""),
        "created_at": str(item.get("created_at") or ""),
        "actor": _login(item.get("actor")),
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
    }


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
    return {
        "sha": str(item.get("sha") or ""),
        "title": message.splitlines()[0] if message else "",
        "message_excerpt": _excerpt(message, _BODY_LIMIT),
        "url": str(item.get("html_url") or ""),
        "author": _login(item.get("author")) or str(author.get("name") or ""),
        "committer": _login(item.get("committer")) or str(committer.get("name") or ""),
        "committed_at": str(committer.get("date") or author.get("date") or ""),
        "is_merge": len(parents) > 1,
        "is_revert": bool(re.match(r"(?i)^revert\b", message)),
        "parent_count": len(parents),
    }


def _compact_release(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item.get("id") or 0),
        "tag": str(item.get("tag_name") or ""),
        "name": str(item.get("name") or ""),
        "url": str(item.get("html_url") or ""),
        "author": _login(item.get("author")),
        "draft": bool(item.get("draft")),
        "prerelease": bool(item.get("prerelease")),
        "created_at": str(item.get("created_at") or ""),
        "published_at": str(item.get("published_at") or ""),
        "body_excerpt": _excerpt(item.get("body"), _BODY_LIMIT),
    }


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
    return {
        "kind": kind,
        "id": int(item.get("id") or 0),
        "url": str(item.get("html_url") or ""),
        "author": _login(item.get("user")),
        "author_association": str(item.get("author_association") or ""),
        "created_at": str(item.get("created_at") or ""),
        "updated_at": str(item.get("updated_at") or ""),
        "path": str(item.get("path") or ""),
        "line": item.get("line") or item.get("original_line"),
        "body_excerpt": _excerpt(item.get("body"), _COMMENT_LIMIT),
    }


def _compact_review(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(item.get("id") or 0),
        "url": str(item.get("html_url") or ""),
        "author": _login(item.get("user")),
        "author_association": str(item.get("author_association") or ""),
        "state": str(item.get("state") or ""),
        "submitted_at": str(item.get("submitted_at") or ""),
        "commit_id": str(item.get("commit_id") or ""),
        "body_excerpt": _excerpt(item.get("body"), _COMMENT_LIMIT),
    }


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
                    "blob_url": str(file.get("blob_url") or ""),
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
            commit["is_revert"] and _is_in_window(commit["committed_at"], start, end)
            for commit in commits
        ),
        "releases": sum(
            _is_in_window(
                release["published_at"] or release["created_at"],
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
    print("self-test: ok")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", help="GitHub repository in owner/name form")
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--history-days", type=float, default=30.0)
    parser.add_argument("--mode", choices=("created", "updated"), default="updated")
    parser.add_argument("--until", help="UTC ISO-8601 end time; defaults to now")
    parser.add_argument("--state-file", type=Path)
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
    state = _read_state(args.state_file)
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
        "trend_context": {
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
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")

    if args.state_file is not None:
        new_seen = list(seen)
        new_seen.extend(
            keys_items
            + keys_issue_events
            + keys_repo_events
            + keys_commits
            + keys_releases
        )
        _write_state(
            args.state_file,
            {
                "last_success_utc": _format_utc(end),
                "seen": new_seen[-10000:],
            },
        )
    return 0


if __name__ == "__main__":
    _configure_utf8_stdio()
    try:
        raise SystemExit(main())
    except (RuntimeError, ValueError) as exc:
        json.dump({"ok": False, "error": str(exc)}, sys.stderr, ensure_ascii=False)
        sys.stderr.write("\n")
        raise SystemExit(1) from exc
