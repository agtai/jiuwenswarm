#!/usr/bin/env python3
"""Render the digest report from the run's own numbers and the model's findings.

The division of labour is the point of this script. Everything a report says
about *how much* happened is read here, from the file the fetcher wrote, and can
therefore only ever be what the run actually measured. Everything a report says
about *what it means* -- which changes mattered, which way a theme is moving,
what to do about it -- is judgement, arrives as ``--findings`` JSON, and is the
only part a model writes.

That split exists because the other arrangement was tried and does not hold. A
report composed freely from a summary varies in section set, in section order,
in header shape and in its numbers, from one day to the next, with nothing
having changed but the run; and the numbers are the part that fails silently,
because an invented count is indistinguishable from a measured one once it is in
the text. Findings JSON has no field for a count, so there is nowhere to put one.

The section set is fixed here for the same reason the numbers are. Every section
is written on every run: one that has nothing says so in a line of its own,
because a section that simply disappears cannot be told apart from one nobody
filled in, and consecutive runs over the same window were observed dropping and
restoring three of them with the measured activity unchanged. What varies
between two reports should be what the runs found, never which questions were
asked.

Re-rendering is free and consumes nothing: the watermark moved when the fetcher
ran. A run whose findings fail a check should fix the findings and render again,
never abandon the report -- see ``--check-language``.

Two kinds of problem can be found here, and they are treated differently on
purpose. A *structural* problem means there is nothing worth rendering: activity
that is not a fetcher run, a findings file in some other schema, a report with no
judgement in it at all. Those refuse, because the alternative is a document that
is wrong or empty while looking finished.

A *content-quality* problem means the report is fine except that one item falls
short of a rule the report makes for itself -- a conclusion published without its
evidence link, an item with no title, a severity outside its vocabulary. Those no
longer refuse. Refusing converted one weak line into no report at all, which is
strictly worse for the reader, and it did not even buy a corrected findings file:
the observed outcome was the same render command reissued byte-identically until
the host ended the run, or a report composed outside this script entirely. The
rule is kept and made visible instead -- the item renders with a mark where it
falls short, and every shortfall is listed under *Reporting Shortfalls*. Nothing
a writer can put in the findings adds to that section, edits it or empties it,
which is the property that keeps it a check rather than a suggestion.

A third kind sits between them and is treated as content quality: content that
arrived under a name nothing here reads. It is not structural -- the report is
deliverable and the rest of the item is intact -- but it is not an ordinary
shortfall either, because what goes missing is not a rule the writer skipped,
it is material the writer supplied and this file threw away. Two rules follow
from that. Nothing is ever read from a name the schema does not define, however
obvious the intent, because a second name for a field is how the mistake becomes
permanent; and every populated name that is not read is named in the report, so
that the loss is visible in the run that caused it rather than in none.

A fourth kind is neither, and is dropped rather than published or refused:
content the writer did not write. The fetch's ``template`` ships one worked
example per key, so that a writer can see what an item's fields are called
instead of guessing, and every value in it carries a marker. A finding still
carrying that marker is content nobody asserted, which no mark can make true and
which is not grounds for losing the findings around it -- so the entry is
removed, the removal is listed under *Reporting Shortfalls*, and the report is
delivered without it. See ``_clear_placeholders``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SEVERITY_MARKS = {
    "critical": "\U0001f534",
    "major": "\U0001f7e0",
    "stable": "\U0001f7e2",
}
_DIRECTION_MARKS = {
    "rising": "↑ Rising",
    "stable": "→ Stable",
    "cooling": "↓ Cooling",
}
_LABELS = {
    "fact": "FACT",
    "inference": "INFERENCE",
    "recommendation": "RECOMMENDATION",
}
_CONFIDENCE = {"high": "High", "medium": "Medium", "low": "Low"}
_THREAD_MARKER = "<!-- jiuwenswarm:slack-thread-details -->"

# Put where a report falls short of its own rules. It marks the item in place, so
# a reader meets the shortfall where the weak claim is rather than only in a list
# at the end, and it is the same mark in every section so one glance identifies
# it. It is written by this file alone; no findings field produces it.
_WARN = "⚠️"

# Every top-level key the findings file may carry. Named here so a file that
# shares none of them can be told apart from one that is merely incomplete: the
# two need opposite advice, and giving the first the second's message is what
# sends a run off to write its own report instead.
_FINDINGS_KEYS = (
    "tldr",
    "significant_changes",
    "risks",
    "actions",
    "trends",
    "missing_capabilities",
    "opportunities",
    "evidence_gaps",
)

# The keys each kind of item is read for. ``_check_findings_shape`` refuses a
# file that puts content under an unrecognised *top-level* key, because content
# going unread in silence is the failure mode; it does not look inside an item,
# and the same defect one level down was unguarded. The observed instance was an
# evidence url written as ``link`` on a significant change: nothing read it, and
# the item then reported itself as carrying no evidence at all -- a diagnosis
# that points away from its own cause, which is worse than plain absence.
#
# The scalar/collection distinction the top-level check makes does not hold
# here. Up there a stray scalar is a note a writer kept for itself beside eight
# keys that hold the content; down here the scalar *is* the content -- a title,
# a sentence, a url -- so any populated value under an unread name is a loss and
# is reported as one. The cost is a shortfall line for a bookkeeping field
# somebody hung on an item; the cost of the other choice is this defect.
_TLDR_KEYS = ("severity", "text", "original")
_CHANGE_KEYS = ("title", "label", "text", "original", "evidence")
_RISK_KEYS = ("severity", "text", "original", "evidence")
_ACTION_KEYS = ("text", "original")
_TREND_KEYS = ("theme", "direction", "text", "original", "confidence", "evidence")
_CAPABILITY_GROUPS = ("explicit", "inferred", "insufficient")
_CAPABILITY_KEYS = {
    "explicit": ("text", "original"),
    "inferred": ("text", "original", "confidence"),
    "insufficient": ("text", "original"),
}
_OPPORTUNITY_KEYS = (
    "title",
    "kind",
    "user_value",
    "research_value",
    "effort",
    "risk",
    "recommendation",
)
_GAP_GROUPS = ("known", "unknown", "needed")
_GAP_KEYS = ("text", "original")
_EVIDENCE_KEYS = ("label", "url")

# A key name is caller text, and *Reporting Shortfalls* is otherwise written in
# this file's own words. Names are printed because naming the key is the whole
# of the fix -- but only names that cannot be anything except a name: no path,
# no link syntax, no newline, and nothing long enough to bury the sentence
# around it. A name that does not qualify is counted rather than quoted, so a
# hostile or malformed key cannot reach the channel and cannot make the report
# refuse itself on the path check either.
_KEY_NAME_RE = re.compile(r"\A[A-Za-z0-9_.\-]{1,40}\Z")

# Enough to tell "the evidence is here under the wrong name" from "there is no
# evidence". Read for the diagnosis only; see ``_misplaced_evidence``.
_URL_IN_VALUE_RE = re.compile(r"https?://")

# The marker every value in the fetch's ``template`` carries, and the one string
# this file will not publish under any circumstances.
#
# The template ships a worked example per key because eight empty arrays named
# the sections and never named a field inside one, and runs were observed
# inventing a whole item vocabulary instead of opening the schema reference. That
# fix is only safe if an example cannot become a finding, and the item-level
# unread-key check does not make it safe: a copied example sits under a key this
# file *does* read, so it passes every check and renders as though somebody meant
# it. The worst failure this skill has recorded was exactly that shape --
# per-theme figures copied out of a template and published as measured.
#
# The marker is on each value rather than on the item, because the granularity
# has to match the mistake. A writer fills an example in field by field, so a
# flag on the item would still be there once the content is entirely real, and
# discarding that item would cost a genuine finding. A value still carrying the
# marker is a value nobody wrote, whatever else on the item they did write.
#
# It is a literal rather than a pattern for the same reason: it has to be
# recognisable after a writer has edited the sentence around it, and it has to be
# impossible to hit by accident. No sentence about a repository contains it.
_PLACEHOLDER = "PLACEHOLDER-REPLACE-THIS"

# The brief is the part that lands in the channel; everything after the marker
# lands in its thread. Slack's own section limit is 3000 characters, and the
# connector splits above that, so a brief kept under this never depends on where
# a splitter happened to cut.
_BRIEF_BUDGET = 2800

# A path is input. It tells a reader nothing they can act on and it publishes
# the host's directory layout to whoever can see the channel, so no rendered
# line may carry one -- including one that arrived inside a finding.
_PATHISH_RE = re.compile(r"(?:(?<=\s)|\A)(?:~|\.{1,2})?/[^\s<>|]*/[^\s<>|]*")
_WINDOWS_PATHISH_RE = re.compile(r"[A-Za-z]:\\\\[^\s<>|]+")


class RenderError(Exception):
    """A structural problem: there is nothing here worth rendering.

    Raising ends the render. Reserved for the cases where the alternative is a
    document that is wrong or empty while looking finished -- not for an item
    that falls short, which is what ``_Shortfalls`` is for.
    """


class _EvidenceProblem(Exception):
    """One evidence reference that cannot be rendered as a link.

    Local to the evidence line: it is caught where it is raised, the reference is
    dropped, and the shortfall is recorded. It is deliberately not a
    ``RenderError``, so that a reference nobody can follow costs its own line and
    not the whole report.

    ``carried_url`` says whether the reference had a url that simply was not
    under ``url``, and ``misplaced`` names the keys it was under when they can be
    named. Neither is used to render the url -- the reference is dropped either
    way -- but the mark left in its place has to state which of the two happened.
    Saying "no evidence link" over a reference that carried one is the same false
    diagnosis as saying it over an item that carried one.
    """

    def __init__(
        self,
        message: str,
        *,
        carried_url: bool = False,
        misplaced: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.carried_url = carried_url
        self.misplaced = misplaced or []


class _Shortfalls:
    """Where the report falls short of its own rules, collected rather than raised.

    One instance per render. Every entry names the item it belongs to, so a
    reader can find it and a writer can fix it; nothing here is reachable from
    the findings, so a run cannot silence a shortfall by writing anything -- and
    a check that can be silenced is not a check.

    Entries carry no text the caller supplied, with two exceptions, both of them
    identifiers rather than prose. One is the name a trend signal gave itself,
    which is how a reader finds the signal and is already printed in the section
    above. The other is the name of a key the renderer did not read, which is the
    whole of that shortfall -- a note that will not say which key is a note
    nobody can act on -- and which is filtered to something that cannot be
    anything but a key name before it is printed. Everything else is this file's
    own wording, so the section cannot become a second route into the report for
    material the rest of the renderer would have refused.
    """

    def __init__(self) -> None:
        self.items: list[str] = []

    def note(self, where: str, problem: str) -> None:
        self.items.append(f"{where}: {problem}")

    def __len__(self) -> int:
        return len(self.items)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _quoted(names: Any) -> str:
    return ", ".join(f"`{name}`" for name in sorted(names))


def _unread(entry: Any, known: tuple[str, ...]) -> tuple[dict[str, Any], int]:
    """Return the populated keys of one item that nothing in this file reads.

    Split into the ones safe to name and a count of the rest, because the names
    are published and the shortfall section publishes no unfiltered caller text.
    """
    if not isinstance(entry, dict):
        return {}, 0
    named: dict[str, Any] = {}
    unnamed = 0
    for key, value in entry.items():
        if key in known or not value:
            continue
        if isinstance(key, str) and _KEY_NAME_RE.match(key):
            named[key] = value
        else:
            unnamed += 1
    return named, unnamed


def _holds_url(value: Any) -> bool:
    try:
        return bool(
            _URL_IN_VALUE_RE.search(json.dumps(value, ensure_ascii=False, default=str))
        )
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False


def _misplaced_evidence(entry: Any, known: tuple[str, ...]) -> list[str]:
    """Name the unread keys carrying a url on an item whose ``evidence`` is empty.

    Read for the diagnosis and never for the report. Rendering the url would be
    accepting a second name for ``evidence``, and two names for one field is how
    this survived: once the link prints, the report looks finished and only the
    writer's own diligence ever moves it. It also cannot be done truthfully. A
    url under some other key need not be evidence for the sentence beside it --
    a homepage, an avatar, a link the writer was quoting -- and publishing one
    under "Evidence:" asserts a backing nobody claimed, which trades one false
    statement for another. So the url is found, named, and left where it is: the
    reader is told the evidence was not read, instead of being told the
    conclusion is unverified, which was the false part.
    """
    if not isinstance(entry, dict) or _as_list(entry.get("evidence")):
        return []
    named, _unnamed = _unread(entry, known)
    return sorted(key for key, value in named.items() if _holds_url(value))


def _note_unread(
    entry: Any,
    known: tuple[str, ...],
    *,
    where: str,
    shortfalls: _Shortfalls,
    explained: list[str] | tuple[str, ...] = (),
) -> None:
    """Record content this item carries under a name the renderer does not read.

    The structural half of the fix, and the half that catches the next one:
    it names no field in particular, so a `link`, a `summary`, a `url_` and
    whatever comes after them are all reported the same way, in the run that
    writes them, rather than being dropped in silence.

    ``explained`` is for keys a more specific note already named, so that one
    mistake costs one line.
    """
    if not isinstance(entry, dict):
        if entry:
            shortfalls.note(
                where,
                "arrived as something other than an object, so nothing in it is "
                "read; every part of a finding lives on an object with the keys "
                + _quoted(known),
            )
        return
    named, unnamed = _unread(entry, known)
    names = [key for key in named if key not in explained]
    if not names and not unnamed:
        return
    carried = []
    if names:
        carried.append(_quoted(names))
    if unnamed:
        carried.append(f"{unnamed} further key(s) whose names cannot be printed")
    shortfalls.note(
        where,
        "carries content under "
        + " and ".join(carried)
        + ", which this renderer does not read, so none of it appears in the "
        "report. The keys read here are "
        + _quoted(known)
        + "; see references/findings-schema.md",
    )


def _holds_placeholder(value: Any) -> bool:
    """Say whether anything anywhere in this value is still the template's text."""
    if isinstance(value, str):
        return _PLACEHOLDER in value
    if isinstance(value, dict):
        return any(_holds_placeholder(item) for item in value.values())
    if isinstance(value, list):
        return any(_holds_placeholder(item) for item in value)
    return False


