#!/usr/bin/env python3
"""Seen-story ledger for the ai-news-monitor skill.

A monitoring skill is only useful if the second run does not repeat the first.
This keeps a small append-only record of what has already been reported, so a
sweep can ask "which of these are actually new?" before spending tokens reading
them, and so each digest can say honestly when it last looked.

Storage lives outside the repo because it is user state, not project code, and
follows the XDG spec. The root resolves most-explicit-first:
  --home  >  $AI_NEWS_HOME  >  $XDG_STATE_HOME/ai-news-monitor  >  ~/.local/state/ai-news-monitor

Profiles let one user keep separate watch lists (e.g. "work" and "personal")
without cross-talk.

Commands
  status                            last run, item count, beat breakdown, run dir
  start-run                         empty and print this run's scratch directory
  since                             just the last-run timestamp (or "never")
  new     --items JSON | --input F  filter candidates down to unseen, in-window items
  add     --items JSON | --input F  record items as reported, stamp the run
  record-run                        stamp a run that reported nothing
  config  [--interests TEXT]        read or set this profile's standing interests
  recent  [--days N] [--beat SLUG]  dump what was reported recently (default: LOOKBACK_DAYS)
  forget  --url URL                 drop one item (for a mis-recorded entry)

Only `new` and `add` take items. Everything else takes no items at all, and no
subcommand takes a bare positional argument — the profile is `--profile NAME`,
never a word on its own.

Items are always JSON, in one of three forms. `--input` in particular names a
file of item JSON, not a rendered digest: handing it the Markdown a run just
wrote fails with "input is not valid JSON" and records nothing.

  --input items.json           a file of item JSON, or stdin when omitted
  --items '[{"url": "..."}]'   inline JSON, for a handful of items you type
  --url ... --title ...        one item from flags, no JSON to write

`--input` is the normal form, and a file for it is written with the file-write
tool — never with a shell heredoc or a redirect. Titles are arbitrary web text,
and one apostrophe, quote or parenthesis in a title ends the shell's quoting
early and turns the rest of the JSON into shell syntax; retrying the same
command line cannot fix that, because the fault is in the quoting rather than in
the data. The same applies to `--items`, which additionally cannot carry a whole
candidate list: the operating system caps the length of a single argument, and a
list that exceeds it is rejected as "Argument list too long" before this script
runs at all. Use `--items` only for items short enough to have typed by hand.

Item JSON is a list of objects (or an object with an "items" key); only `url`
is required:
  [{"url": "...", "title": "...", "beat": "...", "date": "2026-07-30",
    "source": "...", "why": "one line on why it mattered"}]

`new` prints the unseen subset (same shape, plus "_dup_of" on ones it drops when
--verbose is passed), so it can be piped straight into the reading step. Kept
items that look related to something already reported carry "_maybe_same_as"
hints for the caller to adjudicate; --no-hints suppresses them.

`new` also drops items dated outside the run's window, which it works out for
itself from the profile's last run unless told otherwise with --window-start /
--window-end. An item outside the window survives only by naming one of the
documented boundary cases in a "window_exception" field. Nothing about this
changes the exit code.

`add` refuses to record an item as published unless it can establish where the
item came from, on both counts:

  the link      pass --verified with the receipt `check_links.py --json` wrote.
                Any published URL that run found broken, unsourced or never
                looked at stops the whole call.
  the date      the same window `new` applies, resolved the same way and
                overridable with the same --window-start / --window-end. An item
                outside it survives only on a documented "window_exception",
                exactly as in `new`.

Unlike `new`'s filter both are hard failures — the digest is already written by
the time `add` runs, so dropping an item here would leave it published and
unrecorded, which is worse than not recording the run. Entries marked
`duplicate_of` or `reason` were never shown to a reader and are exempt from both:
an item correctly ruled out by the window belongs in the ledger that way. The
exemption is checked rather than taken on trust — a URL that appears in the
receipt was cited in the digest, so an item claiming both is refused.
"""

import argparse
import calendar
import json
import os
import re
import shutil
import sys
from datetime import MAXYEAR, MINYEAR, UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that identify a campaign, not a document. Stripping these keeps
# the same article arriving from a newsletter and from search from looking like
# two different stories.
TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "hsa_", "vero_", "_hs")
TRACKING_EXACT = {
    "ref", "referrer", "source", "src", "fbclid", "gclid", "gbraid", "wbraid",
    "igshid", "cmpid", "campaign_id", "spm", "share", "share_id", "smid",
    "at_medium", "at_campaign", "guccounter", "__twitter_impression",
}

# Words that carry no distinguishing signal in a tech headline. Dropping them
# before fingerprinting stops "OpenAI Announces X" and "OpenAI Unveils X" from
# reading as unrelated stories.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "into", "is", "it", "its", "new", "now", "of", "on", "or", "the", "to",
    "with", "will", "that", "this", "you", "your", "we", "our", "says", "said",
    "announces", "announced", "announcing", "unveils", "unveiled", "launches",
    "launched", "introduces", "introducing", "releases", "released", "debuts",
    "reveals", "revealed", "brings", "adds", "update", "updates", "report",
    "reports", "here", "why", "how", "what", "can", "could", "just", "more",
}

# Dots are allowed inside a name but a name of only dots is "." or "..",
# which would silently resolve to the store root or its parent.
PROFILE_RE = re.compile(r"^(?!\.+$)[A-Za-z0-9._-]+$")

TITLE_MATCH_THRESHOLD = 0.72  # Jaccard overlap above which two titles are one story.

# How far back "have I already covered this?" looks. One value, deliberately,
# because it governs two things that must not drift apart: which stored items
# `new` compares against, and how much history `recent` hands back for the
# caller's own semantic review. If the human-or-model pass looked back less far
# than the lexical pass, it would be the weaker check on the harder cases —
# exactly backwards. Bounded rather than unlimited because headlines legitimately
# recur over long spans. Override per call with `recent --days N`.
LOOKBACK_DAYS = 45

# Independent coverage of one event shares much less headline vocabulary than
# you would expect: "Kimi K3 open weights arrive July 27, the catch is 1.4TB"
# and "Kimi K3 Open Weights: 2.8T Params, Day-0 Hosting" score 0.30. Dropping at
# that level is not safe — "vLLM v1.1.0 adds FP4 decode kernels" and "SGLang
# v0.5 adds FP4 decode kernels" score 0.60 and are genuinely different stories.
# So below the drop threshold we do not decide, we point: anything plausibly
# related is annotated and passed through for the caller to adjudicate.
SUGGEST_THRESHOLD = 0.22
MAX_HINTS = 2


# ------------------------------------------------------------------ window gate

# Two digests running have carried items five months and nine weeks older than
# the window they were headed with, after the rule had been stated in the skill,
# moved to the step that selects items, and had its contradiction removed. Both
# items were recorded with their true dates, so the model read the date, wrote it
# down, and kept the item regardless: a rule the model must apply to itself does
# not hold, however clearly it is written. Hence a gate that runs whatever the
# model concluded.
#
# The boundary is genuinely soft, though — SKILL.md Step 1 lists four cases where
# an out-of-window item belongs in the digest — so this is not a refusal. Three of
# those cases keep the item and are named here. The fourth, "older news in fresh
# coverage", is a rule to *drop* the item: it is dated by when the event happened
# rather than by when someone wrote about it again, and new commentary is not a
# new event. It gets no code deliberately, because a recap of an old announcement
# is precisely what both failures were.
WINDOW_EXCEPTIONS = {
    "straddles-window": (
        "the event spans the window start — a multi-day conference, an embargo "
        "that lifted the evening before"
    ),
    "still-live": (
        "announced just before the window, but its deadline, launch or effect "
        "lands inside it"
    ),
    "first-run-context": (
        "predates the window and is load-bearing on a first run, and the digest "
        "says that it predates the window"
    ),
}

# The window when the profile has never run, matching SKILL.md Step 1.
DEFAULT_WINDOW_DAYS = 7

# A story filed in a timezone ahead of UTC carries tomorrow's date for several
# hours. Without slack that reads as out-of-window and demands a justification
# that would be false, which is how a gate teaches its caller to route around it.
# One day only: anything further ahead is a mis-read year, which is worth
# stopping — Step 4 of the skill exists partly because fetched pages report 2026
# releases as 2024.
FUTURE_GRACE_DAYS = 1


# -------------------------------------------------------------- provenance gate

# A run published a complete seven-item digest in which every URL was invented.
# check_links.py caught it — `broken`, `unreachable` and `404` are all in that
# run's log — and `add` recorded the seven items regardless, because nothing
# carried the verdict from the check to the write. The detection was never the
# missing piece; the connection was. So `add` now asks for the verdict, and an
# item it cannot account for stops the call.
#
# The verdict arrives as a file, not a fetch. `add` is a local append that runs
# in tens of milliseconds; giving it network access would hand it timeouts,
# proxies, rate limits and a second implementation of a probe the skill already
# has. check_links.py does the fetching, writes what it concluded with --json,
# and this reads that.
#
# BLOCKED counts as usable on purpose, matching check_links.py's own exit code:
# openai.com answers 403 to a script and CNN 451, so treating a refused
# automated request as a bad link would fail runs over good citations — which is
# how a gate teaches its caller to route around it. BROKEN and UNSOURCED do not:
# one is a link the reader cannot follow, the other a link nobody opened.
USABLE_VERDICTS = {"OK", "BLOCKED"}

