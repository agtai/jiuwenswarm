"""A digest may only cite links the run actually retrieved.

A run once presented five URLs that appeared in no tool output: titles listed as
plain text on a round-up page were turned into links by guessing that each title
becomes its own slug. Four of the five resolved, because that is how the site
builds URLs, so checking reachability returned OK on them and the digest shipped
citations nobody had opened. One was a hard 404.

Reachability therefore cannot be the only check. `--retrieved` compares each
citation against a record of what the run opened, which is the only signal that
separates a guessed slug from a real link when both resolve. These tests run
with --offline throughout: the provenance verdict must not depend on the
network, and the suite must not reach for it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "local_skills"
    / "ai-news-monitor"
    / "scripts"
    / "check_links.py"
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
def digest(tmp_path: Path) -> Path:
    path = tmp_path / "ai-digest-2026-08-04.md"
    path.write_text(
        "# AI monitor\n\n"
        "[Opened](https://vendor.test/blog/a-post-that-was-read)\n"
        "[Guessed](https://vendor.test/blog/slug-built-from-the-headline)\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def retrieved(tmp_path: Path) -> Path:
    path = tmp_path / "retrieved-urls.txt"
    path.write_text(
        "https://vendor.test/blog/a-post-that-was-read\n"
        "https://vendor.test/blog/something-else-seen-in-the-sweep\n",
        encoding="utf-8",
    )
    return path


def test_unretrieved_url_is_unsourced_and_fails(digest: Path, retrieved: Path) -> None:
    """The fabricated citation fails the run even though nothing is malformed."""
    r = run(str(digest), "--retrieved", str(retrieved), "--offline")

    assert r.returncode == 1
    assert "UNSOURCED" in r.stdout
    assert "slug-built-from-the-headline" in r.stdout
    # The retrieved one must not be swept up with it.
    assert "a-post-that-was-read" not in r.stdout


def test_all_retrieved_urls_pass(tmp_path: Path, retrieved: Path) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text(
        "[Opened](https://vendor.test/blog/a-post-that-was-read)\n", encoding="utf-8"
    )

    r = run(str(clean), "--retrieved", str(retrieved), "--offline")

    assert r.returncode == 0
    assert "UNSOURCED" not in r.stdout


def test_without_the_flag_a_fabrication_is_not_caught(digest: Path) -> None:
    """Why --retrieved has to be passed every time, not just when convenient.

    Syntactically the guessed URL is unimpeachable, so the check the skill ran
    before this change reports it clean.
    """
    r = run(str(digest), "--offline")

    assert r.returncode == 0
    assert "UNSOURCED" not in r.stdout


@pytest.mark.parametrize(
    "cited",
    [
        "https://vendor.test/blog/a-post-that-was-read/",  # trailing slash
        "https://WWW.Vendor.test/blog/a-post-that-was-read",  # host case, www
        "https://vendor.test/blog/a-post-that-was-read#section",  # fragment
    ],
)
def test_incidental_differences_do_not_read_as_fabrication(
    tmp_path: Path, retrieved: Path, cited: str
) -> None:
    """False positives here would train the operator to ignore the verdict."""
    doc = tmp_path / "d.md"
    doc.write_text(f"[x]({cited})\n", encoding="utf-8")

    r = run(str(doc), "--retrieved", str(retrieved), "--offline")

    assert r.returncode == 0, r.stdout


def test_a_different_path_on_a_retrieved_host_is_still_unsourced(
    tmp_path: Path, retrieved: Path
) -> None:
    """The path is what gets invented, so it cannot be normalised away."""
    doc = tmp_path / "d.md"
    doc.write_text("[x](https://vendor.test/blog/never-opened)\n", encoding="utf-8")

    r = run(str(doc), "--retrieved", str(retrieved), "--offline")

    assert r.returncode == 1
    assert "UNSOURCED" in r.stdout


def test_record_is_scanned_for_urls_anywhere_in_it(tmp_path: Path) -> None:
    """Raw tool output can be appended unedited, so the sweep need not reformat."""
    record = tmp_path / "retrieved-urls.txt"
    record.write_text(
        "1. Some Result Title\n"
        "   url: https://vendor.test/blog/a-post-that-was-read\n"
        "   snippet: ...\n",
        encoding="utf-8",
    )
    doc = tmp_path / "d.md"
    doc.write_text(
        "[x](https://vendor.test/blog/a-post-that-was-read)\n", encoding="utf-8"
    )

    r = run(str(doc), "--retrieved", str(record), "--offline")

    assert r.returncode == 0, r.stdout


def test_empty_record_is_an_invocation_error_not_a_clean_pass(
    tmp_path: Path, digest: Path
) -> None:
    """An empty record vouches for nothing; passing everything would be worse."""
    record = tmp_path / "empty.txt"
    record.write_text("", encoding="utf-8")

    r = run(str(digest), "--retrieved", str(record), "--offline")

    assert r.returncode == 2
    assert "cannot vouch" in r.stderr


def test_missing_record_is_an_invocation_error(tmp_path: Path, digest: Path) -> None:
    r = run(str(digest), "--retrieved", str(tmp_path / "absent.txt"), "--offline")

    assert r.returncode == 2
    assert "no such file" in r.stderr


def test_json_output_carries_the_verdict(digest: Path, retrieved: Path) -> None:
    import json

    r = run(str(digest), "--retrieved", str(retrieved), "--offline", "--json")

    # The receipt is an object, not a bare list: `provenance_checked` is a
    # property of the whole run and a list on its own cannot carry it.
    receipt = json.loads(r.stdout)
    assert receipt["provenance_checked"] is True
    verdicts = {e["url"]: e["verdict"] for e in receipt["results"]}
    assert verdicts["https://vendor.test/blog/slug-built-from-the-headline"] == "UNSOURCED"
    assert verdicts["https://vendor.test/blog/a-post-that-was-read"] == "OK"


# ------------------------------------------------------- the forms a digest uses


def test_bare_urls_are_checked(tmp_path: Path, retrieved: Path) -> None:
    """The citation form a real digest used, and the check did not see.

    A delivered digest listed its sources as `- **URL:** https://…`. The check
    recognised only bracketed links, found nothing, and exited zero — so a
    fabricated citation in that form was never examined at all.
    """
    doc = tmp_path / "d.md"
    doc.write_text(
        "### A headline\n"
        "- **URL:** https://vendor.test/blog/a-post-that-was-read\n"
        "### Another\n"
        "- **URL:** https://vendor.test/blog/slug-built-from-the-headline\n",
        encoding="utf-8",
    )

    r = run(str(doc), "--retrieved", str(retrieved), "--offline")

    assert r.returncode == 1, r.stdout
    assert "UNSOURCED" in r.stdout
    assert "slug-built-from-the-headline" in r.stdout


@pytest.mark.parametrize(
    "line",
    [
        "- **URL:** https://vendor.test/blog/a-post-that-was-read",
        "see https://vendor.test/blog/a-post-that-was-read.",
        "(https://vendor.test/blog/a-post-that-was-read)",
        "<https://vendor.test/blog/a-post-that-was-read>",
        "<https://vendor.test/blog/a-post-that-was-read|Opened>",
        "[Opened](https://vendor.test/blog/a-post-that-was-read)",
    ],
)
def test_every_citation_form_reaches_the_receipt(
    tmp_path: Path, retrieved: Path, line: str
) -> None:
    """One URL, six ways of writing it, one verdict.

    Trailing sentence punctuation is not part of the URL — a bare link followed
    by a full stop must not be reported BROKEN for it, or the check becomes
    something to work around.
    """
    import json

    doc = tmp_path / "d.md"
    doc.write_text(line + "\n", encoding="utf-8")

    r = run(str(doc), "--retrieved", str(retrieved), "--offline", "--json")

    receipt = json.loads(r.stdout)
    assert [e["url"] for e in receipt["results"]] == [
        "https://vendor.test/blog/a-post-that-was-read"
    ], r.stdout
    assert receipt["results"][0]["verdict"] == "OK"
    assert r.returncode == 0


def test_a_url_cited_twice_is_probed_once(tmp_path: Path, retrieved: Path) -> None:
    """The template gives a source a link and a bare URL; that is one citation."""
    import json

    doc = tmp_path / "d.md"
    url = "https://vendor.test/blog/a-post-that-was-read"
    doc.write_text(f"[Opened]({url})\n- **URL:** {url}\n", encoding="utf-8")

    r = run(str(doc), "--retrieved", str(retrieved), "--offline", "--json")

    assert len(json.loads(r.stdout)["results"]) == 1, r.stdout


# --------------------------------------------------------------- an empty check


def test_a_digest_with_no_links_fails(tmp_path: Path, retrieved: Path) -> None:
    """The exact shape of the pass that was not one.

    The check found no links, exited zero, and wrote a zero-byte receipt. The
    run read that as a clean gate and delivered. A gate that inspected nothing
    has been skipped, not satisfied.
    """
    doc = tmp_path / "d.md"
    doc.write_text("# Nothing to report\n\nA quiet week.\n", encoding="utf-8")

    r = run(str(doc), "--retrieved", str(retrieved), "--offline")

    assert r.returncode == 1, r.stdout
    assert "no links found" in r.stderr


def test_a_receipt_is_written_even_when_no_links_were_found(
    tmp_path: Path, retrieved: Path
) -> None:
    """A consumer needs the verdicts most when there are none."""
    import json

    doc = tmp_path / "d.md"
    doc.write_text("# Nothing to report\n", encoding="utf-8")

    r = run(str(doc), "--retrieved", str(retrieved), "--offline", "--json")

    receipt = json.loads(r.stdout)
    assert receipt["results"] == []
    assert receipt["files"][0]["name"] == "d.md"


# ------------------------------------------------------- a self-identifying receipt


def test_the_receipt_says_what_wrote_it_and_what_it_read(
    digest: Path, retrieved: Path
) -> None:
    """`add` can tell this file from one somebody typed.

    A run whose check produced nothing wrote its own receipt in a schema this
    script cannot emit, and delivered. The header is what makes that detectable
    rather than a matter of trust.
    """
    import hashlib
    import json

    r = run(str(digest), "--retrieved", str(retrieved), "--offline", "--json")

    receipt = json.loads(r.stdout)
    assert receipt["tool"] == "check_links"
    assert receipt["receipt_version"] == 1
    assert receipt["generated_at"]
    checked = receipt["files"][0]
    assert checked["name"] == digest.name
    assert checked["sha256"] == hashlib.sha256(digest.read_bytes()).hexdigest()
