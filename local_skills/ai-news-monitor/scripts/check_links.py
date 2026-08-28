#!/usr/bin/env python3
"""Check every link in a digest before it is delivered.

A digest is a set of claims plus the sources that back them. A link that does
not resolve does not merely look sloppy — it removes the reader's ability to
check the claim, which is the thing the digest is for. And an invented URL is
worse than none: it reads as a citation while being the opposite of one.

Three failure modes, and this script settles two of them:

  - **Malformed or dead** is mechanically decidable, so it is checked here.
  - **Never retrieved** — a URL built by guessing a slug from a headline — is
    decidable too, but only against a record of what this run actually opened.
    Pass `--retrieved` and any citation absent from that record is reported as
    UNSOURCED. This is the check that catches an invented URL which happens to
    resolve, and a fabricated citation usually does resolve: guessing that a
    title becomes its own slug is right often enough on sites that publish that
    way, so a link check alone returns OK on the fabrication and the reader is
    handed a citation nobody ever read.
  - **Wrong target** — a real page that does not say what it was cited for —
    is not decidable by any script. The defence for that is the provenance rule
    in SKILL.md: cite only what you actually opened.

Nothing here says anything about **age**, and that is deliberate rather than an
omission to fill in later. This script reasons about URLs, and a URL does not
carry a publication date: a slug reading `2026-mcp-roadmap` names the year the
roadmap covers, not the March it was posted. A months-old page is served with
exactly the 200 a fresh one is, so every verdict below returns OK on a stale
item, and a digest can pass this gate cleanly while being filled with material
from outside its own stated window. Freshness is a property of the item, where a
date field already exists, not of the link — so it is checked against the window
in Step 5 of SKILL.md, not here.

Verdicts are deliberately three-way rather than pass/fail, because many
perfectly good sources refuse automated requests. openai.com returns 403 to a
script, CNN returns 451, Reddit blocks outright. Treating those as broken would
train whoever runs this to ignore the output, so they are reported as BLOCKED
and do not fail the run. Only genuinely malformed URLs and definitive 404/410
responses are errors.

Handles Markdown [label](url), Markdown <url> autolinks, Slack mrkdwn
<url|label>, and bare URLs, so it works on both copies of a digest. Bare URLs
count because the template cites sources as `- **URL:** https://…` and a digest
written that way is the ordinary case, not a malformed one. A checker that
recognised only the bracketed forms found nothing in such a digest, reported no
links, and exited zero — passing a gate it had never applied.

Usage
  python3 scripts/check_links.py digest.md
  python3 scripts/check_links.py digest*.md digest*.slack.txt
  python3 scripts/check_links.py digest.md --offline    # syntax only, no network
  python3 scripts/check_links.py digest.md --json
  python3 scripts/check_links.py digest.md --retrieved retrieved-urls.txt

`--retrieved` may be passed more than once, and each file is scanned for
http(s) URLs anywhere in it, so raw search results or fetch output can be
appended as they arrive with no reformatting.

`--json` prints a **receipt**: the verdicts, plus whether provenance was checked
at all. It is written to be handed to `ledger.py add --verified`, which refuses
to record an item as published unless this run said its URL is usable. That is
how the verdict reaches the write without `add` opening a socket of its own —
the fetching stays here, in the one component that already does it.

  python3 scripts/check_links.py digest.md --retrieved retrieved-urls.txt \
          --json > link-check.json

`provenance_checked` is a property of the whole run, not of one link, which is
why it sits in the header rather than on each result: without `--retrieved`
nothing here can distinguish a citation from a guess, so a consumer needs to
know that before it trusts a single `OK`.

Exit codes: 0 all links usable, 1 at least one broken or unsourced *or* the
files held no links at all, 2 bad invocation. The receipt is written on every
one of those, because a consumer needs the verdicts most when they are bad.

Finding no links is a failure rather than a pass. This is a gate, and a gate
that inspected nothing has not been satisfied — it has been skipped. A digest
with no citation in it cannot support a published item either way, so there is
no reading of an empty result that means "ready to deliver".
"""

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