# The whole verdict vocabulary check_links.py emits. Anything outside it means
# the file is not that script's output, however much it resembles it — and the
# resemblance is the danger. A receipt was once hand-written with `status` keys
# where `verdict` belongs; every lookup returned the empty string, which is not
# a usable verdict, so `add` refused correctly but printed a URL followed by a
# blank reason. The refusal was right and unreadable, which sent the run looking
# for a fault in its items rather than in its receipt.
KNOWN_VERDICTS = USABLE_VERDICTS | {"BROKEN", "UNSOURCED"}

# What a receipt has to say about itself. check_links.py stamps these; nothing
# else does. Requiring them is what makes `--verified` a claim about a check
# that ran, rather than about a file that parses.
RECEIPT_TOOL = "check_links"
RECEIPT_VERSIONS = {1}

# What to run to produce the receipt, quoted verbatim in every refusal. A gate
# that says only "no" gets worked around; one that says what to type gets used.
RECEIPT_RECIPE = (
    "  python3 <skill>/scripts/check_links.py <run>/digest.md \\\n"
    "          --retrieved <run>/retrieved-urls.txt --json > <run>/link-check.json"
)


# --------------------------------------------------------------------------- paths


SKILL_DIR = Path(__file__).resolve().parent.parent

WORKING_FILE_RULE = (
    "Working files belong in this run's own directory, made once in Step 1:\n"
    "  python3 <skill>/scripts/ledger.py --home <store> --profile <profile> start-run\n"
    "It empties that directory and prints it — the store path with `.run` "
    "appended — so a step that no longer has the path derives it from the store "
    "again rather than making a second directory. Refer to files in it as "
    "<run>/<name>."
)

# Said here as well as in SKILL.md because a run that got this wrong is reading
# an error, not the prose. A model that is told only "the file is missing"
# reissues the command that failed to create it; one that is told which tool
# writes the file, and why the shell will not, has somewhere else to go.
FILE_WRITE_RULE = (
    "Write that file with the file-write tool — `write_file`, or `edit_file` to "
    "amend one that exists — and not with a shell heredoc or a redirect: item "
    "titles are arbitrary web text, and one apostrophe, quote or parenthesis in "
    "a title ends the quoting early and turns the rest of the JSON into shell "
    "syntax. That failure is in the quoting rather than in the data, so the same "
    "command line cannot help however many times it is retried."
)


def reject_path_in_skill_dir(path: str | None, flag: str) -> None:
    """Refuse a working file that lives inside the skill's own directory.

    That directory is a single path shared by every profile and every run, and on
    a deployed installation the next sync overwrites it wholesale — so a file
    written there is both raced and disposable. The race is not hypothetical: a
    link check ran against a `digest.md` that a different run replaced seconds
    later, so it validated the wrong digest and never probed the seven fabricated
    URLs of the one that was actually delivered.

    Checked on read rather than on write because reading is what these scripts
    do. It is the same run either way, and the point is to stop the run rather
    than to be a filesystem permission.
    """
    if not path or path == "-":
        return
    try:
        resolved = Path(path).resolve()
    except OSError:
        return
    if resolved != SKILL_DIR and SKILL_DIR not in resolved.parents:
        return
    raise SystemExit(
        f"{flag} {path} is inside the skill directory ({SKILL_DIR}).\n"
        "Every run and every profile shares that one path, and a deployed copy is "
        "replaced wholesale by the next sync, so files there are overwritten by "
        "other runs and lost by deploys. A link check has already passed a digest "
        "another run had since replaced.\n"
        f"{WORKING_FILE_RULE}"
    )


LEGACY_HOME = Path.home() / ".claude" / "ai-news-monitor"

_HOME_OVERRIDE: str | None = None


def set_home_override(path: str | None) -> None:
    """Apply `--home`, which outranks the environment.

    Set once from the parsed arguments before any command runs. The cache is
    cleared rather than assumed cold so this stays correct if the module is
    driven as a library rather than through main().
    """
    global _HOME_OVERRIDE
    if path is not None and not path.strip():
        raise SystemExit(
            "--home was given an empty value. Refusing to fall back to the real "
            "store: an unset shell variable would otherwise write live state "
            "into a run meant to be isolated."
        )
    _HOME_OVERRIDE = path
    home.cache_clear()


@cache
def home() -> Path:
    """Resolve the store root, following the XDG Base Directory spec.

    Precedence is most-explicit-wins: --home, then AI_NEWS_HOME, then
    XDG_STATE_HOME, then the XDG default. A flag beats an inherited environment
    because it is the thing the caller typed on purpose.

    Cached because several paths are derived per command; without it the
    legacy-store notice below would print once per lookup. One process is one
    CLI invocation, so re-reading the environment mid-run is not a case worth
    supporting.

    The ledger is a record of what was reported and when — history that should
    survive a restart but that nobody needs to back up or carry between
    machines. That is what XDG_STATE_HOME is for. Keeping it there rather than
    under any one agent's config directory means this script stays useful to
    whatever drives it.

    Order: --home > AI_NEWS_HOME > XDG_STATE_HOME > ~/.local/state.
    """
    if _HOME_OVERRIDE:
        return Path(_HOME_OVERRIDE).expanduser()

    if override := os.environ.get("AI_NEWS_HOME"):
        return Path(override).expanduser()

    xdg = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state"
    store = root / "ai-news-monitor"

    # An earlier version stored under ~/.claude/. Keep reading it rather than
    # silently starting a fresh ledger, which would re-report everything.
    if not store.exists() and LEGACY_HOME.exists():
        print(
            f"note: using legacy store {LEGACY_HOME} — move it to {store} to follow XDG",
            file=sys.stderr,
        )
        return LEGACY_HOME
    return store


def profile_dir(profile: str) -> Path:
    if not PROFILE_RE.match(profile or ""):
        raise SystemExit(
            f"invalid profile name {profile!r}: use letters, digits, dot, dash or "
            "underscore. A profile is a directory name, so a path here would "
            "scatter ledgers outside the store."
        )
    d = home() / profile
    d.mkdir(parents=True, exist_ok=True)
    return d


def ledger_path(profile: str) -> Path:
    return profile_dir(profile) / "ledger.jsonl"


def state_path(profile: str) -> Path:
    return profile_dir(profile) / "state.json"


# The working files a run makes for itself, named here so `start-run` can write
# them down. Nothing reads this list to decide anything — it exists so a step
# does not have to join a long store path to a filename by hand, because a
# mistyped path produces a command that fails, gets retried unchanged, and takes
# the run with it. The digest is the one entry that is also a deliverable, and it
# is a copy of this file that leaves, never this file.
RUN_WORKING_FILES = (
    "candidates.json",
    "verified.json",
    "retrieved-urls.txt",
    "digest.md",
    "link-check.json",
    "reported.json",
)


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


def run_dir_for(profile: str) -> Path:
    """This run's scratch directory, derived so a later step can re-derive it.

    Public, and derived rather than made fresh, for a stronger version of the
    reason the ledger and the state file are derived: `--home` and `--profile` are
    the two strings the caller supplies, so anything positioned beside the store
    can be recomputed at any point in a run instead of being carried from step to
    step. A digest is drafted by one command, link-checked by a second, recorded
    by a third and delivered by a fourth, and each of those is its own shell — so
    a directory the first made with `mktemp -d` is gone by the second, and cannot
    be found again, because its name was random and nothing wrote it down. That
    has already cost a run: the link check ran against a digest another run had
    replaced, and passed seven citations it never probed.

    Beside the profile's store rather than inside the skill directory, because
    that directory is shared by every run and every profile and is replaced
    wholesale by the next sync; and beside the store rather than in the working
    directory, because a working directory shared between runs turns one run's
    leftovers into the next run's inputs.

    The suffix is appended, not replaced: a profile name may contain a dot, and
    replacing the suffix would make profiles `a.b` and `a.c` share one `a.run`.
    """
    store = profile_dir(profile)
    return store.parent / f"{store.name}.run"


