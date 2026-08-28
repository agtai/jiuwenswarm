#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["markdown-to-mrkdwn>=0.3.3"]
# ///
"""Convert Markdown to Slack mrkdwn.

Slack does not render Markdown. It uses mrkdwn, which differs in most of the
places that matter for a digest: `*bold*` not `**bold**`, `_italic_` not
`*italic*`, `<url|label>` not `[label](url)`, `•` not `-`, and no headings at
all. Getting that right by hand every time is fiddly work that belongs in a
script rather than in prose instructions.

Conversion only, by design. This script does not split, post, or know anything
about Slack's API — delivery is a separate concern and belongs to whatever ends
up doing the posting.

Length in particular is not handled here. Slack recommends at most 4000
characters in a message's text and hard-truncates at 40000; a Block Kit section
block caps at 3000. Converting does not meaningfully
change length: measured over a corpus of digests, plain mrkdwn comes out about
1% *shorter* than its Markdown source. (`--divider` reverses that, adding roughly
17 characters per section — about +1% on a real digest.) A document that is too long was too long before conversion, so
the fix belongs where the text is written — the skill takes a length budget for
exactly that reason — or in a poster, where the API limit actually lives.

Usage
  uv run scripts/md_to_mrkdwn.py digest.md              # to stdout
  uv run scripts/md_to_mrkdwn.py digest.md --divider    # rules above sections
  uv run scripts/md_to_mrkdwn.py digest.md -o out.txt   # to a file
  cat digest.md | uv run scripts/md_to_mrkdwn.py -      # stdin

Without uv: pip install markdown-to-mrkdwn, then run with python3.
"""

import argparse
import sys
from pathlib import Path

DIVIDER = "───────────────"


def add_dividers(markdown: str) -> str:
    """Put a rule above each `##` section, before conversion flattens levels.

    mrkdwn has no headings, so the library renders every level as bold and a
    section title becomes indistinguishable from an item title. Applied to the
    Markdown, where heading level is still visible; afterwards it is all just
    bold text.
    """
    out, in_fence = [], False
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        # A digest quoting a shell snippet or a config fragment can contain a
        # comment line starting at column 0; without fence tracking it would
        # collect a rule and a blank line in the middle of the code block.
        elif not in_fence and line.startswith("## ") and out:
            out.extend(["", DIVIDER])
        out.append(line)
    return "\n".join(out)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("input", help="Markdown file, or - for stdin")
    p.add_argument(
        "--divider",
        action="store_true",
        help="rule above each section, since mrkdwn has no heading levels",
    )
    p.add_argument("-o", "--out", help="write here instead of stdout")
    args = p.parse_args()

    try:
        from markdown_to_mrkdwn import SlackMarkdownConverter
    except ImportError:
        sys.exit(
            "markdown-to-mrkdwn is not installed.\n"
            "  run with uv:  uv run scripts/md_to_mrkdwn.py <file>\n"
            "  or install:   pip install markdown-to-mrkdwn"
        )

    src = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    text = SlackMarkdownConverter().convert(add_dividers(src) if args.divider else src)

    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {len(text)} chars to {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