# [label](url) · <url|label> · <url> · bare https://…
#
# Order matters: the bracketed forms are tried first at each position, so a
# markdown link is consumed whole rather than having its target matched twice.
LINK_RE = re.compile(
    r"\[[^\]]*\]\((?P<a>[^)\s]+)\)"
    r"|<(?P<b>https?://[^>|\s]+)(?:\|[^>]*)?>"
    r"|(?P<c>https?://[^\s<>\"'\]\)]+)"
)

# Trailing punctuation belongs to the sentence, not the URL. Only stripped from
# a bare match: inside [label](url) the author drew the boundary themselves, and
# a stray character there is worth reporting rather than silently repairing.
BARE_TRAILING = ".,;:!?'\""

# The receipt's schema. `add` refuses anything that does not identify itself as
# this tool's output, so a receipt hand-written to get past a refusal fails
# loudly instead of resolving to a blank verdict.
RECEIPT_TOOL = "check_links"
RECEIPT_VERSION = 1

# Any bare URL, for reading the retrieval record. Deliberately looser than
# LINK_RE: that record is whatever the run happened to save, not formatted
# Markdown.
BARE_URL_RE = re.compile(r"https?://[^\s<>\"'\]\)]+")

# A browser sends one, and a surprising number of sites vary their response on
# it. Checking with a bare urllib signature would manufacture failures.
UA = "Mozilla/5.0 (compatible; ai-news-monitor link check)"

TIMEOUT = 10
BLOCKED_CODES = {401, 402, 403, 405, 406, 429, 451, 999}

SKILL_DIR = Path(__file__).resolve().parent.parent

# Where a working file does belong, quoted verbatim in the refusal below. A gate
# that says only "no" gets worked around; one that says what to type gets used.
#
# It names `ledger.py` rather than doing the derivation here on purpose: the run
# directory is derived from the ledger store, and this script is deliberately not
# told which store a run is using — it checks a digest, and a link checker that
# had to be pointed at a ledger would be one more flag to get wrong on the one
# command whose failure the run is not allowed to shrug off. The path it prints is
# derivable, which is the property that matters: a step that no longer holds it
# recomputes it from the store instead of making a new directory.
WORKING_FILE_RULE = (
    "Working files belong in this run's own directory, made once in Step 1:\n"
    "  python3 <skill>/scripts/ledger.py --home <store> --profile <profile> start-run\n"
    "It empties that directory and prints it — the store path with `.run` "
    "appended — and `status` prints the same path as `run_dir` for any step that "
    "no longer has it. Refer to files in it as <run>/<name>."
)


def path_in_skill_dir(path: str) -> bool:
    """True when this file sits inside the skill's own directory.

    A digest or a retrieval record kept there is shared by every profile and
    every run, and a deployed copy of the skill is replaced wholesale by the next
    sync. Both matter here: this script's whole job is to say something about one
    specific digest, and it has already said it about the wrong one — checking a
    `digest.md` that another run overwrote seconds later, reporting that run's
    stale links and never probing the seven fabricated URLs in the digest that
    was actually delivered.
    """
    try:
        resolved = Path(path).resolve()
    except OSError:
        return False
    return resolved == SKILL_DIR or SKILL_DIR in resolved.parents