def prepare_run_dir(profile: str) -> Path:
    """Empty and create this run's scratch directory, and return it.

    Cleared on entry rather than on exit, which is the part that makes it
    reliable: a run that fails never reaches a cleanup step, and it is exactly the
    failed run whose leftovers mislead its successor. A stale `digest.md` beside
    the store is indistinguishable from one this run wrote, so a run that dies
    during the sweep leaves the next step link-checking last week's digest and
    delivering it — a digest no run produced, headed with a window it never
    covered.

    The timing of the clear is unchanged, and is made safe by refusing rather
    than clearing when the directory is being written to at that moment. A
    leftover is still deleted, which is the whole point of clearing on entry;
    only the write that is still in flight is spared, and it is spared loudly.
    """
    run_dir = run_dir_for(profile)
    if run_dir.is_dir():
        held = names_held_open_in(run_dir)
        if held:
            raise SystemExit(
                f"the run directory is being written to right now: {run_dir}\n"
                f"Held open by a command that is still running: "
                f"{', '.join(held)}.\n"
                "\n"
                "`start-run` empties that directory as its first action, so "
                "anything a redirect on the same command line writes there is "
                "deleted while it is still being written. That is why the file "
                "cannot be found afterwards, and why issuing the same command "
                "line again cannot help.\n"
                "\n"
                "Run `start-run` on its own instead: it prints the run "
                "directory and nothing else, and that one line is the whole of "
                "its output. This run's working files are written there by the "
                "steps that follow, each as its own command, after `start-run` "
                "has returned."
            )
        shutil.rmtree(run_dir, ignore_errors=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "store": str(profile_dir(profile)),
                "profile": profile,
                "files": {name: str(run_dir / name) for name in RUN_WORKING_FILES},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_dir


# --------------------------------------------------------------------- normalising


def canonical_url(url: str) -> str:
    """Reduce a URL to the thing that identifies the document."""
    url = str(url or "").strip()
    if not url:
        return ""
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    host = host.split(":")[0] if host.endswith((":80", ":443")) else host

    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not (k.lower() in TRACKING_EXACT or k.lower().startswith(TRACKING_PREFIXES))
    ]
    path = parts.path.rstrip("/") or "/"
    # amp variants point at the same article
    path = re.sub(r"/amp$", "", path)
    return urlunsplit(("https", host, path, urlencode(sorted(kept)), ""))


def stem(word: str) -> str:
    """Crude suffix stripping, enough to collapse headline verb tense.

    Coverage of one event reliably varies the verb — "retires", "retiring",
    "retired" — and without this the same story reads as three. A real stemmer
    would be better but not by enough to justify the dependency.
    """
    for suffix, min_len in (("ing", 6), ("ed", 5), ("es", 5), ("s", 4)):
        if word.endswith(suffix) and len(word) >= min_len:
            return word[: -len(suffix)]
    return word


# Stopwords are compared after stemming, so that a reporting verb is dropped
# whatever its tense. Testing the raw word instead let "reporting" through while
# "reports" was removed, which moved a score by 0.25 — enough to straddle the
# drop threshold on an otherwise identical pair.
STEMMED_STOPWORDS = frozenset(stem(w) for w in STOPWORDS) | STOPWORDS


def title_tokens(title: str) -> frozenset[str]:
    """Reduce a headline to the tokens that identify the story it tells.

    Short tokens are dropped as noise, but never ones containing a digit. In
    this field the digit usually *is* the story: "vLLM v0.9" and "vLLM v0.10"
    differ by one character, and dropping it leaves two token sets that are
    identical, so a genuinely new release scores 1.0 against its predecessor and
    is discarded as a repeat. Suppressing real news is the one failure this
    whole script exists to prevent, so version and model numbers are kept
    whatever their length.
    """
    words = re.findall(r"[a-z0-9]+", str(title or "").lower())
    stems = (stem(w) for w in words)
    return frozenset(
        w
        for w in stems
        if w not in STEMMED_STOPWORDS and (len(w) > 2 or any(c.isdigit() for c in w))
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def parse_date_span(value: str) -> tuple[date, date] | None:
    """Read an item's `date` as the span of days it could denote, or None.

    A span rather than a point because sources publish at three granularities and
    only the full form is unambiguous. A monthly archive gives "2026-08", which
    means some day in August; pinning that to the 1st would put a story filed on
    the 20th outside a window starting on the 4th, and the gate would then be
    wrong about a legitimate item — the one failure that gets a check disabled.
    Comparing spans keeps a coarse date honest: it is out of window only when no
    day it could mean falls inside.

    Returning None for anything unreadable, rather than guessing, is what lets the
    caller distinguish "this is outside the window" from "nobody established a
    date"; those want different handling and must not be collapsed.
    """
    text = str(value or "").strip()
    if not text:
        return None

    # Full ISO date, or a timestamp: exact to the day either way.
    if dt := parse_iso(text):
        return dt.date(), dt.date()

    if m := re.fullmatch(r"(\d{4})-(\d{1,2})", text):
        year, month = int(m[1]), int(m[2])
        if not 1 <= month <= 12 or not MINYEAR <= year <= MAXYEAR:
            return None
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])

    if m := re.fullmatch(r"(\d{4})", text):
        year = int(m[1])
        if not MINYEAR <= year <= MAXYEAR:
            return None
        return date(year, 1, 1), date(year, 12, 31)

    return None


def _window_bound(value: str | None, flag: str, *, end: bool) -> date | None:
    """Read one end of an explicitly given window, or None when it was omitted.

    A coarse bound resolves outwards — `--window-start 2026-08` means from the
    1st, `--window-end 2026-08` means through the 31st — so a month-granularity
    window covers the whole month rather than a single day of it.
    """
    if not value:
        return None
    span = parse_date_span(value)
    if span is None:
        raise SystemExit(
            f"{flag} is not a date: {value!r}. Use YYYY-MM-DD (YYYY-MM and YYYY "
            "also work, and resolve to the whole month or year)."
        )
    return span[1] if end else span[0]


def resolve_window(args) -> tuple[date, date, str]:
    """Settle the window this run covers, and say where the answer came from.

    Precedence mirrors SKILL.md Step 1: an explicit `--window-start` wins,
    otherwise the profile's own `last_run`, otherwise the documented seven-day
    default for a profile that has never run. Working it out rather than
    requiring a flag is the whole point — a gate that fires only when the caller
    remembers to arm it is instruction again, and instruction is what failed.

    The source string is returned so the summary line can name it. A window
    silently derived from the wrong place would be a worse failure than the one
    this replaces, because it would be invisible.
    """
    today = datetime.now(UTC).date()
    end = _window_bound(args.window_end, "--window-end", end=True) or today

    if start := _window_bound(args.window_start, "--window-start", end=False):
        source = "--window-start"
    elif last_run := parse_iso(read_state(args.profile).get("last_run", "")):
        start, source = last_run.date(), "this profile's last run"
    else:
        start = end - timedelta(days=DEFAULT_WINDOW_DAYS)
        source = f"the {DEFAULT_WINDOW_DAYS}-day default — this profile has never run"

    if start > end:
        raise SystemExit(
            f"window start {start} is after window end {end}. "
            "Check --window-start/--window-end."
        )
    return start, end, source


def window_check(item: dict, start: date, end: date) -> tuple[str, str]:
    """Judge one item against the window. Returns (verdict, note).

    Verdicts, and why each is what it is:

    ``ok``        dated inside the window; nothing to say.
    ``undated``   no usable date. Kept, not dropped: Step 2 of the skill
                  explicitly allows a candidate to reach this point without one
                  and have it established during the Step 4 fetch, so dropping
                  here would fight documented policy on ordinary runs. Annotated
                  and counted instead, because an item that reaches the digest
                  still undated is a real defect.
    ``excepted``  outside the window, with one of the documented boundary cases
                  named. Kept, and the name is echoed so the digest can say which.
    ``out``       outside the window with no exception named, or with one that is
                  not a documented case. Dropped.

    An unrecognised exception is treated as no exception on purpose. Free text
    in that field would make the gate self-service: anything that had to be
    justified could be justified by asserting it was, which is the failure being
    fixed, one level up.
    """
    span = parse_date_span(item.get("date", ""))
    if span is None:
        raw = str(item.get("date", "")).strip()
        if raw:
            return "undated", f"date {raw!r} is not a date — fix it or drop the item"
        return "undated", "no date — establish one when you fetch it, or drop the item"

    first, last = span
    if first > end + timedelta(days=FUTURE_GRACE_DAYS):
        placement = f"dated {item.get('date')}, ahead of the window ending {end}"
    elif last < start:
        placement = f"dated {item.get('date')}, before the window starting {start}"
    else:
        return "ok", ""

    claimed = str(item.get("window_exception", "")).strip()
    if claimed in WINDOW_EXCEPTIONS:
        return "excepted", f"{placement}; kept as {claimed}: {WINDOW_EXCEPTIONS[claimed]}"
    if claimed:
        return "out", (
            f"{placement}. window_exception {claimed!r} is not one of the "
            f"documented boundary cases ({', '.join(WINDOW_EXCEPTIONS)})"
        )
    return "out", (
        f"{placement}. To keep it, set window_exception to one of "
        f"{', '.join(WINDOW_EXCEPTIONS)} — a recap of an older event is none of them"
    )


# ------------------------------------------------------------------------- storage