def _drop_placeholders(value: Any, *, in_evidence: bool = False) -> tuple[Any, int, int]:
    """Return the value with every unwritten list entry removed, and how many went.

    Innermost first, so the two levels do not take each other's entries. An
    evidence reference left as the example is dropped from the item that carries
    it; the item itself survives on the strength of what its writer *did* write,
    and picks up the existing "no evidence link" mark. Only once its own values
    are clean is the item judged, so a real finding is never discarded for an
    example hanging off it.

    Returns ``(value, items, references)`` -- counted separately because the two
    are different mistakes to a writer, and one line that conflated them would
    send them looking in the wrong place.
    """
    items = 0
    references = 0
    if isinstance(value, list):
        kept: list[Any] = []
        for entry in value:
            cleaned, sub_items, sub_references = _drop_placeholders(entry)
            items += sub_items
            references += sub_references
            if _holds_placeholder(cleaned):
                if in_evidence:
                    references += 1
                else:
                    items += 1
                continue
            kept.append(cleaned)
        return kept, items, references
    if isinstance(value, dict):
        cleaned_map: dict[str, Any] = {}
        for key, entry in value.items():
            cleaned, sub_items, sub_references = _drop_placeholders(
                entry, in_evidence=(key == "evidence")
            )
            items += sub_items
            references += sub_references
            cleaned_map[key] = cleaned
        return cleaned_map, items, references
    return value, items, references