def extract(text: str) -> list[str]:
    """Every URL the file offers a reader, in the order they appear.

    Deduplicated within a file: the same page cited twice would otherwise be
    probed twice and appear twice in the receipt for no gain.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in LINK_RE.finditer(text):
        if bare := m.group("c"):
            url = bare.rstrip(BARE_TRAILING)
        else:
            url = m.group("a") or m.group("b")
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def check_syntax(url: str) -> str | None:
    """Return a reason the URL is unusable, or None if it looks well formed."""
    if url.startswith(("mailto:", "#")):
        return "not a web link"
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return f"scheme is {parts.scheme or 'missing'}, expected http(s)"
    if not parts.netloc:
        return "no host"
    if "." not in parts.netloc.rstrip("."):
        return f"host {parts.netloc!r} has no dot"
    if any(c.isspace() for c in url):
        return "contains whitespace"
    # A trailing bracket or comma is nearly always the surrounding prose
    # captured by mistake, and it turns a good URL into a 404.
    if url[-1] in ").,;":
        return f"ends with {url[-1]!r}, probably punctuation from the sentence"
    if "example.com" in parts.netloc or parts.netloc.endswith(".example"):
        return "placeholder domain"
    return None


def normalise(url: str) -> str:
    """Reduce a URL to what makes two references the same page.

    Compared strictly, a citation would count as unsourced because the digest
    dropped a trailing slash the search result carried, which would train
    whoever runs this to pass --retrieved and then ignore it. Compared loosely,
    a guessed slug could match something genuinely retrieved. Case in the host,
    a default port, a trailing slash and a fragment are all safe to ignore; the
    path is not, because the path is exactly what gets invented.
    """
    parts = urlsplit(url.strip().rstrip(".,;)"))
    host = parts.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    if parts.port and parts.port not in (80, 443):
        host = f"{host}:{parts.port}"
    path = parts.path.rstrip("/")
    return f"{host}{path}?{parts.query}" if parts.query else f"{host}{path}"


def load_retrieved(paths: list[str]) -> set[str]:
    """Read the record of what this run actually opened."""
    seen: set[str] = set()
    for p in paths:
        path = Path(p)
        if not path.exists():
            raise FileNotFoundError(p)
        for u in BARE_URL_RE.findall(path.read_text(encoding="utf-8")):
            seen.add(normalise(u))
    return seen


def probe(url: str, timeout: int) -> tuple[str, str]:
    """Fetch just enough to learn whether the document is there."""
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return "OK", f"{r.status}"
    except urllib.error.HTTPError as e:
        # Some servers reject HEAD but serve GET perfectly well.
        if e.code in (400, 405, 501):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return "OK", f"{r.status} (GET)"
            except urllib.error.HTTPError as e2:
                e = e2
            except Exception as exc:
                return "BLOCKED", type(exc).__name__
        if e.code in (404, 410):
            return "BROKEN", f"{e.code} {e.reason}"
        if e.code in BLOCKED_CODES:
            return "BLOCKED", f"{e.code} {e.reason} — refuses automated requests"
        return "BLOCKED", f"{e.code} {e.reason}"
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        # A host that does not resolve is a fabricated or mistyped domain.
        if "Name or service not known" in str(reason) or "nodename nor servname" in str(reason):
            return "BROKEN", f"host does not resolve ({reason})"
        return "BLOCKED", str(reason)
    except Exception as exc:
        return "BLOCKED", type(exc).__name__


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("files", nargs="+", help="digest files to check")
    p.add_argument("--offline", action="store_true", help="syntax only, no requests")
    p.add_argument("--timeout", type=int, default=TIMEOUT)
    p.add_argument(
        "--json",
        action="store_true",
        help="write a receipt: verdicts plus whether provenance was checked, "
        "for ledger.py add --verified",
    )
    p.add_argument(
        "--retrieved",
        action="append",
        metavar="FILE",
        help="record of URLs actually retrieved this run; citations absent from "
        "it are UNSOURCED (repeatable)",
    )
    args = p.parse_args()

    stray = [f for f in [*args.files, *(args.retrieved or [])] if path_in_skill_dir(f)]
    if stray:
        print(
            "these are inside the skill directory (" + str(SKILL_DIR) + "):\n  "
            + "\n  ".join(stray)
            + "\nEvery run and every profile shares that one path, and a deployed "
            "copy is replaced wholesale by the next sync, so a digest kept there is "
            "overwritten by other runs. This check has already validated the wrong "
            "digest that way.\n" + WORKING_FILE_RULE,
            file=sys.stderr,
        )
        return 2

    retrieved: set[str] | None = None
    if args.retrieved:
        try:
            retrieved = load_retrieved(args.retrieved)
        except FileNotFoundError as exc:
            print(f"no such file: {exc}", file=sys.stderr)
            return 2
        if not retrieved:
            print(
                "--retrieved was given but the record holds no URLs. An empty "
                "record cannot vouch for anything, so every citation would be "
                "reported unsourced; record the sweep's results or drop the flag.",
                file=sys.stderr,
            )
            return 2

    urls: list[tuple[str, str]] = []
    checked_files: list[dict] = []
    for f in args.files:
        path = Path(f)
        if not path.exists():
            print(f"no such file: {f}", file=sys.stderr)
            return 2
        raw = path.read_bytes()
        # The digest's bytes, recorded so the receipt names what it inspected.
        checked_files.append(
            {
                "name": path.name,
                "path": str(path.resolve()),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
        )
        for u in extract(raw.decode("utf-8")):
            urls.append((path.name, u))

    no_links = not urls
    if no_links:
        print(
            "no links found in " + ", ".join(f["name"] for f in checked_files) + ".\n"
            "This is a failed check, not a clean one: nothing was inspected, so "
            "nothing has been vouched for. A digest citing no source cannot support "
            "a published item, and a receipt from this run says so — `add` will "
            "refuse every item that claims one.\n"
            "If the digest does cite sources, they are in a form this did not "
            "recognise; it reads [label](url), <url>, <url|label> and bare "
            "http(s) URLs.",
            file=sys.stderr,
        )

    results = []
    to_probe = []
    for src, u in urls:
        # Provenance outranks reachability: a URL nobody opened is a fabrication
        # whether or not it happens to resolve, and probing it would only
        # produce an OK that argues for keeping it.
        if retrieved is not None and normalise(u) not in retrieved:
            results.append(
                {
                    "file": src,
                    "url": u,
                    "verdict": "UNSOURCED",
                    "detail": "not in the record of what this run retrieved",
                }
            )
            continue
        bad = check_syntax(u)
        if bad:
            results.append({"file": src, "url": u, "verdict": "BROKEN", "detail": bad})
        elif args.offline:
            results.append({"file": src, "url": u, "verdict": "OK", "detail": "syntax only"})
        else:
            to_probe.append((src, u))

    if to_probe:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for (src, u), (verdict, detail) in zip(
                to_probe, pool.map(lambda t: probe(t[1], args.timeout), to_probe)
            ):
                results.append({"file": src, "url": u, "verdict": verdict, "detail": detail})

    broken = [r for r in results if r["verdict"] == "BROKEN"]
    blocked = [r for r in results if r["verdict"] == "BLOCKED"]
    unsourced = [r for r in results if r["verdict"] == "UNSOURCED"]

    if args.json:
        # An object rather than a bare list, so the receipt can carry the one
        # fact a per-link verdict cannot: whether anything checked provenance.
        # A guessed slug resolves on any site that builds URLs from titles, so
        # without --retrieved every fabrication in the file is reported OK, and
        # a consumer handed only the results would read that as verification.
        print(
            json.dumps(
                {
                    "tool": RECEIPT_TOOL,
                    "receipt_version": RECEIPT_VERSION,
                    "generated_at": datetime.now(timezone.utc).isoformat(
                        timespec="seconds"
                    ),
                    # What was inspected, by content. A receipt that names its
                    # files and their bytes is one `add` can tell apart from a
                    # receipt someone typed, and it says which draft was checked
                    # when a later one went out.
                    "files": checked_files,
                    "provenance_checked": retrieved is not None,
                    "results": results,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for r in results:
            if r["verdict"] != "OK":
                print(f"{r['verdict']:8} {r['url']}\n         {r['detail']}  [{r['file']}]")
        ok_count = len(results) - len(broken) - len(blocked) - len(unsourced)
        print(
            f"\n{len(results)} links: {ok_count} ok, {len(blocked)} blocked, "
            f"{len(broken)} broken, {len(unsourced)} unsourced",
            file=sys.stderr,
        )
        if blocked:
            print(
                "blocked means the site refused an automated request, not that the "
                "link is bad — confirm those in a browser if you have not already "
                "opened them.",
                file=sys.stderr,
            )
        if broken:
            print(
                "broken links must be fixed or removed before delivering. A citation "
                "the reader cannot follow is worse than no citation.",
                file=sys.stderr,
            )
        if unsourced:
            print(
                "unsourced links were never retrieved this run. Do not repair one by "
                "opening it now and keeping the sentence it was attached to: the claim "
                "was written before anything was read. Replace it with a source that "
                "was actually opened, or drop the item.",
                file=sys.stderr,
            )
    return 1 if broken or unsourced or no_links else 0


if __name__ == "__main__":
    raise SystemExit(main())