# Growth is not managed, deliberately. Entries run ~575 bytes, so a weekly digest
# reaches ~7 MB after ten years and `new` stays under 0.2s (measured: 5k entries
# 0.10s, 50k 0.53s, 200k 2.2s). Daily cadence for a decade is ~50 MB and ~1s.
#
# If that ever needs addressing, compact rather than delete. Title comparison is
# already bounded by LOOKBACK_DAYS, but URL matching is deliberately unbounded —
# dropping an old URL means a repost of that link costs a fresh semantic catch
# again, which is the whole payoff of duplicate_of. Only canonical_url, beat,
# duplicate_of/reason and recorded_at are read for entries older than the window,
# so stripping the other fields preserves every current behaviour at ~226 bytes.
def read_ledger(profile: str) -> list[dict]:
    path = ledger_path(profile)
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a torn line should not take down the whole run
    return out


def append_ledger(profile: str, entries: list[dict]) -> None:
    with ledger_path(profile).open("a", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def read_state(profile: str) -> dict:
    """Load a profile's state, refusing to guess if the file is damaged.

    Returning an empty dict on a parse error would be worse than failing: the
    profile would read as never having run, the window would silently widen to
    the default, and the next write would overwrite the damaged file — losing
    the run count and the standing interests for good. Better to stop and let
    someone look at it.
    """
    path = state_path(profile)
    if not path.exists():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"{path} is not valid JSON ({exc}).\n"
            "Refusing to continue: this profile would look like it had never run, "
            "and the next write would overwrite it. Inspect or delete the file."
        ) from None
    if not isinstance(state, dict):
        raise SystemExit(f"{path} should contain a JSON object, found {type(state).__name__}.")
    return state


def write_state(profile: str, state: dict) -> None:
    """Write via a temporary file so an interrupted run cannot truncate state."""
    path = state_path(profile)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


# window_exception belongs here rather than only on `new` because `add` applies
# the same window now, and a gate whose escape hatch the second checkpoint does
# not recognise would refuse the legitimate items the first one deliberately
# kept. One field, one meaning, read the same way by both — the alternative is a
# second vocabulary for the same judgement, which is how two gates drift apart.
# It is stored as well as read, so an out-of-window entry in the ledger says on
# its own line why it is there.
_ITEM_FIELDS = (
    "url", "title", "beat", "date", "source", "why", "duplicate_of", "reason",
    "window_exception",
)


def items_from_flags(args) -> list[dict] | None:
    """Build items from the inline forms, or None when neither was used.

    A caller holding one item should not have to write a JSON document to record
    it, so there are three ways in:

    - ``--items '<json>'`` — a JSON list, an ``{"items": [...]}`` object, or a lone object
    - ``--url ... --title ...`` — one item from named flags
    - ``--input FILE`` or stdin — the bulk form, unchanged

    Returns None when neither inline form was given, so the caller falls through
    to ``load_items``.
    """
    inline = getattr(args, "items", None)
    if inline:
        try:
            data = json.loads(inline)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"--items is not valid JSON: {exc}") from None
        if isinstance(data, dict):
            data = data["items"] if "items" in data else [data]
        if not isinstance(data, list):
            raise SystemExit(f"--items must be a JSON list or object, got {type(data).__name__}")
        bad = [entry for entry in data if not isinstance(entry, dict)]
        if bad:
            raise SystemExit(f"--items contains a non-object entry, e.g. {bad[0]!r:.60}")
        return data

    # getattr with a default because the item flags are registered only on the
    # subcommands that consume items; elsewhere the key is simply absent.
    single = {f: getattr(args, f, None) for f in _ITEM_FIELDS}
    single = {k: v for k, v in single.items() if v}
    if not single:
        return None
    if "url" not in single:
        raise SystemExit(
            "--url is required when recording an item from flags; "
            "the ledger suppresses by URL, so an item without one matches nothing"
        )
    return [single]


def read_input_text(source: str | None) -> str:
    """The text behind ``--input``, or stdin, refusing unreadably.

    A bare ``Path.read_text`` raises FileNotFoundError, and a traceback says
    only that a path was absent — not that the file was this run's own to write,
    nor which tool writes it. The run that cost this read the traceback as noise
    and reissued the same command, so the message names the path, says the file
    is read and never created, and carries the rule for writing it.
    """
    if source in (None, "-"):
        return sys.stdin.read()

    path = Path(source)
    if path.is_dir():
        raise SystemExit(
            f"--input {source} is a directory, not a file.\n"
            "Name the JSON file inside it that holds the items, then run this "
            f"command again.\n{FILE_WRITE_RULE}"
        )
    if not path.exists():
        raise SystemExit(
            f"--input {source} does not exist.\n"
            "This command reads that file and never creates it, so write it "
            "first and then run this command again.\n"
            f"{FILE_WRITE_RULE}\n{WORKING_FILE_RULE}"
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(
            f"--input {source} could not be read: {exc.strerror or exc}.\n"
            "Write the items to a readable path in this run's own directory and "
            f"pass that instead.\n{WORKING_FILE_RULE}"
        ) from None
    except UnicodeDecodeError:
        raise SystemExit(
            f"--input {source} is not UTF-8 text, so it is not the item JSON "
            "this expects.\n"
            "Check the path names the candidates file this run wrote, and "
            f"rewrite it if it does not.\n{FILE_WRITE_RULE}"
        ) from None


def load_items(source: str | None) -> list[dict]:
    reject_path_in_skill_dir(source, "--input")
    raw = read_input_text(source)
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"input is not valid JSON: {exc}") from None

    if isinstance(data, dict):
        if "items" not in data:
            raise SystemExit(
                "expected a JSON list of items, or an object with an \"items\" key. "
                "Got an object with: " + ", ".join(sorted(data)[:6])
            )
        data = data["items"]
    if not isinstance(data, list):
        raise SystemExit(f"expected a JSON list of items, got {type(data).__name__}")

    bad = [i for i in data if not isinstance(i, dict)]
    if bad:
        # Silently discarding these is how a caller ends up believing an empty
        # result means "nothing new" when it really means "nothing understood".
        raise SystemExit(
            f"{len(bad)} entr{'y' if len(bad) == 1 else 'ies'} in the list "
            f"{'is' if len(bad) == 1 else 'are'} not an object, e.g. {bad[0]!r:.60}"
        )
    return data


def is_published(item: dict) -> bool:
    """True when this entry is something a reader was actually shown.

    `duplicate_of` and `reason` mark entries recorded so their URL stops coming
    back, never entries that appeared in a digest. Nothing was cited, so there is
    no citation to verify — and Step 7 of the skill records a correctly
    out-of-window item as a `reason` suppression precisely because it was *not*
    published. Holding suppressions to a publication standard would break the one
    recipe that stops stale news costing a judgement call every week.
    """
    return not (item.get("duplicate_of") or item.get("reason"))


