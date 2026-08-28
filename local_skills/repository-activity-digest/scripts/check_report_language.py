#!/usr/bin/env python3
"""Check a finished report for source text left in another language.

A repository's Issue titles, PR titles and commit subjects arrive verbatim from
the fetcher, in whatever language its contributors write. Pasting one into a
finding costs nothing and reads as faithful, so it happens: a report otherwise
written in the output language ends up with its `[FACT]` lines and TL;DR bullets
in a language the reader may not have. `report-format.md` requires instead that
such text be rendered into the output language with the original in parentheses
after it. This script is the gate on that requirement.

It exists because the requirement is one a model has to apply to itself at the
moment of writing, and this Skill's history says that is not enough on its own.
The rule is easy to state, easy to agree with, and easy to skip on the one line
where copying is the obvious move — which is exactly the line that reaches the
reader. So the finished text is checked, the same way links are checked rather
than merely required to be real.

What it decides, and what it cannot
-----------------------------------

This is a **script** check. It resolves the output language to the writing
systems that language uses, then looks for letters outside them. That catches
Chinese, Japanese, Korean, Cyrillic, Arabic, Greek, Hebrew, Devanagari and Thai
text sitting in an English report, which is the failure this Skill actually
sees, and it is decidable from the text alone with no model in the loop and no
network.

It cannot catch a different language in the *same* script: French pasted into an
English report is invisible here, and so is Portuguese in a Spanish one. Saying
otherwise would need language identification, which is probabilistic, wrong on
the short strings a title usually is, and would fail a report for a correctly
spelled product name often enough that whoever runs it would learn to pass
`--skip`. A check that is never wrong about a narrower thing is worth more than
one that is sometimes wrong about a wider thing, so the narrower thing is what
is checked, and this paragraph is the honest statement of the gap.

Nothing here judges translation *quality* either. That a parenthetical is a
faithful rendering of the text before it is exactly what no script can settle,
and it is why the rule carries the original at all: the check enforces that the
reader is given both, and the reader settles the rest.

Two verdicts
------------

  - **UNGLOSSED** — foreign-script text with no parentheses around it. This is
    the pasted title, and it is the whole reason the script exists.
  - **LEADS** — foreign-script text correctly in parentheses, but with no
    output-language text anywhere ahead of it. The original is present and the
    rendering is not, or they are the wrong way round. `report-format.md` fixes
    the order deliberately, so this is reported rather than allowed.

Both fail the run. Foreign-script text in parentheses with output-language text
ahead of it passes, which is the shape the format asks for. "Ahead of it" spans
the whole run of non-blank lines a finding occupies, because a rendering on the
`[FACT]` line and its parenthetical on the indented line below is the format
working correctly, not a violation.

URL targets are excluded before anything is examined: a link's target is
machine-addressed, is never read as prose, and may legitimately contain any
script at all. Link *labels* are checked, because they are read.

Usage
  python3 scripts/check_report_language.py report.md
  python3 scripts/check_report_language.py report.md --language en
  python3 scripts/check_report_language.py report.md --json

With no `--language`, the output language is resolved the way SKILL.md resolves
it: `preferred_language` from `$JIUWENSWARM_HOME/config/config.yaml`, or
`~/.jiuwenswarm/config/config.yaml`, falling back to English. Pass `--language`
when the report was explicitly requested in some other language, so the check
follows the report rather than the installation.

An output language whose writing systems are not in the table below cannot be
checked; the run reports SKIPPED and exits 0. Blocking a report over a language
this script has no opinion about would be the wrong trade.

Exit codes: 0 clean or skipped, 1 at least one finding, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

# Ranges are deliberately coarse: enough to tell one writing system from
# another, not a Unicode script database. Anything not listed reads as
# "Unknown", which is treated as foreign — a letter this table cannot place is
# not one the reader was promised.
_SCRIPT_RANGES: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = (
    (
        "Latin",
        (
            (0x0041, 0x005A),
            (0x0061, 0x007A),
            (0x00C0, 0x024F),
            (0x1E00, 0x1EFF),
            (0x2C60, 0x2C7F),
            (0xA720, 0xA7FF),
        ),
    ),
    ("Greek", ((0x0370, 0x03FF), (0x1F00, 0x1FFF))),
    ("Cyrillic", ((0x0400, 0x052F), (0x2DE0, 0x2DFF), (0xA640, 0xA69F))),
    ("Hebrew", ((0x0590, 0x05FF),)),
    ("Arabic", ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))),
    ("Devanagari", ((0x0900, 0x097F), (0xA8E0, 0xA8FF))),
    ("Thai", ((0x0E00, 0x0E7F),)),
    ("Hangul", ((0x1100, 0x11FF), (0x3130, 0x318F), (0xA960, 0xA97F), (0xAC00, 0xD7AF))),
    ("Hiragana", ((0x3040, 0x309F),)),
    ("Katakana", ((0x30A0, 0x30FF), (0x31F0, 0x31FF))),
    (
        "Han",
        (
            (0x2E80, 0x2EFF),
            (0x3400, 0x4DBF),
            (0x4E00, 0x9FFF),
            (0xF900, 0xFAFF),
            (0x20000, 0x2A6DF),
            (0x2A700, 0x2EBEF),
        ),
    ),
)

# Every non-Latin entry also admits Latin, because product, project and
# organisation names keep their own Latin-script form in any output language and
# flagging them would make the check unusable. The reverse does not hold: a
# Latin-script output language admits Latin only, which is what lets this catch
# the case the Skill actually hits.
_LATIN = ("Latin",)
_LANGUAGE_SCRIPTS: dict[str, tuple[str, ...]] = {
    "ar": ("Arabic", "Latin"),
    "cs": _LATIN,
    "da": _LATIN,
    "de": _LATIN,
    "el": ("Greek", "Latin"),
    "en": _LATIN,
    "es": _LATIN,
    "fi": _LATIN,
    "fr": _LATIN,
    "he": ("Hebrew", "Latin"),
    "hi": ("Devanagari", "Latin"),
    "id": _LATIN,
    "it": _LATIN,
    "ja": ("Han", "Hiragana", "Katakana", "Latin"),
    "ko": ("Hangul", "Han", "Latin"),
    "nl": _LATIN,
    "no": _LATIN,
    "pl": _LATIN,
    "pt": _LATIN,
    "ru": ("Cyrillic", "Latin"),
    "sv": _LATIN,
    "th": ("Thai", "Latin"),
    "tr": _LATIN,
    "uk": ("Cyrillic", "Latin"),
    "vi": _LATIN,
    "zh": ("Han", "Latin"),
}

# Openers that mark a parenthetical gloss, and their closers. Square brackets
# are included because the format allows them; `[FACT]` and the like are
# Latin-only and so never reach this code path.
_GLOSS_PAIRS = {
    "(": ")",
    "[": "]",
    "（": "）",
    "【": "】",
    "「": "」",
    "《": "》",
}

_URL = re.compile(r"https?://\S+")
_MRKDWN_LINK = re.compile(r"<(https?://[^|>]+)\|")
_MD_LINK_TARGET = re.compile(r"\]\((https?://[^)]+)\)")


def _script_of(char: str) -> str:
    code = ord(char)
    for name, ranges in _SCRIPT_RANGES:
        for low, high in ranges:
            if low <= code <= high:
                return name
    return "Unknown"


def _is_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def _mask_url_targets(line: str) -> str:
    """Replace link targets with spaces, preserving column positions.

    Offsets are reported to a human reading the original file, so the masked
    line has to stay the same length as the line it came from.
    """

    masked = list(line)

    def blank(start: int, end: int) -> None:
        for index in range(start, end):
            masked[index] = " "

    for pattern in (_MRKDWN_LINK, _MD_LINK_TARGET):
        for match in pattern.finditer(line):
            blank(match.start(1), match.end(1))
    for match in _URL.finditer("".join(masked)):
        blank(match.start(), match.end())
    return "".join(masked)


def _gloss_spans(line: str) -> list[tuple[int, int]]:
    """Return (open_index, close_index) for each bracketed span on the line.

    Unclosed openers are ignored rather than assumed to run to end of line: an
    unbalanced bracket is far more likely to be prose than a gloss, and reading
    it as a gloss would let unglossed text through.
    """

    spans: list[tuple[int, int]] = []
    stack: list[tuple[str, int]] = []
    for index, char in enumerate(line):
        if char in _GLOSS_PAIRS:
            stack.append((char, index))
        elif stack and char == _GLOSS_PAIRS[stack[-1][0]]:
            _, start = stack.pop()
            spans.append((start, index))
    return spans


def _has_expected_letter(text: str, expected: tuple[str, ...]) -> bool:
    return any(_is_letter(char) and _script_of(char) in expected for char in text)


def _foreign_runs(line: str, expected: tuple[str, ...]) -> list[tuple[int, int, str]]:
    """Maximal runs of letters whose script is not one the language uses.

    Digits, punctuation, symbols and emoji are skipped entirely: they carry no
    language, and a run is not broken by the space or comma inside it, so
    `点击取消任务后，后台还在执行` is reported once rather than twice.
    """

    runs: list[tuple[int, int, str]] = []
    start: int | None = None
    scripts: set[str] = set()
    for index, char in enumerate(line + "\n"):
        foreign = _is_letter(char) and _script_of(char) not in expected
        if foreign:
            if start is None:
                start = index
            scripts.add(_script_of(char))
        elif start is not None:
            native = _is_letter(char) and _script_of(char) in expected
            separator = char.isspace() or unicodedata.category(char).startswith(("P", "S", "N"))
            if separator and not native and char != "\n":
                # Hold the run open across an interior separator, but only if
                # more foreign text follows before any native letter does.
                rest = line[index:]
                nxt = next((c for c in rest if _is_letter(c)), "")
                if nxt and _script_of(nxt) not in expected:
                    continue
            runs.append((start, index, "+".join(sorted(scripts))))
            start = None
            scripts = set()
    return [(s, e, k) for s, e, k in runs if line[s:e].strip()]


def resolve_language(explicit: str | None) -> tuple[str, str]:
    """Return (language, where it came from), mirroring SKILL.md's order."""

    if explicit:
        return explicit.strip().lower(), "--language"
    home = os.environ.get("JIUWENSWARM_HOME")
    root = Path(home) if home else Path.home() / ".jiuwenswarm"
    config = root / "config" / "config.yaml"
    if config.is_file():
        # A single top-level scalar is read directly rather than through a YAML
        # parser, so this script keeps the standard-library-only footprint the
        # rest of the Skill's scripts have.
        pattern = re.compile(r"^preferred_language\s*:\s*['\"]?([A-Za-z_-]+)['\"]?\s*(?:#.*)?$")
        try:
            for line in config.read_text(encoding="utf-8").splitlines():
                found = pattern.match(line)
                if found:
                    return found.group(1).strip().lower(), str(config)
        except OSError:
            pass
    return "en", "default"