def _clear_placeholders(
    findings: dict[str, Any], shortfalls: _Shortfalls
) -> dict[str, Any]:
    """Remove every finding still carrying the template's example text.

    Neither of this file's two treatments fits, and saying why is what settles
    the behaviour. A *content-quality* problem is published with a mark: the
    writer meant the claim and fell short of a rule about how to state it, so the
    reader loses precision and never truth. A copied example is not that. Nobody
    asserted it. Publishing it with a mark beside it still publishes a sentence
    about the repository that no one wrote, wearing the format that is the whole
    reason a fabricated report was believed here in the first place -- and a mark
    cannot make an unasserted sentence true, it can only make it look reviewed.

    It is not *structural* either, which is why it does not refuse. One stray
    example beside four real findings is not "nothing worth rendering", and
    refusing over it is the trade this file already made once and reversed: it
    turned one weak line into no report at all, and bought a retry loop or a
    report composed outside this script rather than a corrected findings file.

    So the entry is neither published nor fatal. It is dropped, and the drop is
    named in the one section no findings key can reach. Nothing unwritten is
    published, the run still delivers everything it did write, and the wholesale
    case -- the template copied and left unfilled -- still refuses without a rule
    of its own, because dropping every entry leaves ``tldr`` empty and that
    refusal already exists and already says the right thing.

    Counted per key rather than per position: dropping an entry renumbers the
    ones after it, so a note naming "item 2" would point at an item that is now
    something else.
    """
    cleared: dict[str, Any] = {}
    for key, value in findings.items():
        cleaned, items, references = _drop_placeholders(value)
        cleared[key] = cleaned
        if key not in _FINDINGS_KEYS:
            continue
        if items:
            one = items == 1
            shortfalls.note(
                key,
                f"{items} {'entry' if one else 'entries'} "
                f"{'was' if one else 'were'} still the template's example text "
                f"and {'was' if one else 'were'} not published. An item nobody "
                "wrote is not a finding, and under a heading it reads exactly "
                "like one; replace the example with what this run found, or "
                "leave the key out",
            )
        if references:
            one = references == 1
            shortfalls.note(
                key,
                f"{references} evidence "
                f"{'reference was' if one else 'references were'} still the "
                "template's example link and "
                f"{'was' if one else 'were'} dropped; "
                + (
                    "the conclusion it belonged to is"
                    if one
                    else "the conclusions they belonged to are"
                )
                + " published without it",
            )
    return cleared


def _reject_placeholders(text: str) -> None:
    """Refuse a rendered report that still carries the template's marker anywhere.

    ``_clear_placeholders`` drops entries from the shapes the schema defines. A
    marker somewhere else -- a bare string where a list of items belongs, a value
    nested deeper than any item -- would be past it. This makes "no unwritten
    value reaches a reader" a property of the file rather than a property of the
    findings having arrived in the shape they were meant to.

    A refusal here and a drop there are the same policy, not two: the drop leaves
    a report that is honest without the entry, and reaching this point means
    there is no entry to drop and so no honest report to publish around it. It is
    also unreachable by any findings file that is in the schema at all, which is
    what a backstop should be.
    """
    if _PLACEHOLDER in text:
        raise RenderError(
            f"the rendered report still carries {_PLACEHOLDER}, which is the "
            "marker on every value in the fetch's `template`. Those values are "
            "examples of the shape, not findings: replace each one with what "
            "this run measured, or remove the entry. Nothing carrying that "
            "marker is published."
        )


def _reject_paths(text: str, *, where: str) -> str:
    """Refuse a rendered fragment that carries a filesystem path.

    A refusal rather than a strip: a finding that names a file is a finding
    written for the wrong reader, and quietly deleting the path would leave the
    sentence around it claiming something the reader cannot check.
    """
    for pattern in (_PATHISH_RE, _WINDOWS_PATHISH_RE):
        match = pattern.search(text)
        if match:
            raise RenderError(
                f"{where}: refusing to publish a filesystem path "
                f"({match.group(0)!r}). Paths are input; say what the reader "
                "can act on instead."
            )
    return text


def _link(evidence: Any, *, where: str, shortfalls: _Shortfalls) -> str:
    """Render one evidence reference as a Slack link.

    Slack's own link form is emitted rather than Markdown's because it is the
    one form that needs no conversion layer to be correct. A host may well
    convert ``[text](url)``; a report that depends on one doing so renders
    wrongly the first day it is delivered somewhere that does not, and it fails
    silently -- the reader sees bracket syntax and nothing reports an error.

    A reference with no followable url is dropped, not published: a link the
    reader cannot open is worse than the missing-evidence mark, because it looks
    like the guarantee was met. A reference whose *caption* is unusable keeps its
    url as the caption instead -- the url is the evidence and the caption is
    decoration, so there is no reason for the decoration to cost the reference.
    """
    item = _mapping(evidence)
    url = _text(item.get("url"))
    label = _text(item.get("label")) or url
    # The same defect one level further down, and the same rule: the reference
    # is still dropped -- ``url`` stays the only key read for it -- but the drop
    # is reported as what it is rather than as "no url", which would send a
    # writer looking for something they already wrote.
    misplaced = (
        []
        if url
        else sorted(
            key
            for key, value in _unread(item, _EVIDENCE_KEYS)[0].items()
            if _holds_url(value)
        )
    )
    if isinstance(evidence, dict):
        # A reference that is not an object gets the more specific message
        # below instead, so it is not also reported as a shape problem.
        _note_unread(
            evidence,
            _EVIDENCE_KEYS,
            where=where,
            shortfalls=shortfalls,
            explained=misplaced,
        )
    if not url:
        if misplaced:
            raise _EvidenceProblem(
                "an evidence reference carries its url under "
                + _quoted(misplaced)
                + " rather than `url`, which is the only key read for it, and "
                "was dropped",
                carried_url=True,
                misplaced=misplaced,
            )
        if not isinstance(evidence, dict):
            # A bare value in place of a reference object. Still dropped -- a
            # string is not a reference and there is no caption to render it
            # under -- but when it is a url the mark must not claim none was
            # gathered.
            raise _EvidenceProblem(
                "an evidence reference is a bare value rather than an object "
                "with `label` and `url`, and was dropped",
                carried_url=_holds_url(evidence),
            )
        raise _EvidenceProblem("an evidence reference carries no url and was dropped")
    if not url.startswith(("http://", "https://")):
        # Also the one place a `file://` reference could reach the channel: the
        # path detector runs on the assembled text and does not recognise one
        # behind a scheme. Dropped here, it never gets that far.
        raise _EvidenceProblem(
            "an evidence url is not http(s) and was dropped; the reference "
            "cannot be followed from the report"
        )
    if any(ch in url for ch in "<>|"):
        raise _EvidenceProblem(
            "an evidence url contains link syntax and was dropped"
        )
    if any(ch in label for ch in "<>|"):
        shortfalls.note(
            where,
            "an evidence label contained link syntax and was replaced by its url",
        )
        label = url
    return f"<{url}|{label}>"


def _evidence_line(
    evidence: Any,
    *,
    required: bool,
    where: str,
    shortfalls: _Shortfalls,
    misplaced: list[str] | tuple[str, ...] = (),
) -> str:
    """Render the evidence for one item, saying so in place when there is none.

    The rule that every important conclusion carries a link is kept, and no
    longer enforced by refusing the report. A conclusion that arrives without one
    is published carrying the mark, which is what the rule was for: the reader
    sees which claim is unverified, at the claim, and the run still delivers.

    ``misplaced`` names keys on the item that hold a url and are not read. It
    changes only what the mark *says*, never what is published: "no evidence
    link — this conclusion is unverified" is false when the evidence was gathered
    and simply landed under another name, and it is false in the direction that
    hurts, because the mark that exists to catch the mistake then points away
    from it. Both readers are misled by it -- one is told a verified conclusion
    is unbacked, the other is told to add a link they already added.
    """
    links: list[str] = []
    dropped = False
    dropped_url = False
    dropped_under: list[str] = []
    for item in _as_list(evidence):
        try:
            links.append(_link(item, where=where, shortfalls=shortfalls))
        except _EvidenceProblem as problem:
            shortfalls.note(where, str(problem))
            dropped = True
            dropped_url = dropped_url or problem.carried_url
            dropped_under.extend(problem.misplaced)
    if links:
        return "Evidence: " + " · ".join(links)
    if not required:
        return ""
    if dropped_url:
        # The shortfall is already recorded by the drop itself; only the mark
        # needs correcting. The key is named where there is one to name, because
        # "somewhere else on the reference" is not something a writer can act on.
        if dropped_under:
            under = sorted(set(dropped_under))
            return (
                f"{_WARN} Evidence not published — a reference carried its url "
                "under " + _quoted(under) + ", not `url`."
            )
        return (
            f"{_WARN} Evidence not published — a reference carried a url in a "
            "form this report does not read."
        )
    if misplaced and not dropped:
        one = len(misplaced) == 1
        shortfalls.note(
            where,
            ("a url arrived under " if one else "urls arrived under ")
            + _quoted(misplaced)
            + " rather than `evidence`, which is the only key evidence is read "
            "from; the conclusion is published without its link, and nothing under "
            + ("that key" if one else "those keys")
            + " appears in the report",
        )
        return (
            f"{_WARN} Evidence not published — "
            + ("a url arrived under " if one else "urls arrived under ")
            + _quoted(misplaced)
            + ", not `evidence`."
        )
    if not dropped:
        shortfalls.note(
            where,
            "no evidence link; every important conclusion carries one, and this "
            "one is published without it",
        )
    return f"{_WARN} No evidence link — this conclusion is unverified."