def load_link_receipt(path: str) -> dict[str, dict]:
    """Read check_links.py's verdicts, keyed the way this script keys URLs.

    Canonicalising here rather than trusting either side's spelling is what
    makes the match survive a trailing slash or a utm_ parameter that one file
    carried and the other did not. A near-miss would read as "this URL was never
    checked", and a gate that fails on good input is a gate that gets bypassed.

    A URL cited twice takes its worst verdict: the same link can be sound in one
    place and unsourced in another, and the unsourced one is the finding.
    """
    reject_path_in_skill_dir(path, "--verified")
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        # The commonest way to arrive here is a check that ran and printed its
        # receipt to the terminal, because the `> file` was dropped from the
        # recipe. A check whose links are sound exits zero doing that, so the
        # first sign of trouble is this line — which is why it says what is
        # missing rather than only that something was.
        raise SystemExit(
            f"--verified {path}: no such file. The receipt has to exist before "
            "`add` can read it; a check whose output was not redirected into a "
            "file leaves nothing behind, and exits zero when its links are sound.\n"
            f"{RECEIPT_RECIPE}\n"
            "Nothing was written and the run is not stamped — this says the "
            "receipt could not be read, not that anything is wrong with the items."
        ) from None
    except OSError as exc:
        raise SystemExit(
            f"--verified {path}: {exc.strerror}. The receipt could not be read, "
            "which says nothing about the items — nothing was written and the run "
            f"is not stamped.\n{RECEIPT_RECIPE}"
        ) from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"--verified {path} is not valid JSON: {exc}") from None

    if isinstance(data, list):
        raise SystemExit(
            f"--verified {path} holds a bare list of results. It must be the whole "
            "object check_links.py --json prints: the header says whether "
            "provenance was checked at all, and a list on its own cannot.\n"
            f"{RECEIPT_RECIPE}"
        )
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise SystemExit(
            f"--verified {path} is not a check_links.py receipt (no \"results\" list). "
            f"This is not the digest and not the item JSON:\n{RECEIPT_RECIPE}"
        )
    # Identity before content. A file that parses and holds a "results" list is
    # not thereby a link check; the one that caused this had both, and was typed
    # by hand after the real check came back empty.
    if data.get("tool") != RECEIPT_TOOL:
        raise SystemExit(
            f"--verified {path} does not identify itself as a {RECEIPT_TOOL} receipt "
            f"(\"tool\": {data.get('tool')!r}, expected {RECEIPT_TOOL!r}).\n"
            "A receipt is the output of the check, not a description of it: writing "
            "one by hand records an opinion about the links, which is the thing this "
            "flag exists to stop standing in for a check. If the check found nothing "
            "to report, that is a failed check — the digest cites nothing this run "
            "can vouch for.\n"
            f"{RECEIPT_RECIPE}"
        )
    version = data.get("receipt_version")
    if version not in RECEIPT_VERSIONS:
        raise SystemExit(
            f"--verified {path} carries receipt_version {version!r}, which this "
            f"ledger does not read (knows: {sorted(RECEIPT_VERSIONS)}). The check "
            "and the ledger are shipped together, so this means one of them is from "
            "a different copy of the skill.\n"
            f"{RECEIPT_RECIPE}"
        )
    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit(
            f"--verified {path} names no files, so it does not say which digest was "
            "checked. Every receipt records the files it read and their sha256.\n"
            f"{RECEIPT_RECIPE}"
        )
    for entry in files:
        digest = entry.get("sha256") if isinstance(entry, dict) else None
        if not (isinstance(digest, str) and len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)):
            raise SystemExit(
                f"--verified {path} has a files entry with no usable sha256 "
                f"({entry!r}). The receipt must be the one the check wrote.\n"
                f"{RECEIPT_RECIPE}"
            )

    if not data.get("provenance_checked"):
        raise SystemExit(
            f"--verified {path} was produced without --retrieved, so it says the "
            "links resolve, not that anyone opened them — and a slug guessed from "
            "a headline resolves on any site that builds URLs that way. Re-run the "
            f"check against the record of what this run retrieved:\n{RECEIPT_RECIPE}"
        )

    verdicts: dict[str, dict] = {}
    for index, result in enumerate(data["results"]):
        if not isinstance(result, dict):
            raise SystemExit(
                f"--verified {path}: results[{index}] is {type(result).__name__}, not "
                f"an object with a url and a verdict.\n{RECEIPT_RECIPE}"
            )
        # A missing or unrecognised verdict is a malformed receipt, never an
        # unusable link. Read as the latter it produces a refusal with nothing
        # after the colon, which reads as a verdict on the item and sends the
        # run to fix a digest that was never the problem.
        verdict = result.get("verdict")
        if verdict not in KNOWN_VERDICTS:
            keys = ", ".join(sorted(result)) or "none"
            raise SystemExit(
                f"--verified {path}: results[{index}] has no verdict this ledger "
                f"recognises ({verdict!r}; keys present: {keys}). Expected one of "
                f"{sorted(KNOWN_VERDICTS)}.\n"
                "This is a malformed receipt, not a bad link — nothing here says "
                "anything about the item. Re-run the check and pass the file it "
                "wrote, unedited.\n"
                f"{RECEIPT_RECIPE}"
            )
        url = canonical_url(result.get("url", ""))
        if not url:
            continue
        prior = verdicts.get(url)
        if prior and (prior["verdict"] not in USABLE_VERDICTS or verdict in USABLE_VERDICTS):
            continue
        verdicts[url] = {
            "verdict": verdict,
            "detail": str(result.get("detail", "")),
        }
    return verdicts


class GateRefusal(SystemExit):
    """A gate judged the items and refused them.

    The distinction this class draws is the whole point of it. `add` latches a
    marker when a gate refuses, so that `record-run` cannot later stamp over a
    digest that went unrecorded — and that marker outlives the run, blocking
    every subsequent stamp until an `add` succeeds. Latching it is therefore only
    correct when a gate actually reached a verdict on the items.

    Every gate also raises SystemExit for reasons that are nothing to do with the
    items: a receipt that does not exist, does not parse, or was written by a
    different version of the check; a `--window-start` that is not a date; a
    working file in the skill directory. Those say the gate could not run, not
    that it ran and said no. Caught as refusals, they record a provenance verdict
    on items whose provenance was never assessed — one did, when a run passed
    `--verified` a path that its own check had never been redirected into. The
    file was missing, the run failed correctly, and the profile came away with a
    latch that read as a judgement on two items nobody had judged.

    So the four sites that judge items raise this, and `add` catches only this.
    Everything else propagates as a plain SystemExit: loud, unhandled, and
    leaving the profile exactly as it found it.
    """


def mark_refused(profile: str, published: int) -> None:
    """Remember that an `add` reached a gate and was refused.

    Deliberately not part of the refusal's "nothing was written" promise, which
    is about the ledger and the clock: neither moves here, so the same `add` can
    be fixed and run again with no cleanup. What this records is that a run
    produced a digest and recorded none of it — the one thing `record-run` needs
    to know and has no other way to learn, since a refused profile is otherwise
    indistinguishable from one that simply has not run yet.
    """
    state = read_state(profile)
    state["refused_at"] = now_iso()
    state["refused_items"] = published
    write_state(profile, state)


def check_window_at_add(items: list[dict], start: date, end: date, source: str) -> list[str]:
    """Stop the run unless every published item is one this window admits.

    `new` applies this at Step 3, but nothing made the published set a subset of
    what `new` returned, so an item introduced afterwards was never checked at
    all. One was: a story dated twelve days before the window, reusing the URL of
    an in-window entry, recorded by an `add` whose `new` call had reported zero
    drops. It did not slip past the gate; it never reached it. So the gate also
    runs where the published set is finally fixed.

    Same verdicts, same field, same three exception codes as `new` — a second
    checkpoint that judged differently would just relocate the argument.

    Undated is kept, exactly as `new` keeps it: Step 2 lets a candidate arrive
    without a date and Step 4 establishes it, so refusing here would fight
    documented policy. It is reported, because an item reaching the ledger still
    undated has been through two gates that could not judge it.

    Returns the notes for undated items; refuses outright on anything out of
    window. Nothing is written before it returns.
    """
    refused: list[str] = []
    undated: list[str] = []
    for item in items:
        verdict, note = window_check(item, start, end)
        title = str(item.get("title", "")) or "(untitled)"
        if verdict == "out":
            refused.append(f"  {title[:70]}\n    {note}")
        elif verdict == "undated":
            undated.append(f"  {title[:70]}: {note}")

    if refused:
        # The window's source is named because the window itself is the thing
        # most likely to be wrong here — a second `add` in the same run reads
        # back the stamp the first one wrote and derives a one-day window, and
        # without this line that refusal would look like a verdict on the item.
        raise GateRefusal(
            f"refusing to record {len(refused)} of {len(items)} published item(s) — "
            f"outside the window {start} .. {end} (from {source}):\n"
            + "\n".join(refused)
            + "\n\nNothing was written and the run is not stamped. An item is only "
            "published if it belongs in this digest; one that does not belongs in "
            "the ledger as a suppression, with a `reason` such as \"out of window: "
            "disclosed 6 July\" — which records it without claiming it was reported, "
            "and stops it resurfacing in every future sweep.\n"
            "If the window itself is wrong, pass the one the digest is headed with: "
            "--window-start / --window-end, the same flags `new` takes. Record a run "
            "in one `add` call: a second one sees the stamp the first wrote and "
            "derives a window of a single day."
        )
    return undated


def check_provenance(published: list[dict], receipt: str | None) -> None:
    """Stop the run unless every published item's URL was checked and usable.

    Nothing is written before this returns. `add` is one call that both records
    items and stamps the run, so a partial write would leave the caller unable to
    say which items are in the ledger and the profile's clock advanced over a
    digest that was never fully recorded — the state that makes the *next* run
    wrong too. All or nothing is the only outcome that stays legible.
    """
    if not published:
        return  # nothing was shown to a reader; there is nothing to vouch for

    if not receipt:
        # A verdict, not an operational failure: the published set was assessed
        # and nothing vouches for any of it. Unlike a receipt that could not be
        # read, this leaves no doubt about the items — the run is claiming to
        # have shown a reader N items and can show nothing for them, which is
        # precisely the state `record-run` must not be allowed to stamp over.
        raise GateRefusal(
            f"recording {len(published)} item(s) as published needs --verified: the "
            "receipt from this run's link check. A run once published seven items "
            "whose URLs were all invented; the check had already caught them and "
            "nothing stopped the write.\n"
            f"{RECEIPT_RECIPE}\n"
            "  ledger.py --profile <profile> add --input reported.json "
            "--verified link-check.json --window 7d\n"
            "Items recorded only to suppress them — carrying duplicate_of or "
            "reason — were never published and need no receipt."
        )

    verdicts = load_link_receipt(receipt)
    refused: list[str] = []
    for item in published:
        url = canonical_url(item.get("url", ""))
        title = str(item.get("title", "")) or "(untitled)"
        if not url:
            refused.append(f"  {title[:70]}\n    no url — a published item with no citation cannot be checked")
            continue
        found = verdicts.get(url)
        if found is None:
            refused.append(
                f"  {item.get('url')}\n    not in {receipt} — this URL is not in the "
                "digest that was checked, or the check ran before the digest was written"
            )
        elif found["verdict"] not in USABLE_VERDICTS:
            refused.append(f"  {item.get('url')}\n    {found['verdict']}: {found['detail']}")

    if refused:
        raise GateRefusal(
            f"refusing to record {len(refused)} of {len(published)} published item(s) — "
            "provenance not established:\n"
            + "\n".join(refused)
            + "\n\nNothing was written and the run is not stamped. Fix the digest and "
            "the item list together, re-run the link check, then record again. Do not "
            "clear an UNSOURCED verdict by opening the page now and keeping the "
            "sentence: the claim was written before anything was read.\n"
            "An item that is correctly not going out belongs in the ledger as a "
            "suppression, with duplicate_of or reason — not as a published item."
        )