def check(text: str, expected: tuple[str, ...]) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    # A finding routinely wraps: the rendering sits on the `[FACT]` line and its
    # parenthetical on the indented line below. So "does output-language text
    # come first" is asked of the whole run of non-blank lines, not of one line
    # in isolation -- otherwise every correctly wrapped gloss is a false report,
    # and a check that cries wolf on the documented format teaches whoever runs
    # it to ignore the real findings.
    preceding = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        line = _mask_url_targets(raw)
        if not raw.strip():
            preceding = ""
            continue
        block_before = preceding
        preceding = f"{preceding}\n{line}" if preceding else line
        runs = _foreign_runs(line, expected)
        if not runs:
            continue
        spans = _gloss_spans(line)
        for start, end, scripts in runs:
            span = next((s for s in spans if s[0] < start and end <= s[1]), None)
            if span is None:
                verdict = "UNGLOSSED"
            elif _has_expected_letter(block_before + line[: span[0]], expected):
                continue
            else:
                verdict = "LEADS"
            findings.append(
                {
                    "verdict": verdict,
                    "line": number,
                    "column": start + 1,
                    "scripts": scripts,
                    "text": raw[start:end],
                    "context": raw.strip()[:160],
                }
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fail a report that carries source text in another language.",
    )
    parser.add_argument("report", help="the finished report, as it will be delivered")
    parser.add_argument(
        "--language",
        help="output language code; defaults to preferred_language, then English",
    )
    parser.add_argument("--json", action="store_true", help="emit a machine-readable receipt")
    args = parser.parse_args(argv)

    path = Path(args.report)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        print(f"cannot read {path}: {error}", file=sys.stderr)
        return 2

    language, source = resolve_language(args.language)
    expected = _LANGUAGE_SCRIPTS.get(language)
    if expected is None:
        receipt = {
            "report": str(path),
            "language": language,
            "language_source": source,
            "status": "SKIPPED",
            "reason": f"no writing systems recorded for {language!r}",
            "findings": [],
        }
        if args.json:
            print(json.dumps(receipt, ensure_ascii=False, indent=2))
        else:
            print(f"SKIPPED  output language {language!r} has no writing systems in this table")
        return 0

    findings = check(text, expected)
    receipt = {
        "report": str(path),
        "language": language,
        "language_source": source,
        "expected_scripts": list(expected),
        "status": "FAIL" if findings else "OK",
        "findings": findings,
    }

    if args.json:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    elif not findings:
        print(f"OK  {path}: no source text outside {'/'.join(expected)} (language {language}, from {source})")
    else:
        for item in findings:
            print(f"{item['verdict']}  line {item['line']} col {item['column']} [{item['scripts']}]  {item['text']}")
            print(f"          {item['context']}")
        print(
            f"\n{len(findings)} finding(s). Render each in {language} and put the original in "
            "parentheses after it, per references/report-format.md.",
        )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