def _same_wording(rendering: str, original: str) -> bool:
    """Say whether a gloss would repeat the rendering instead of explaining it.

    Spacing and letter case are the two differences a reader cannot see the
    point of, so they are normalised away before comparing. Everything else --
    a translated title, a rephrased commit subject, an added clause -- is a
    difference worth showing, and keeps its gloss.
    """
    return " ".join(rendering.split()).casefold() == " ".join(original.split()).casefold()


def _gloss(entry: dict[str, Any]) -> str:
    """Append the source's own wording, in parentheses, when it differs.

    The order is fixed here rather than asked for, because the order is what the
    language gate checks and what a reader needs: the rendering first, the
    original after it.

    An ``original`` that repeats the rendering is dropped rather than printed.
    The word "original" tells a reader the two differ, so printing a sentence
    after itself asserts the one thing it disproves; and it is the common case
    rather than a rare one, because a writer with nothing to gloss fills the
    field with a copy far more readily than leaving it out. Dropping it also
    keeps the language gate honest: source text that reached the report
    untranslated now arrives at the gate unglossed, which is what it is, instead
    of hiding behind a parenthesis that looks like a rendering.
    """
    body = _text(entry.get("text"))
    original = _text(entry.get("original"))
    if not original or _same_wording(body, original):
        return body
    return f"{body} (原文：{original})" if _has_cjk(original) else (
        f"{body} (original: {original})"
    )


def _body(entry: dict[str, Any], *, where: str, shortfalls: _Shortfalls) -> str:
    """Return the item's own words, saying so when it brought none.

    The reason an empty one cannot simply be printed: every line in this report
    is a mark, a heading or a bracket followed by the writer's sentence, so an
    entry with no sentence renders as punctuation and nothing else. That reads as
    a rendering fault rather than as a missing finding, and a reader who takes it
    for one stops trusting the lines around it too.
    """
    text = _gloss(entry)
    if text:
        return text
    shortfalls.note(where, "no text; the item is published with nothing to say")
    return f"{_WARN} (nothing stated)"


def _has_cjk(text: str) -> bool:
    return any("㐀" <= ch <= "鿿" or "豈" <= ch <= "﫿" for ch in text)


def _severity(
    entry: dict[str, Any], *, default: str = "", where: str, shortfalls: _Shortfalls
) -> str:
    """Return the item's severity, or nothing when it stated one nobody knows.

    Falling back to the default was considered and rejected: it would print a
    green mark beside an item whose writer called it urgent, which is a wrong
    answer that looks like a measured one. An unrated item is marked as unrated.
    """
    value = _text(entry.get("severity")).lower()
    if not value:
        value = default
    if value and value not in _SEVERITY_MARKS:
        shortfalls.note(
            where,
            "severity is not one of "
            + ", ".join(sorted(_SEVERITY_MARKS))
            + "; the item is published unrated",
        )
        return ""
    return value


def _mark(severity: str) -> str:
    return _SEVERITY_MARKS.get(severity, _WARN)


def _label(
    entry: dict[str, Any], *, default: str, where: str, shortfalls: _Shortfalls
) -> str:
    value = _text(entry.get("label")).lower() or default
    if value not in _LABELS:
        shortfalls.note(
            where,
            "label is not one of "
            + ", ".join(sorted(_LABELS))
            + "; the item is published unlabelled",
        )
        return f"{_WARN} UNLABELLED"
    return _LABELS[value]


# ------------------------------------------------------------------ the run


def _run_facts(activity: dict[str, Any]) -> dict[str, Any]:
    """Read everything the report states as measured, from the run's own file."""
    repository = _text(activity.get("repository"))
    generated = _text(activity.get("generated_at_utc"))
    if not repository or not generated:
        raise RenderError(
            "--activity is not a fetcher run: repository and generated_at_utc "
            "are both required"
        )
    try:
        stamp = datetime.fromisoformat(generated.replace("Z", "+00:00"))
    except ValueError as exc:  # pragma: no cover - defensive
        raise RenderError(f"generated_at_utc is not a timestamp: {generated!r}") from exc

    windows = _mapping(activity.get("windows"))
    coverage = _mapping(activity.get("coverage"))
    warnings = [_text(w) for w in _as_list(coverage.get("warnings")) if _text(w)]
    truncated = _mapping(activity.get("truncated"))
    state = _mapping(activity.get("state"))

    hours = _mapping(windows.get("daily")).get("requested_hours") or 24
    days = _mapping(windows.get("history")).get("days") or 30
    counts = _mapping(activity.get("window_counts"))

    # Items the run saw but did not deep-read. The deep-read sample is capped by
    # ``--detail-limit``, and on a busy day the remainder is most of the window;
    # a reader told nothing about it reads the inspected handful as the whole of
    # what was examined.
    omitted = coverage.get("daily_detail_candidates_omitted")
    detail_omitted = int(omitted) if isinstance(omitted, (int, float)) else 0

    # The run record is read, never asserted. A watermark that did not move, or
    # moved to a different instant than the data covers, means the next run will
    # re-report this window; that is a fact about the report and belongs in it.
    incomplete: list[str] = []
    if state and not state.get("written"):
        reason = _text(state.get("reason")) or "the watermark was not written"
        incomplete.append(f"Run not recorded: {reason}.")
    elif state and _text(state.get("last_success_utc")) != generated:
        incomplete.append(
            "Run not recorded against this window; the next report repeats it."
        )
    # ``catch_up_from_state`` is true whenever the window was widened at all,
    # and consecutive daily runs never start at the same second, so on a healthy
    # schedule it is set every day by a few seconds of drift. Reported as-is it
    # would put a "catching up" line in every report and teach its reader to
    # skip the line that matters on the day a run was actually missed. Report
    # the widening, not the flag, and only once it is larger than drift.
    widened = _widening_seconds(windows)
    if widened > 900:
        incomplete.append(
            f"Window widened by {_duration(widened)} to cover activity an "
            "earlier run did not report."
        )

    return {
        "repository": repository,
        "date": stamp.astimezone(timezone.utc).strftime("%Y-%m-%d"),
        "hours": _number(hours),
        "days": _number(days),
        "coverage": "partial" if warnings else "complete",
        "warnings": warnings,
        "truncated": truncated,
        "detail_omitted": detail_omitted,
        "counts": counts,
        "incomplete": incomplete,
    }