# ------------------------------------------------------------------------ commands


def check_suppressions(items: list[dict], receipt: str | None) -> None:
    """Stop the run when something marked as suppressed was in fact published.

    `duplicate_of` and `reason` exempt an item from both gates, and that exemption
    is sound: the item was never shown to anyone, so there is no citation to
    verify, and refusing it for being out of window would break the one recipe —
    record the stale story with a `reason` — that stops it costing a judgement
    call every week. Neither gate is closable for suppressions without breaking
    what suppressions are for.

    What is checkable is whether the claim behind the exemption is true. The
    receipt is built from the links in the digest itself, so a URL in it is a URL
    the reader was handed. An item carrying that URL and a suppression marker
    asserts two things that cannot both hold, and the receipt settles which one
    is wrong — with no second opinion about the item's merits, and nothing for a
    caller to elect.

    This does not make the markers a closed door. A caller who omits `--verified`
    entirely — legal when every item is a suppression, since none needs a
    receipt — is not checked here, and closing that would mean `add` reading the
    digest. What it does close is the useful version of the bypass: relabelling
    the items of a digest whose provenance was just refused, so `add` exits zero
    and the `&&` chain carries on to deliver it.
    """
    if not receipt:
        return
    suppressed = [i for i in items if not is_published(i)]
    if not suppressed:
        return

    verdicts = load_link_receipt(receipt)
    refused: list[str] = []
    for item in suppressed:
        url = canonical_url(item.get("url", ""))
        if url and url in verdicts:
            marker = "duplicate_of" if item.get("duplicate_of") else "reason"
            refused.append(f"  {item.get('url')}\n    cited in the checked digest, but recorded with {marker}")

    if refused:
        raise GateRefusal(
            f"refusing to record {len(refused)} of {len(suppressed)} suppressed item(s) — "
            f"their URLs are in {receipt}, so they were cited in the digest this run "
            "checked:\n"
            + "\n".join(refused)
            + "\n\nNothing was written and the run is not stamped. A suppression is an "
            "item the digest does not contain — recorded so its URL stops coming back, "
            "never one a reader was shown. `status` counts these as suppressed rather "
            "than published, so recording a published item this way also understates "
            "what the digest covered.\n"
            "If the item was published, record it as published and let the receipt "
            "vouch for it. If it should not have gone out, take it out of the digest, "
            "re-run the link check, and record it as a suppression then."
        )