def _instant(value: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _widening_seconds(windows: dict[str, Any]) -> float:
    """Return how much wider the daily window is than the one that was asked for."""
    daily = _mapping(windows.get("daily"))
    start = _instant(daily.get("start_utc"))
    end = _instant(daily.get("end_utc"))
    try:
        requested = float(daily.get("requested_hours") or 0) * 3600.0
    except (TypeError, ValueError):
        return 0.0
    if start is None or end is None or requested <= 0:
        return 0.0
    return max(0.0, (end - start).total_seconds() - requested)


def _duration(seconds: float) -> str:
    hours = seconds / 3600.0
    if hours >= 1:
        return f"{hours:.1f}h"
    return f"{int(seconds // 60)}min"


def _number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _count(counts: dict[str, Any], window: str, key: str) -> int:
    value = _mapping(counts.get(window)).get(key)
    return int(value) if isinstance(value, (int, float)) else 0


# Which endpoint each measure is counted from. A measure is only as wide as the
# endpoint that fed it: GitHub paginates, the fetcher stops at --max-pages, and
# a count taken past that point is a count of what fitted, not of what happened.
_MEASURES: tuple[tuple[str, str, str], ...] = (
    ("Issues opened", "issues_created", "issues"),
    ("Issues updated", "issues_updated", "issues"),
    ("PRs opened", "pull_requests_created", "issues"),
    ("PRs updated", "pull_requests_updated", "issues"),
    ("PRs merged", "merged_events", "issues/events"),
    ("Closed", "closed_events", "issues/events"),
    ("Commits", "commits", "commits"),
    ("Releases", "releases", "releases"),
)


def _quiet_window(facts: dict[str, Any]) -> bool:
    """Say whether the run measured no activity at all in the report's own window.

    The rule is "every row of the activity table reads zero in the daily column",
    and it is stated that way on purpose: it is checkable from the report itself.
    A reader who meets an empty *Significant Changes* can look at the table in the
    same message and see the emptiness was earned, without taking anyone's word
    for it, and a writer cannot move the line because the counts are read from the
    run's file and there is no findings field for one.

    Zero of everything rather than a threshold. The temptation is to allow a
    window with two commits and nothing else, and it is the wrong direction: the
    fabrication pressure this rule exists to relieve comes only from having
    nothing to point at. A window with any measured change always offers a
    truthful item, so calling one of them significant is at worst over-inclusion,
    with real evidence behind it. A window with none offers only invention. And a
    threshold would be the one part of this file that is a judgement rather than a
    measurement: arguable in either direction, and impossible to state in the
    report where a reader could check it.

    A missing count is not a zero. ``_count`` reads an absent key as 0, so a fetch
    that wrote no ``window_counts`` at all would otherwise look like the quietest
    window there has ever been and license an empty section on the busiest day.
    Every measure has to be present *and* zero.
    """
    daily = _mapping(_mapping(facts["counts"]).get("daily"))
    if not all(key in daily for _title, key, _endpoint in _MEASURES):
        return False
    return not any(
        _count(facts["counts"], "daily", key) for _title, key, _endpoint in _MEASURES
    )


def _measured(facts: dict[str, Any]) -> str:
    """Name what the run did count for the window, for the message that refuses.

    Empty only when no measure was recorded at all, which is a different thing
    from a quiet window and has to read as one: those counts were never taken, so
    nothing measured that the window was quiet.
    """
    return ", ".join(
        f"{title.lower()} {_count(facts['counts'], 'daily', key)}"
        for title, key, _endpoint in _MEASURES
        if _count(facts["counts"], "daily", key)
    )


def _capped_endpoints(warnings: list[str]) -> set[str]:
    """Return the endpoints whose history the run could not read to the end."""
    capped: set[str] = set()
    for warning in warnings:
        head, _, _rest = warning.partition(":")
        name = head.strip()
        if name:
            capped.add(name)
    return capped


def _activity_table(facts: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Render the one place in the report where a number may appear.

    Every count comes from ``window_counts``. Findings JSON carries no count
    field at all, so a per-theme figure has nowhere to be invented into -- which
    is the whole reason the trend section states direction and evidence and no
    arithmetic.

    A wider column is left as ``n/a`` when its endpoint stopped short of the
    history boundary. This matters more than it looks: a truncated 7-day count
    equals its 24-hour count exactly, so it does not read as missing data, it
    reads as *a week in which nothing else happened* -- a wrong answer that
    looks like a quiet week. The daily column is unaffected; it is inside every
    endpoint's reach.
    """
    counts = facts["counts"]
    capped = _capped_endpoints(facts["warnings"])
    lines = [
        f"| Measure | {facts['hours']}h | 7d | {facts['days']}d |",
        "| --- | ---: | ---: | ---: |",
    ]
    limited: list[str] = []
    for title, key, endpoint in _MEASURES:
        daily = _count(counts, "daily", key)
        if endpoint in capped:
            wider = ("n/a", "n/a")
            if endpoint not in limited:
                limited.append(endpoint)
        else:
            wider = (
                str(_count(counts, "seven_day", key)),
                str(_count(counts, "history", key)),
            )
        lines.append(f"| {title} | {daily} | {wider[0]} | {wider[1]} |")
    notes: list[str] = []
    if limited:
        notes.append(
            "`n/a`: this run could not read "
            + ", ".join(limited)
            + " back to the window boundary, so the wider counts are not "
            "stated. The daily column is unaffected; the reason is under "
            "*Evidence Gaps*."
        )
    return lines, notes


# -------------------------------------------------------------- the sections


def _render_tldr(findings: dict[str, Any], shortfalls: _Shortfalls) -> list[str]:
    # No bullets at all is structural, not a shortfall: the TL;DR is the whole of
    # the judgement the channel message carries, and a report whose first section
    # is empty is indistinguishable from a run that analysed nothing. There is no
    # weak line here to publish with a mark -- there is no line.
    #
    # This is the one required section a quiet window does not excuse, and the
    # asymmetry with *Significant Changes* is deliberate rather than an oversight.
    # A quiet window can honestly have no significant change, because a change is
    # something that has to have happened; it cannot honestly have no judgement,
    # because "nothing moved in this window" is itself the judgement and takes one
    # line to write. Excusing it would leave the channel message -- which is the
    # TL;DR and little else -- carrying no statement at all, so the reader could
    # not tell a quiet window from a run that gave up.
    entries = _as_list(findings.get("tldr"))[:3]
    if not entries:
        raise RenderError("tldr: at least one bullet is required")
    lines = ["*TL;DR*"]
    for index, raw in enumerate(entries, start=1):
        entry = _mapping(raw)
        where = f"TL;DR bullet {index}"
        _note_unread(raw, _TLDR_KEYS, where=where, shortfalls=shortfalls)
        severity = _severity(
            entry, default="stable", where=where, shortfalls=shortfalls
        )
        lines.append(
            f"• {_mark(severity)} " + _body(entry, where=where, shortfalls=shortfalls)
        )
    return lines


def _render_changes(
    findings: dict[str, Any], facts: dict[str, Any], shortfalls: _Shortfalls
) -> list[str]:
    """Render the significant changes, or say the window had none to have.

    Empty used to refuse outright, and that refusal was a fabrication incentive
    rather than a guard. On a genuinely quiet window the honest finding is that
    nothing significant happened, and refusing left a writer two ways out: invent
    a change, or fail the render -- and a failed render is the documented
    precondition for both the retry loop and for a report composed outside this
    script entirely. A report in this exact format with no measured data behind
    it has been observed, so this is not a hypothetical cost.

    The gate is the run's own numbers and never the findings, which is the whole
    of the distinction worth drawing here: "nothing happened" is a fact about the
    repository that the fetcher measured, "the writer produced nothing" is a fact
    about the document. The first is a report; the second is an empty one. A busy
    window with no changes stated still refuses, and now names what it counted, so
    the message cannot be read as a shape complaint.
    """
    entries = _as_list(findings.get("significant_changes"))[:5]
    if not entries:
        if _quiet_window(facts):
            # Follows every other empty section: a line of its own, saying what
            # was looked for. A section that simply disappeared, or one that read
            # "None identified", would both leave the emptiness looking like
            # something nobody filled in. This one states the measurement.
            return [
                "*Significant Changes*",
                "• None; this run measured no issue, pull request, commit or "
                "release activity in the window, so there was no change to weigh.",
            ]
        measured = _measured(facts)
        raise RenderError(
            "significant_changes: at least one item is required. "
            + (
                f"This window is not quiet -- the run counted {measured} -- so "
                "an empty section would report that nothing happened where "
                "something did."
                if measured
                else "This run recorded no window counts, so nothing measured "
                "that the window was quiet; a count that is absent was never "
                "taken, and an absent count is not a zero."
            )
            + " The section may be left empty only when every measure in the "
            "activity table is present and reads zero for the window."
        )
    lines = ["*Significant Changes*"]
    for index, raw in enumerate(entries, start=1):
        entry = _mapping(raw)
        where = f"significant change {index}"
        misplaced = _misplaced_evidence(raw, _CHANGE_KEYS)
        _note_unread(
            raw,
            _CHANGE_KEYS,
            where=where,
            shortfalls=shortfalls,
            explained=misplaced,
        )
        title = _text(entry.get("title"))
        if title:
            heading = f"*{title}*"
        else:
            # An untitled item is published, but never as an empty heading: a
            # blank line where a title belongs reads as a rendering fault and
            # tells the reader nothing. The body and the evidence below it are
            # the substance and are intact, so the item is worth keeping.
            shortfalls.note(where, "no title; the item is published untitled")
            heading = f"{_WARN} *(untitled)*"
        lines.append(f"{index}. {heading}")
        lines.append(
            "   ["
            + _label(entry, default="fact", where=where, shortfalls=shortfalls)
            + "] "
            + _body(entry, where=where, shortfalls=shortfalls)
        )
        lines.append(
            "   "
            + _evidence_line(
                entry.get("evidence"),
                required=True,
                where=where,
                shortfalls=shortfalls,
                misplaced=misplaced,
            )
        )
    return lines


def _render_risks(findings: dict[str, Any], shortfalls: _Shortfalls) -> list[str]:
    entries = _as_list(findings.get("risks"))[:5]
    lines = ["*Risks and Blockers*"]
    if not entries:
        lines.append("• None identified in this window.")
        return lines
    for index, raw in enumerate(entries, start=1):
        entry = _mapping(raw)
        where = f"risk {index}"
        # No ``misplaced`` here on purpose: evidence is optional on a risk, so
        # there is no line in place to correct. The unread-key note below still
        # names the key, which is where a writer looks.
        _note_unread(raw, _RISK_KEYS, where=where, shortfalls=shortfalls)
        severity = _severity(
            entry, default="major", where=where, shortfalls=shortfalls
        )
        evidence = _evidence_line(
            entry.get("evidence"), required=False, where=where, shortfalls=shortfalls
        )
        rating = severity.title() if severity else "Unrated"
        lines.append(
            f"• {_mark(severity)} *{rating}* — "
            + _body(entry, where=where, shortfalls=shortfalls)
        )
        if evidence:
            lines.append(f"  {evidence}")
    return lines


def _render_actions(findings: dict[str, Any], shortfalls: _Shortfalls) -> list[str]:
    entries = _as_list(findings.get("actions"))[:5]
    lines = ["*Recommended Actions*"]
    if not entries:
        lines.append("• None; nothing in this window calls for one.")
        return lines
    for index, raw in enumerate(entries, start=1):
        where = f"action {index}"
        _note_unread(raw, _ACTION_KEYS, where=where, shortfalls=shortfalls)
        lines.append(
            f"{index}. [RECOMMENDATION] "
            + _body(_mapping(raw), where=where, shortfalls=shortfalls)
        )
    return lines


def _render_trends(findings: dict[str, Any], shortfalls: _Shortfalls) -> list[str]:
    entries = _as_list(findings.get("trends"))
    lines = ["*Trend Signals*"]
    if not entries:
        lines.append("• None; no theme moved enough this window to state a direction.")
        return lines
    for index, raw in enumerate(entries, start=1):
        entry = _mapping(raw)
        theme = _text(entry.get("theme"))
        # Signals are bulleted rather than numbered, so the theme is how a reader
        # finds the one a shortfall belongs to. It is the only caller text this
        # section repeats, and it is already printed on the line above.
        where = f"trend {theme!r}" if theme else f"trend signal {index}"
        misplaced = _misplaced_evidence(raw, _TREND_KEYS)
        _note_unread(
            raw, _TREND_KEYS, where=where, shortfalls=shortfalls, explained=misplaced
        )
        if theme:
            heading = f"*{theme}*"
        else:
            shortfalls.note(where, "no theme; the signal is published unnamed")
            heading = f"{_WARN} *(theme not stated)*"
        direction = _text(entry.get("direction")).lower()
        if direction in _DIRECTION_MARKS:
            movement = _DIRECTION_MARKS[direction]
        else:
            # A direction is the whole claim a signal makes. Substituting
            # "stable" for an unrecognised word would state a claim nobody wrote.
            shortfalls.note(
                where,
                "direction is not one of "
                + ", ".join(sorted(_DIRECTION_MARKS))
                + "; no direction is published for this signal",
            )
            movement = f"{_WARN} Direction not stated"
        lines.append(f"• {heading} — {movement}")
        basis = _gloss(entry)
        if basis:
            lines.append(f"  {basis}")
        confidence = _CONFIDENCE.get(_text(entry.get("confidence")).lower())
        if not confidence:
            shortfalls.note(
                where,
                "confidence is not High, Medium or Low; the signal is published "
                "without one",
            )
            confidence = f"{_WARN} not stated"
        evidence = _evidence_line(
            entry.get("evidence"),
            required=True,
            where=where,
            shortfalls=shortfalls,
            misplaced=misplaced,
        )
        lines.append(f"  {evidence} · Confidence: {confidence}")
    return lines


def _render_capabilities(findings: dict[str, Any], shortfalls: _Shortfalls) -> list[str]:
    raw_groups = findings.get("missing_capabilities")
    # A group name nobody reads renders as "None identified in this window.",
    # which is not silence but a false statement -- so the group map is checked
    # the same way an item is.
    _note_unread(
        raw_groups,
        _CAPABILITY_GROUPS,
        where="missing capabilities",
        shortfalls=shortfalls,
    )
    groups = _mapping(raw_groups)
    ordered = (
        ("explicit", "Explicit"),
        ("inferred", "Inferred"),
        ("insufficient", "Evidence insufficient"),
    )
    body: list[str] = []
    for key, title in ordered:
        for index, raw in enumerate(_as_list(groups.get(key)), start=1):
            entry = _mapping(raw)
            where = f"{key} missing capability {index}"
            _note_unread(
                raw, _CAPABILITY_KEYS[key], where=where, shortfalls=shortfalls
            )
            heading = title
            if key == "inferred":
                confidence = _CONFIDENCE.get(_text(entry.get("confidence")).lower())
                if not confidence:
                    shortfalls.note(
                        where,
                        "confidence is not High, Medium or Low; the inference is "
                        "published without one",
                    )
                    heading = f"Inferred ({_WARN} confidence not stated)"
                else:
                    heading = f"Inferred ({confidence} confidence)"
            body.append(f"• *{heading}* — {_gloss(entry)}")
    if not body:
        body = ["• None identified in this window."]
    return ["*Missing Capabilities*", *body]


def _render_opportunities(findings: dict[str, Any], shortfalls: _Shortfalls) -> list[str]:
    entries = _as_list(findings.get("opportunities"))
    lines = ["*Opportunities for Our Team*"]
    if not entries:
        lines.append("• None identified in this window.")
        return lines
    for index, raw in enumerate(entries, start=1):
        entry = _mapping(raw)
        where = f"opportunity {index}"
        _note_unread(raw, _OPPORTUNITY_KEYS, where=where, shortfalls=shortfalls)
        title = _text(entry.get("title"))
        kind = _text(entry.get("kind"))
        # Reported separately: an item can well have one and not the other, and
        # a note that names both when only one is missing sends its reader
        # looking for a second problem that is not there.
        if not title:
            shortfalls.note(where, "no title; the item is published untitled")
        if not kind:
            shortfalls.note(where, "no kind; the item is published unclassified")
        heading = f"*{title}*" if title else f"{_WARN} *(untitled)*"
        classification = kind if kind else f"{_WARN} kind not stated"
        lines.append(f"{index}. {heading} — {classification}")
        grades = " · ".join(
            f"{label}: {_text(entry.get(field)) or 'Unknown'}"
            for label, field in (
                ("User value", "user_value"),
                ("Research value", "research_value"),
                ("Effort", "effort"),
                ("Risk", "risk"),
            )
        )
        lines.append(f"   {grades}")
        recommendation = _text(entry.get("recommendation"))
        if recommendation:
            lines.append(f"   Recommendation: {recommendation}")
    return lines


def _render_gaps(
    findings: dict[str, Any], facts: dict[str, Any], shortfalls: _Shortfalls
) -> list[str]:
    """Render evidence gaps, with the run's own limits added rather than asked for.

    Coverage warnings and truncation notices are the gaps most easily left out,
    because they are the ones nothing in the material reminds a writer of. They
    come from the run, so they are appended here and cannot be dropped.

    Both kinds have the same failure mode when they go missing: a capped list
    reads as a complete one, and neither party says otherwise. The writer does
    not know a cap was applied, and a renderer that promises the line but reads
    the value from a key nothing writes prints nothing at all -- which is
    indistinguishable, to a reader, from a window that was fully covered.
    """
    raw_groups = findings.get("evidence_gaps")
    _note_unread(
        raw_groups, _GAP_GROUPS, where="evidence gaps", shortfalls=shortfalls
    )
    groups = _mapping(raw_groups)
    lines = ["*Evidence Gaps*"]
    for key, title in (("known", "Known"), ("unknown", "Unknown"), ("needed", "Needed")):
        for index, raw in enumerate(_as_list(groups.get(key)), start=1):
            _note_unread(
                raw,
                _GAP_KEYS,
                where=f"{key} evidence gap {index}",
                shortfalls=shortfalls,
            )
            lines.append(f"• {title}: {_gloss(_mapping(raw))}")
    for warning in facts["warnings"]:
        lines.append(f"• Coverage: {warning}")
    for name, detail in sorted(_mapping(facts["truncated"]).items()):
        counts = _mapping(detail)
        lines.append(
            f"• Coverage: {name.replace('_', ' ')} shows "
            f"{counts.get('shown', '?')} of {counts.get('total', '?')}."
        )
    if facts["detail_omitted"]:
        lines.append(
            f"• Coverage: {facts['detail_omitted']} further item(s) active in "
            "this window were not inspected in detail; the deep-read sample is "
            "capped."
        )
    for note in facts["incomplete"]:
        lines.append(f"• Run: {note}")
    if len(lines) == 1:
        lines.append("• None recorded for this window.")
    return lines


def _render_shortfalls(shortfalls: _Shortfalls) -> list[str]:
    """List where this report falls short of its own rules.

    A section of its own rather than more lines under *Evidence Gaps*, because
    the two answer different questions and are fixed by different people.
    *Evidence Gaps* says what this run could not establish about the repository
    -- a fact about the world, and the reader's cue to trust a conclusion less.
    This says where the report failed a rule it makes for itself -- a fact about
    the document, and the writer's cue to fix the next one. Filed together, a
    missing evidence link would read as an evidence limitation, which is exactly
    the excuse it must not have; and *Evidence Gaps* is half written by the
    findings, so a renderer's note placed there sits among lines the writer
    controls and can be lost in them.

    Written on every run, like every other section. A section that appears only
    when something is wrong is one a reader cannot tell from a section nobody
    filled in -- and on a clean run the line is the guarantee being reported as
    met, which is the only way a reader ever learns it was checked.
    """
    lines = ["*Reporting Shortfalls*"]
    if not shortfalls.items:
        lines.append("• None; every item in this report met the reporting rules.")
        return lines
    for item in shortfalls.items:
        lines.append(f"• {_WARN} {item}")
    return lines


def _check_findings_shape(findings: dict[str, Any]) -> None:
    """Refuse a findings file that is not in this schema, and say so as that.

    A file sharing no key with the schema is a different mistake from a file
    missing one, and the difference decides whether a run can recover. Reporting
    an invented shape as "tldr is required" names one key out of eight and
    describes the rest of the file as acceptable when none of it will be read;
    a run that acts on it adds a `tldr`, renders again, and gets a report with
    everything else missing -- or, observed more often, concludes the renderer
    cannot be satisfied and writes its own report instead, which is the one
    outcome the whole split exists to prevent.
    """
    recognised = [key for key in _FINDINGS_KEYS if key in findings]
    # A key the renderer does not read is dropped in silence. That is harmless
    # for a scalar the writer kept for itself -- a timestamp, a repository name
    # -- and is the whole failure for a list or an object, which is where a
    # findings file puts its content. Sharing one schema key is therefore not
    # enough to call the file this schema: a run that writes its findings under
    # `findings` and a single `trends` alongside passes the test below, is told
    # only that `tldr` needs a bullet, and never learns that the rest of what it
    # wrote will not be read.
    ignored = sorted(
        key for key, value in findings.items()
        if key not in _FINDINGS_KEYS and isinstance(value, (list, dict)) and value
    )
    if recognised and not ignored:
        return
    if not recognised:
        found = ", ".join(sorted(findings)) or "nothing"
        raise RenderError(
            "--findings is not in this schema: it carries none of the keys this "
            f"renderer reads ({', '.join(_FINDINGS_KEYS)}), and holds {found} "
            "instead. Rewrite the file against references/findings-schema.md; "
            "nothing under an unrecognised key is read, so a report rendered from "
            "this file would be missing everything it says."
        )
    raise RenderError(
        f"--findings holds content under {', '.join(ignored)}, which this "
        f"renderer does not read; of its own keys ({', '.join(_FINDINGS_KEYS)}) "
        f"the file fills {'only ' if len(recognised) < len(_FINDINGS_KEYS) else ''}"
        f"{', '.join(recognised)}. Move that content onto "
        "the schema's keys per references/findings-schema.md rather than adding "
        "to what is already there -- rendered as it stands, everything under "
        f"{', '.join(ignored)} is dropped without appearing anywhere."
    )


def render(
    activity: dict[str, Any],
    findings: dict[str, Any],
    *,
    title: str = "Repository intelligence",
    shortfalls: _Shortfalls | None = None,
) -> str:
    """Render the report, or refuse when there is nothing worth rendering.

    Pass a ``_Shortfalls`` to read afterwards what the report fell short on; it
    is published in the report either way, so a caller that does not care can
    leave it out. It is an out-parameter rather than a second return value so
    that "render" keeps meaning "the finished text", which is what every caller
    delivers.
    """
    shortfalls = _Shortfalls() if shortfalls is None else shortfalls
    facts = _run_facts(activity)
    _check_findings_shape(findings)
    # After the shape check, which reads the document as it arrived: a key the
    # writer invented is still an invented key once its example content is gone,
    # and that diagnosis is the one that keeps a run from rendering again into
    # the same wall.
    findings = _clear_placeholders(findings, shortfalls)

    # The title names the repository and the date and nothing else. A
    # deployment's own wording for it belongs in the prompt that passes
    # ``--title``, not in a Skill another deployment installs: a report headed
    # with somebody else's product name is the first thing a new operator has to
    # go and find in the source to change.
    brief: list[str] = [
        f"*{title} — {facts['repository']} — {facts['date']}*",
        f"_Windows: {facts['hours']}h / 7d"
        f" / {facts['days']}d · Coverage: {facts['coverage']}_",
    ]
    for block in (
        _render_tldr(findings, shortfalls),
        _render_changes(findings, facts, shortfalls),
        _render_risks(findings, shortfalls),
        _render_actions(findings, shortfalls),
    ):
        brief.extend(["", *block])

    # An over-long brief is not shortened here and no longer refuses. The report
    # is complete and correct; the only consequence is that the host splits the
    # channel message at a point of its choosing rather than at one this budget
    # chose, and a reader still receives every section. Refusing traded that for
    # no report at all. Recorded before the sections are assembled, so it reaches
    # the same place every other shortfall does.
    brief_text = "\n".join(brief).strip()
    if len(brief_text) > _BRIEF_BUDGET:
        shortfalls.note(
            "the channel brief",
            f"{len(brief_text)} characters, over the {_BRIEF_BUDGET} budget; the "
            "host may split it mid-section. Shorten the findings rather than the "
            "sections -- a section dropped to fit is one the reader never learns "
            "was there",
        )

    # Every section is rendered on every run, present or empty. Which sections
    # a report has is therefore a property of this file and not of what the
    # writer happened to fill in, and a reader who finds no trend signal learns
    # that the run found none rather than that the section might not exist.
    table, table_notes = _activity_table(facts)
    blocks = [
        ["*Activity in numbers*", *table, *table_notes],
        _render_trends(findings, shortfalls),
        _render_capabilities(findings, shortfalls),
        _render_opportunities(findings, shortfalls),
        _render_gaps(findings, facts, shortfalls),
    ]
    # Last, and after every other section has been built: it reports on them, so
    # it cannot be assembled while any of them is still unwritten.
    blocks.append(_render_shortfalls(shortfalls))
    detail: list[str] = []
    for block in blocks:
        detail.extend(["", *block])

    text = "\n".join([*brief, "", _THREAD_MARKER, *detail]).strip() + "\n"
    _reject_paths(text, where="report")
    _reject_placeholders(text)
    return text


# ------------------------------------------------------------------- driver


def _load(path: Path, *, what: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RenderError(f"{what}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RenderError(f"{what} is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RenderError(f"{what} must be a JSON object")
    return data


def _load_findings(path: Path | None, text: str | None) -> dict[str, Any]:
    """Read the findings from the command itself, or from the file named for it."""
    if text is not None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RenderError(f"the findings given on stdin are not JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise RenderError("the findings given on stdin must be a JSON object")
        return data
    if path is None:  # pragma: no cover - _resolve_inputs settles one or the other
        raise RenderError("no findings were given")
    if not path.exists():
        raise RenderError(
            f"no findings: {path.name} does not exist in the run directory and "
            "nothing was given on the command. Findings can be passed inline, "
            "which is the form that cannot be run too early: "
            "--findings - <<'JSON' … JSON"
        )
    return _load(path, what="--findings")


def _stdin_offers_findings() -> bool:
    """Say whether stdin is carrying a document rather than nothing.

    Findings normally arrive inline, as a heredoc on this command, because that
    makes "render before the findings exist" impossible to express: the two are
    one action, so there is no window in which the renderer can be called against
    a file that has not been written yet. Detecting the heredoc rather than
    demanding a flag for it is what keeps the shorter form correct.

    Reading stdin unconditionally would not be safe. A scheduled run's stdin can
    be an open pipe with nothing on the other end, and a read on one blocks until
    the host kills the run -- trading a legible error for a hang. A heredoc is a
    regular file, or a pipe whose bytes are already there, and both of those can
    be recognised without reading.
    """
    try:
        fileno = sys.stdin.fileno()
        mode = os.fstat(fileno).st_mode
    except (AttributeError, OSError, ValueError):
        return False
    if stat.S_ISREG(mode):
        return True
    if not stat.S_ISFIFO(mode):
        # A terminal, /dev/null or a socket. None of them is a heredoc, and the
        # first two are what an unattended run gets.
        return False
    try:
        readable, _, _ = select.select([fileno], [], [], 0.0)
    except (OSError, ValueError):  # pragma: no cover - platform dependent
        return False
    return bool(readable)


def _resolve_inputs(args: Any) -> tuple[Path, Path | None, Path | None, str | None]:
    """Settle where each input comes from, preferring the run directory over retyping.

    ``--run-dir`` exists because of how this command fails in practice. It named
    three absolute paths, each around a hundred characters, and every one had to
    be reproduced by hand from the fetcher's stdout. A path reproduced by hand is
    a path that can lose a character, and the resulting command does not fail
    politely: it fails, gets retried byte-identically because nothing about it
    looks wrong, and the retry is what ends the run. Naming the directory once
    and deriving the rest removes two thirds of that surface.

    The explicit flags still win where they are given, so a caller rendering an
    archived run, or findings written somewhere else, is not forced through the
    directory layout.
    """
    run_dir: Path | None = args.run_dir
    activity: Path | None = args.activity
    findings: Path | None = args.findings
    output: Path | None = args.output

    # Findings given inline win over any file, and are read before anything else
    # so that a heredoc is never silently ignored in favour of yesterday's file.
    findings_text: str | None = None
    if findings is not None and str(findings) == "-":
        findings = None
        findings_text = sys.stdin.read()
        if not findings_text.strip():
            raise RenderError(
                "--findings - was given but stdin carried nothing. The findings "
                "JSON goes on the command itself: "
                "--findings - <<'JSON' … JSON"
            )
    elif findings is None and _stdin_offers_findings():
        offered = sys.stdin.read()
        if offered.strip():
            findings_text = offered

    if run_dir is not None:
        if not run_dir.is_dir():
            raise RenderError(f"--run-dir is not a directory: {run_dir}")
        if findings is None and findings_text is None:
            findings = run_dir / "findings.json"
        if output is None:
            output = run_dir / "report.md"
        if activity is None:
            manifest = run_dir / "run.json"
            if not manifest.exists():
                raise RenderError(
                    f"--run-dir has no run.json ({manifest}), so the activity "
                    "file it belongs to is unknown. Re-run the fetch, or pass "
                    "--activity."
                )
            recorded = _text(_load(manifest, what="run.json").get("raw_output"))
            if not recorded:
                raise RenderError("run.json records no raw_output path")
            activity = Path(recorded)

    if activity is None or (findings is None and findings_text is None):
        raise RenderError(
            "give --run-dir, or give both --activity and --findings. The "
            "findings themselves can go on the command instead of into a file: "
            "--findings - <<'JSON' … JSON"
        )
    return activity, findings, output, findings_text


def _check_language(text: str, language: str | None) -> list[str]:
    """Run the sibling language gate over the rendered text, in-process.

    Rendering and checking in one command is what makes a failure cheap to fix:
    the caller corrects the findings and renders again, and nothing has been
    consumed in between. A separate check invites the opposite -- treating the
    failure as a reason to stop, which loses the window the fetcher already
    committed.
    """
    import importlib.util

    script = Path(__file__).resolve().parent / "check_report_language.py"
    if not script.exists():
        return ["language check skipped: check_report_language.py is not installed"]
    spec = importlib.util.spec_from_file_location("_digest_language_gate", script)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        return ["language check skipped: the checker could not be loaded"]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    resolved, _source = module.resolve_language(language)
    expected = module._LANGUAGE_SCRIPTS.get(resolved)
    if expected is None:
        # An output language the table does not cover skips rather than blocks:
        # the gate compares writing systems, and it has nothing to compare
        # against here. Saying so beats failing a report for a missing table row.
        return []
    return [
        f"{item['verdict']}  line {item['line']} col {item['column']} "
        f"[{item['scripts']}]  {item['text']}"
        for item in module.check(text, expected)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        help=(
            "this run's directory, named on the fetcher's stdout under "
            "paths.run_dir. Supplies --activity, --findings and --output, so "
            "the command carries one path instead of three"
        ),
    )
    parser.add_argument(
        "--activity",
        type=Path,
        help="the fetcher's raw-output file, named on its stdout under paths",
    )
    parser.add_argument(
        "--findings",
        type=Path,
        help=(
            "the judgement half of the report as JSON. Give '-' to pass it on "
            "the command itself — --findings - <<'JSON' … JSON — which is the "
            "form that cannot be run before the findings exist. A path still "
            "works, and a heredoc is recognised without the flag. See "
            "references/findings-schema.md"
        ),
    )
    parser.add_argument(
        "--output", type=Path, help="also write the rendered report to this file"
    )
    parser.add_argument(
        "--title",
        default="Repository intelligence",
        help=(
            "wording for the report's own title; the repository and the date "
            "are appended to it and are not configurable"
        ),
    )
    parser.add_argument(
        "--language",
        help="override the output language the gate checks against",
    )
    parser.add_argument(
        "--check-language",
        action="store_true",
        help=(
            "run the output-language gate over the rendered report and exit "
            "non-zero on a finding. The report is still printed: fix the "
            "findings and render again, never abandon the run"
        ),
    )
    args = parser.parse_args(argv)

    shortfalls = _Shortfalls()
    try:
        activity_path, findings_path, output_path, findings_text = _resolve_inputs(args)
        activity = _load(activity_path, what="--activity")
        findings = _load_findings(findings_path, findings_text)
        text = render(activity, findings, title=args.title, shortfalls=shortfalls)
    except RenderError as exc:
        print(f"render failed: {exc}", file=sys.stderr)
        # Whatever was noted before the refusal is very often its cause, and it
        # is the half the refusal cannot state. A findings file copied from the
        # template unfilled fails on "tldr: at least one bullet is required" --
        # true, and the wrong thing to act on, because the bullet was written and
        # then dropped as an example. Naming a missing key rather than the actual
        # shape is precisely the error this file's own docstring records as the
        # one that sends a run off to write its own report.
        for item in shortfalls.items:
            print(f"noted before the refusal: {item}", file=sys.stderr)
        return 2

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)

    # Reported here as well as in the report, and deliberately not as a failure.
    # This is a finished report: the exit status stays 0 so that nothing treats
    # it as one to retry, and the text above is the deliverable exactly as it
    # stands. Re-rendering is still free, but only corrected findings change the
    # outcome -- the same command run again produces the same report.
    if shortfalls.items:
        print("", file=sys.stderr)
        for item in shortfalls.items:
            print(f"reporting shortfall: {item}", file=sys.stderr)
        print(
            f"\n{len(shortfalls)} reporting shortfall(s). They are published in "
            "the report above, under 'Reporting Shortfalls'. The report is "
            "finished and is the deliverable as it stands; render again only "
            "with corrected findings.",
            file=sys.stderr,
        )

    if args.check_language:
        problems = _check_language(text, args.language)
        if problems:
            print("", file=sys.stderr)
            for problem in problems:
                print(problem, file=sys.stderr)
            print(
                f"\n{len(problems)} language finding(s). Correct the findings "
                "JSON and render again; rendering consumes nothing.",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except AttributeError:  # pragma: no cover - very old interpreters
        pass
    raise SystemExit(main())