def cmd_status(args) -> int:
    items = read_ledger(args.profile)
    state = read_state(args.profile)
    beats: dict[str, int] = {}
    suppressed = 0
    for i in items:
        # Entries carrying either marker were recorded so their URLs never
        # come back, not because they were published. Counting them as coverage
        # would overstate what the reader actually saw.
        if i.get("duplicate_of") or i.get("reason"):
            suppressed += 1
            continue
        beats[i.get("beat") or "unfiled"] = beats.get(i.get("beat") or "unfiled", 0) + 1
    payload = {
        "profile": args.profile,
        "store": str(profile_dir(args.profile)),
        # Reported, never created or emptied here. This is the line a step reads
        # when it no longer has the path — which is the point of deriving it — and
        # `status` is also the command a run repeats to check its own work, so
        # touching the directory from here would delete the digest between
        # recording it and delivering it. `start-run` is the one that empties it.
        "run_dir": str(run_dir_for(args.profile)),
        "last_run": state.get("last_run", "never"),
        "last_window": state.get("last_window", ""),
        "interests": state.get("interests", ""),
        "runs": state.get("runs", 0),
        "items_published": len(items) - suppressed,
        "items_suppressed": suppressed,
        "by_beat": dict(sorted(beats.items(), key=lambda kv: -kv[1])),
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_start_run(args) -> int:
    """Empty and create this run's scratch directory, and print its path.

    A command of its own rather than a side effect of `status`, and that division
    is the whole of the design. The directory has to be emptied by something, and
    emptied once, at the top of the run — so the command that does it must be one
    a run has no reason to repeat. `status` is precisely the wrong candidate: it
    is read-only, it is the natural way to check the run's own work, and it is
    already suggested after `add` to confirm the recording landed. Clearing from
    there would delete the digest between recording it and delivering it.

    Nothing here touches the ledger or the state file. Scratch and history are
    separate concerns, and a run that restarts its scratch has not un-reported
    anything.
    """
    print(prepare_run_dir(args.profile))
    return 0


def cmd_since(args) -> int:
    print(read_state(args.profile).get("last_run", "never"))
    return 0


def cmd_new(args) -> int:
    candidates = items_from_flags(args)
    if candidates is None:
        candidates = load_items(args.input)
    win_start, win_end, win_source = resolve_window(args)
    seen = read_ledger(args.profile)

    seen_urls = {c for c in (canonical_url(i.get("url", "")) for i in seen) if c}
    cutoff = datetime.now(UTC) - timedelta(days=LOOKBACK_DAYS)
    recent_titles = [
        (title_tokens(i.get("title", "")), i)
        for i in seen
        if (parse_iso(i.get("recorded_at", "")) or cutoff) >= cutoff and i.get("title")
    ]

    fresh: list[dict] = []
    dropped: list[dict] = []
    batch_urls: set[str] = set()
    batch_titles: list[tuple[frozenset[str], dict]] = []

    hinted = 0
    stale: list[dict] = []
    excepted = 0
    undated = 0
    for item in candidates:
        # The window is checked before deduplication, not after, so an item the
        # window rejects cannot claim a URL or a headline in the batch and thereby
        # suppress a legitimate in-window write-up of the same story as a
        # "duplicate within this batch".
        verdict, note = window_check(item, win_start, win_end)
        if verdict == "out":
            stale.append({**item, "_out_of_window": note})
            continue

        url = canonical_url(item.get("url", ""))
        tokens = title_tokens(item.get("title", ""))
        dup_of = None
        hints: list[dict] = []

        if url and url in seen_urls:
            dup_of = "already reported (same url)"
        elif url and url in batch_urls:
            dup_of = "duplicate within this batch (same url)"
        else:
            # Rank every prior title rather than stopping at the first match, so
            # a near-miss can still be reported back as a hint.
            scored = sorted(
                ((jaccard(tokens, pt), prior) for pt, prior in recent_titles + batch_titles),
                key=lambda pair: -pair[0],
            )
            if scored and scored[0][0] >= TITLE_MATCH_THRESHOLD:
                dup_of = f"same story as: {scored[0][1].get('title', '')[:80]}"
            elif not args.no_hints:
                hints = [
                    {"title": prior.get("title", "")[:100], "similarity": round(score, 2)}
                    for score, prior in scored[:MAX_HINTS]
                    if score >= SUGGEST_THRESHOLD
                ]

        if dup_of:
            dropped.append({**item, "_dup_of": dup_of})
            continue

        if url:
            batch_urls.add(url)
        if tokens:
            batch_titles.append((tokens, item))

        kept = dict(item)
        if verdict == "excepted":
            excepted += 1
            kept["_window_exception"] = note
        elif verdict == "undated":
            undated += 1
            kept["_date_unknown"] = note
        if hints:
            hinted += 1
            kept["_maybe_same_as"] = hints
        fresh.append(kept)

    if args.verbose:
        print(
            json.dumps(
                {"new": fresh, "skipped": dropped, "out_of_window": stale},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps(fresh, indent=2, ensure_ascii=False))
    if not args.quiet:
        # The window is named on every run, whether or not it rejected anything.
        # A window derived from the wrong place is the failure this gate cannot
        # catch for itself, so it is stated where the caller will see it.
        lines = [f"window {win_start} .. {win_end} (from {win_source})"]
        note = f", {hinted} flagged as possibly already covered — check _maybe_same_as" if hinted else ""
        lines.append(
            f"{len(fresh)} new, {len(dropped)} filtered (already reported or duplicate coverage){note}"
        )
        if stale:
            lines.append(
                f"{len(stale)} dropped as out of window — listed under out_of_window with -v; "
                "to keep one, add a documented window_exception and run this again"
            )
        if excepted:
            lines.append(
                f"{excepted} kept outside the window on a stated exception — the digest must say so"
            )
        if undated:
            lines.append(
                f"{undated} kept with no usable date — establish it when you fetch, or drop the item; "
                "an undated item is not checked against the window"
            )
        print("\n".join(lines), file=sys.stderr)
    return 0


def cmd_add(args) -> int:
    items = items_from_flags(args)
    if items is None:
        items = load_items(args.input)
    # Both gates run before anything is written: a refusal must leave the profile
    # exactly as it was. The window is resolved from `last_run`, which this call
    # is about to advance — reading it first is what makes `add` judge against
    # the same window `new` used at Step 3 rather than a window of zero days.
    published = [i for i in items if is_published(i)]
    # A gate that refuses leaves the ledger and `last_run` untouched, which is
    # what makes the call retryable — but it also leaves the profile looking
    # exactly like one that has not run yet, and `record-run` cannot tell those
    # apart. So a refusal is remembered. This writes no item and does not move
    # the clock; it only records that a run got this far and recorded nothing.
    #
    # Only GateRefusal is caught, and only the four sites that judge items raise
    # it. The gates raise plain SystemExit for a dozen operational faults too —
    # an unreadable or unparseable receipt above all — and catching those here
    # latched a provenance verdict on items no gate had looked at. Those now
    # propagate: the run fails, loudly and with the file named, and the profile
    # is untouched, which is what an operational fault deserves.
    try:
        check_provenance(published, args.verified)
        check_suppressions(items, args.verified)
        win_start, win_end, win_source = resolve_window(args)
        undated = check_window_at_add(published, win_start, win_end, win_source)
    except GateRefusal:
        mark_refused(args.profile, len(published))
        raise

    state = read_state(args.profile)
    try:
        runs = int(state.get("runs", 0))
    except (TypeError, ValueError):
        raise SystemExit(f"state.json has a non-numeric 'runs' value: {state.get('runs')!r}") from None
    stamp = now_iso()
    entries = []
    for item in items:
        url = item.get("url", "")
        entries.append(
            {
                "url": url,
                "canonical_url": canonical_url(url),
                "title": item.get("title", ""),
                "beat": item.get("beat", ""),
                "date": item.get("date", ""),
                "source": item.get("source", ""),
                "why": item.get("why", ""),
                # Both are set only on entries that were seen and deliberately
                # not published. Recording them means the URL is suppressed by
                # exact match forever, instead of having to be recognised again
                # by judgement every week.
                #
                # duplicate_of names the story this one restates. reason covers
                # every other ground for exclusion — most often an item that is
                # correctly out of window, which is not a duplicate of anything
                # and would otherwise resurface in every future sweep.
                "duplicate_of": item.get("duplicate_of", ""),
                "reason": item.get("reason", ""),
                # Stored, not merely accepted: an entry dated outside the window
                # it was published in reads as a mistake, and this is the line
                # that says it was a decision and which of the three it was.
                "window_exception": item.get("window_exception", ""),
                "recorded_at": stamp,
            }
        )
    append_ledger(args.profile, entries)

    state["last_run"] = stamp
    state["runs"] = runs + 1
    if args.window:
        state["last_window"] = args.window
    # This write is the recovery: whatever was refused earlier has now been
    # recorded, either fixed or as a suppression, so the block on `record-run`
    # goes with it. Clearing it anywhere else would make the block advisory.
    state.pop("refused_at", None)
    state.pop("refused_items", None)
    write_state(args.profile, state)

    print(f"recorded {len(entries)} items; last_run = {stamp}")
    # The window is named on every add, as it is on every `new`, because a window
    # silently derived from the wrong place is the one failure this gate cannot
    # catch for itself.
    summary = [f"window {win_start} .. {win_end} (from {win_source})"]
    if undated:
        summary.append(
            f"{len(undated)} recorded with no usable date, so unchecked against the window:"
        )
        summary.extend(undated)
    print("\n".join(summary), file=sys.stderr)
    return 0


def cmd_record_run(args) -> int:
    """Stamp a run that found nothing worth reporting, so the window still advances.

    "Reported nothing" and "failed to record what it reported" both leave the
    ledger empty, and only the first is a reason to advance the clock. Stamping
    after a refusal is worse than not stamping at all: `last_run` becomes today,
    so the next run derives a window of a single day and drops as out-of-window
    the very items the refused digest already covered. The failure is invisible
    at the point it happens and surfaces a week later as an empty sweep.

    So this refuses while a refusal is outstanding. The key is the marker `add`
    leaves, not the item count or the clock — those look identical either way.
    """
    state = read_state(args.profile)
    if state.get("refused_at"):
        raise SystemExit(
            f"refusing to stamp this profile — an `add` was refused at "
            f"{state['refused_at']} and {state.get('refused_items', 0)} published "
            "item(s) went unrecorded.\n"
            "`record-run` is for a run that reported nothing, and this run reported "
            "something it could not record. Stamping now would set last_run to "
            "today, leaving the next run a one-day window that drops everything "
            "this digest covered.\n"
            "Fix what the refusal named and run `add` again. If those items are "
            "correctly not going out, record them as suppressions with a `reason` "
            "— that is still an `add`, it stops them resurfacing every sweep, and "
            "it clears this."
        )
    state["last_run"] = now_iso()
    state["runs"] = int(state.get("runs", 0)) + 1
    write_state(args.profile, state)
    print(state["last_run"])
    return 0


def cmd_config(args) -> int:
    """Read or set the profile's standing interests.

    Interests are stable per reader but tedious to restate every run, which is
    the one thing that reliably kills them: a note you must retype weekly is a
    note you stop typing, and every digest quietly reverts to generic. Storing
    them per profile keeps the skill itself generic and shareable — this is the
    reader's state, not the skill's configuration.
    """
    state = read_state(args.profile)
    if args.clear:
        state.pop("interests", None)
        write_state(args.profile, state)
    elif args.interests is not None:
        state["interests"] = args.interests.strip()
        write_state(args.profile, state)
    print(
        json.dumps(
            {"profile": args.profile, "interests": state.get("interests", "")},
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


def cmd_recent(args) -> int:
    if args.days < 0:
        raise SystemExit("--days cannot be negative")
    cutoff = datetime.now(UTC) - timedelta(days=min(args.days, 36500))
    out = [
        i
        for i in read_ledger(args.profile)
        if (parse_iso(i.get("recorded_at", "")) or cutoff) >= cutoff
        and (not args.beat or i.get("beat") == args.beat)
    ]
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


def cmd_forget(args) -> int:
    target = canonical_url(args.url)
    before = read_ledger(args.profile)
    # new() recomputes the canonical form from `url`; matching only the stored
    # canonical_url field left hand-edited or imported entries permanently
    # suppressed yet unforgettable, with forget reporting success.
    kept = [
        i
        for i in before
        if (i.get("canonical_url") or canonical_url(i.get("url", ""))) != target
    ]
    with ledger_path(args.profile).open("w", encoding="utf-8") as fh:
        for i in kept:
            fh.write(json.dumps(i, ensure_ascii=False) + "\n")
    print(f"removed {len(before) - len(kept)} entries for {target}")
    return 0


_ITEM_FORMS = """
Three ways to pass items, pick whichever you already have. All three carry the
same fields; only `url` is required:

  one item, no JSON:
    ledger.py add --url https://example.com/x --title "..." --beat inference \\
                  --date 2026-08-04 --source Example --why "1.8x on B200"
  inline JSON:
    ledger.py add --items '[{"url": "...", "title": "...", "beat": "..."}]'
  a file of item JSON, or stdin:
    ledger.py add --input reported.json

--input reads JSON, not prose: a rendered Markdown digest is rejected.
The profile is a flag too — ledger.py --profile work add ..., never
ledger.py work add ...

`add` also needs --verified link-check.json whenever any item is being recorded
as published; see `add --help`.
"""


# Spelled out on the subcommands that consume items, because `add --help` is
# where a caller who has already guessed wrong looks next, and the top-level
# description does not reach them there.
_ITEM_DESCRIPTION = """\
Items are JSON. Pass them inline with --items, as single-item flags
(--url/--title/...), or as a file of item JSON with --input; with none of
those, item JSON is read from stdin.

--input names a file containing a JSON list of item objects (or an object
with an "items" key) — the same shape the sweep collected. It is not a place
to pass the rendered digest: a Markdown file fails with "input is not valid
JSON", exits non-zero, and records nothing.

  [{"url": "...", "title": "...", "beat": "...", "date": "2026-07-30",
    "source": "...", "why": "one line on why it mattered"}]

Only `url` is required; the ledger suppresses by URL, so an item without one
matches nothing later.\
"""


# Only on `add`, which is the only command that writes a published entry.
_PROVENANCE_DESCRIPTION = """\

Provenance
----------
An item recorded as published must have a URL this run checked and found usable.
Pass --verified with the receipt the link check wrote:

  check_links.py digest.md --retrieved retrieved-urls.txt --json > link-check.json
  ledger.py --profile <profile> add --input reported.json \\
            --verified link-check.json --window 7d

Verdicts of OK and BLOCKED are usable — BLOCKED means the site refused an
automated request, which is common and not a defect in the link. BROKEN and
UNSOURCED are not, and neither is a URL absent from the receipt altogether: that
means the digest that was checked did not cite it, which is what happens when an
item is introduced after the check, or the check ran against a stale file.

A receipt written without --retrieved is rejected outright. Reachability alone
is exactly the check a fabricated URL passes.

The window is checked here too, against the same window `new` used — derived
from this profile's last run, which this call has not advanced yet, and
overridable with the same --window-start / --window-end. `new` filters its own
stdout, but nothing made the published set a subset of that, so an item
introduced after Step 3 reached the ledger unchecked. One did: dated twelve days
before the window, on a run whose `new` call reported no drops at all. An item
outside the window survives on a documented `window_exception`, the same three
codes `new` accepts. A missing or unreadable date is kept and reported, again as
in `new`, because Step 4 is where a date gets established.

Unlike the window filter on `new`, both of these refuse rather than filter, and
exit non-zero: the digest already exists by the time `add` runs, so quietly
dropping an item would leave it published and unrecorded. Nothing is written and
the run is not stamped, so `add && deliver` correctly stops before delivery.

Entries carrying duplicate_of or reason were never shown to anyone and are exempt
from both checks — --verified may be omitted entirely when every item is one of
those, and an out-of-window item recorded with a `reason` is the documented way
to stop it resurfacing in every future sweep.\
"""


# Only on `new`, which is the only command that applies the window.
_WINDOW_DESCRIPTION = """\

The window
----------
`new` also drops candidates dated outside the window the digest covers, because
a digest headed with one window and filled from another is wrong in the way
readers notice first. The window needs no flag: it runs from this profile's
`last_run` to today, or the last 7 days when the profile has never run. Pass
--window-start / --window-end only when the ask names a different span
("this month", "since CES"). The window used is printed on stderr every run.

The boundary is soft, so this is not a refusal. An item outside the window is
kept if it names one of three documented boundary cases in a `window_exception`
field, and the digest then has to say which:

  straddles-window    the event spans the window start — a multi-day conference,
                      an embargo that lifted the evening before
  still-live          announced just before the window, but its deadline, launch
                      or effect lands inside it
  first-run-context   predates the window, load-bearing on a first run, and the
                      digest says that it predates the window

Any other value is treated as no exception at all. Older news in fresh coverage
has no code on purpose: it is dated by when the event happened, not by when
someone wrote about it again, and a recap of an old announcement is the thing
this gate exists to stop.

An item whose `date` is missing or unreadable is kept, annotated `_date_unknown`
and counted, never silently dropped — a candidate may legitimately arrive
undated and have its date established when it is fetched. It is also not checked
against the window, so leaving the field blank is not a way past this.

Exit status is unaffected by any of it: an out-of-window candidate is a filtered
candidate, not a failed run, so `new && ...` still chains.\
"""


def _teach_item_forms(parser: argparse.ArgumentParser) -> None:
    """Make malformed item calls answer with the forms that do work.

    Bare positional arguments are the most common wrong guess at this interface.
    argparse rejects them with "unrecognized arguments" and nothing else, which
    says what failed but not what to do instead, so a caller that guessed wrong
    has nothing to correct towards. Unknown positionals surface on the top-level
    parser rather than the subparser, hence the argv check.
    """
    original = parser.error

    def error(message: str):
        if "unrecognized arguments" in message and {"add", "new"} & set(sys.argv[1:]):
            parser.exit(2, f"{parser.prog}: error: {message}\n{_ITEM_FORMS}")
        original(message)

    parser.error = error  # type: ignore[method-assign]


def _add_global_arguments(parser: argparse.ArgumentParser, *, top_level: bool) -> None:
    """Accept --profile and --home before *or* after the subcommand.

    Registered only on the top-level parser, these read as global options while
    argparse rejects them anywhere after the subcommand, and the error says
    merely "unrecognized arguments" without naming the position that would
    work. Since every documented example writes the subcommand first, putting
    the flag after it is the natural guess, and recovering from the rejection by
    dropping the flag is a likelier reading than moving it -- which silently
    writes to the default profile, the one case where being wrong is worse than
    failing.

    On the subparsers the defaults are suppressed, so an omitted flag leaves
    whatever the top-level parser resolved and only an explicit one overrides.
    """
    profile_kwargs = {"default": "default"} if top_level else {"default": argparse.SUPPRESS}
    home_kwargs = {"default": None} if top_level else {"default": argparse.SUPPRESS}
    parser.add_argument(
        "--profile",
        help="separate watch list (default: default)",
        **profile_kwargs,  # type: ignore[arg-type]
    )
    parser.add_argument(
        "--home",
        help="store root; outranks AI_NEWS_HOME, XDG_STATE_HOME and the default",
        **home_kwargs,  # type: ignore[arg-type]
    )


def _add_item_arguments(parser: argparse.ArgumentParser) -> None:
    """Attach the inline item forms to a subcommand that consumes items."""
    parser.add_argument("--items", help="items as an inline JSON list or object")
    for field in _ITEM_FIELDS:
        parser.add_argument(f"--{field.replace('_', '-')}", dest=field, help=f"single item: {field}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    _add_global_arguments(p, top_level=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_parser(name: str, **kwargs) -> argparse.ArgumentParser:
        """Every subcommand takes the global flags too, in either position."""
        parser = sub.add_parser(name, **kwargs)
        _add_global_arguments(parser, top_level=False)
        return parser

    add_parser("status", help="last run, counts, beat breakdown, run dir").set_defaults(fn=cmd_status)
    add_parser(
        "start-run",
        help="empty and print this run's scratch directory",
        description=cmd_start_run.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    ).set_defaults(fn=cmd_start_run)
    add_parser("since", help="print last-run timestamp").set_defaults(fn=cmd_since)

    s = add_parser(
        "new",
        help="filter candidates down to unseen, in-window items",
        description=_ITEM_DESCRIPTION + _WINDOW_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("--input", "-i", help="file of item JSON, not a digest (default: stdin)")
    _add_item_arguments(s)
    s.add_argument(
        "--window-start",
        help="first day the digest covers, YYYY-MM-DD "
        "(default: this profile's last run, or 7 days back if it has never run)",
    )
    s.add_argument("--window-end", help="last day the digest covers, YYYY-MM-DD (default: today, UTC)")
    s.add_argument("--verbose", "-v", action="store_true", help="also show what was dropped and why")
    s.add_argument("--quiet", "-q", action="store_true", help="suppress the summary line")
    s.add_argument(
        "--no-hints",
        action="store_true",
        help="do not annotate kept items with _maybe_same_as (byte-identical passthrough)",
    )
    s.set_defaults(fn=cmd_new)

    s = add_parser(
        "add",
        help="record reported items and stamp the run",
        description=_ITEM_DESCRIPTION + _PROVENANCE_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    s.add_argument("--input", "-i", help="file of item JSON, not a digest (default: stdin)")
    s.add_argument("--window", help="free-text label for the window this run covered, e.g. '7d'")
    s.add_argument(
        "--verified",
        metavar="FILE",
        help="receipt from check_links.py --json for this run's digest; required "
        "to record anything as published",
    )
    # Spelled the same as on `new` and resolved by the same function. A run told
    # to cover "since CES" passes them there; if `add` could not be told the same
    # thing it would refuse every item that run published.
    s.add_argument(
        "--window-start",
        help="first day the digest covered, YYYY-MM-DD "
        "(default: this profile's last run, or 7 days back if it has never run)",
    )
    s.add_argument("--window-end", help="last day the digest covered, YYYY-MM-DD (default: today, UTC)")
    _add_item_arguments(s)
    s.set_defaults(fn=cmd_add)

    add_parser(
        "record-run",
        help="stamp a run that reported nothing",
        description=cmd_record_run.__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    ).set_defaults(fn=cmd_record_run)

    s = add_parser("config", help="read or set this profile's standing interests")
    s.add_argument("--interests", help="a line or two on what this reader works on")
    s.add_argument("--clear", action="store_true", help="remove stored interests")
    s.set_defaults(fn=cmd_config)

    s = add_parser("recent", help="dump recently reported items")
    s.add_argument(
        "--days",
        type=int,
        default=LOOKBACK_DAYS,
        help=f"how far back to look (default: {LOOKBACK_DAYS}, matching the dedup window)",
    )
    s.add_argument("--beat")
    s.set_defaults(fn=cmd_recent)

    s = add_parser("forget", help="drop a mis-recorded item")
    s.add_argument("--url", required=True)
    s.set_defaults(fn=cmd_forget)

    _teach_item_forms(p)
    args = p.parse_args()
    set_home_override(args.home)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
