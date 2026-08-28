"""Guards for the prose this skill ships.

The skill has no code: it is a reference document, so every one of its claims is
a string in a Markdown file and every regression is an edit that quietly removes
one. These tests pin the claims that are expensive to get wrong -- the ones where
Slack's own published reference says the opposite, so a reader who "corrects" the
document back towards the source produces a payload the API refuses.

Two kinds of guard live here:

* Portability. A reference to Slack's format must not carry the context of
  whoever transcribed it: no home-directory paths, no citations of documents that
  do not ship with the skill.
* Verified corrections. Where a field was probed against a live workspace and the
  answer contradicts the documentation, the corrected value must stay corrected,
  the contradiction must stay flagged, and anything that was *not* established
  must stay marked as untested rather than drifting into a flat claim.

Run:
    python3 -m pytest <skill>/tests -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_ROOT / "SKILL.md"
BLOCKS = SKILL_ROOT / "references" / "blocks.md"
ELEMENTS = SKILL_ROOT / "references" / "block-elements.md"


def shipped_docs():
    """Every prose file the skill ships, discovered rather than listed.

    Discovery is the point: a reference added later is covered without anyone
    remembering to extend a list here. ``tests/`` is not shipped -- it lives in
    version control only -- so it is not walked.
    """
    found = [SKILL_MD] + sorted((SKILL_ROOT / "references").iterdir())
    return [path for path in found if path.is_file()]


def read(path):
    return path.read_text(encoding="utf-8")


def section(path, heading):
    """The text of one `## ...` section, up to the next `## ...`."""
    text = read(path)
    start = text.index(heading)
    rest = text[start + len(heading) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def field_row(body, field):
    """The field table row for ``field``, from a section's body."""
    for line in body.splitlines():
        if line.startswith(f"| `{field}` |"):
            return line
    raise AssertionError(f"no field table row for `{field}`")


def cell(row, index):
    return [part.strip() for part in row.strip().strip("|").split("|")][index]


PLAN = "## Plan block — `plan`"
TASK_CARD = "## Task card block — `task_card`"
CARD = "## Card block — `card`"
TEXT_ELEMENT = "## Text element — `text`"
EMOJI_ELEMENT = "## Emoji element — `emoji`"


# --------------------------------------------------------- the prose is portable


LEAK_PATTERNS = (
    # a host's home directory: a username and one deployment's layout
    (re.compile(r"/(?:home|Users)/[A-Za-z0-9._-]+/"), "an absolute home-directory path"),
    # a document that does not ship with the skill
    (re.compile(r"design (?:doc|section)", re.IGNORECASE), "a design-document citation"),
    # the machinery that posted the probes, which is not part of Block Kit
    (
        re.compile(r"\b(?:connector|renderer|deployment|allow-?list)\b", re.IGNORECASE),
        "the transcriber's own machinery",
    ),
)

# There is deliberately no pattern for a channel name. Slack's own reference
# names `#general` when it explains the broadcast element's `range`, so a bare
# `#name` cannot be told apart from the format's own vocabulary by a regex. The
# rule still holds -- no workspace of ours is named in the document -- it is just
# not one a guard can enforce without firing on the source material.


def test_the_shipped_prose_carries_no_host_context():
    """A skill teaching a public format must be readable by anyone.

    Narrow on purpose. It fires on a home-directory path, a citation of a
    document nobody outside its author's repository can read, the names of the
    machinery that happened to post the probes -- and on nothing else. Slack's
    own vocabulary is not a leak: `#general` appears in the broadcast element's
    documentation, and a card that "renders" is not a renderer.
    """
    offences = [
        f"{path.relative_to(SKILL_ROOT)}:{lineno}: {complaint}: {line.strip()!r}"
        for path in shipped_docs()
        for lineno, line in enumerate(read(path).splitlines(), 1)
        for pattern, complaint in LEAK_PATTERNS
        if pattern.search(line)
    ]
    assert not offences, "\n".join(offences)


def test_the_leak_guard_catches_what_it_claims_to():
    hits = {
        complaint
        for sample in (
            "the crawl lives in /home/someone/notes/",
            "see the design doc for the rationale",
            "the connector rewrites this before sending",
        )
        for pattern, complaint in LEAK_PATTERNS
        if pattern.search(sample)
    }
    assert len(hits) == len(LEAK_PATTERNS), hits
    for benign in (
        "a card renders a hero image",
        "the block is designed for messages",
        "https://docs.slack.dev/reference/block-kit/blocks/card-block",
        "everyone notifies every person in the #general channel",
    ):
        assert not any(pattern.search(benign) for pattern, _ in LEAK_PATTERNS), benign


def test_block_kit_json_is_fenced_as_blockkit():
    """The one local convention: Block Kit JSON is tagged ```blockkit."""
    offences = [
        f"{path.relative_to(SKILL_ROOT)}:{lineno}"
        for path in shipped_docs()
        for lineno, line in enumerate(read(path).splitlines(), 1)
        if line.strip() == "```json"
    ]
    assert not offences, offences


# ------------------------------------ plan.title is a bare string, card's is not
#
# The single most costly reversal in the document. Slack types `plan.title` as
# `Object` and describes it as plain text, which reads as a call for a
# `plain_text` text object; the API refuses one. The neighbouring card block runs
# the other way. A reader who learns either rule and generalises it writes a
# payload that is rejected outright, so both entries must keep saying so, and
# each must keep pointing at the other.


def test_plan_title_is_typed_as_a_string_not_an_object():
    row = field_row(section(BLOCKS, PLAN), "title")
    assert cell(row, 1) == "String", row
    assert "bare string" in cell(row, 3), row


def test_the_plan_entry_keeps_slacks_own_typing_beside_the_correction():
    """The correction is only usable if the reader can see what it overrides."""
    row = field_row(section(BLOCKS, PLAN), "title")
    assert "Slack's own table types this `Object`" in cell(row, 3), row


def test_the_plan_entry_shows_the_rejection_and_the_accepted_form():
    body = section(BLOCKS, PLAN)
    assert "must provide a string" in body
    assert '"title": "Analysing the paper"' in body
    assert "live workspace" in body


def test_the_plan_and_card_title_rules_point_at_each_other():
    """Neither correction is safe to read on its own."""
    plan = section(BLOCKS, PLAN)
    card = section(BLOCKS, CARD)
    assert "opposite of the card block" in plan
    assert "does not generalise" in plan
    assert "plan.title" in card
    assert "does not generalise" in card


def test_the_summary_lists_plan_title_among_the_genuine_bare_strings():
    text = read(SKILL_MD)
    genuine = text[text.index("The genuine bare\n  strings are few") :][:400]
    assert "`plan.title`" in genuine, genuine


def test_plan_title_is_no_longer_an_open_disagreement():
    """It was open, and it is now settled; it must not be listed as both."""
    text = read(SKILL_MD)
    still_open = text[text.index("- **Still open**") :]
    still_open = still_open[: still_open.index("\n- ", still_open.index("\n  - "))]
    assert "plan.title" not in still_open, still_open


# --------------------------------- task_card.status depends on where the card is
#
# Slack documents one enum and no context. Two sets are enforced, and the value
# that differs, `pending`, is the one Slack's own example uses in the position
# that refuses it. Recorded on the task card entry because that is where a reader
# looks for the values a status may take.


def test_the_task_card_status_row_flags_the_context_dependence():
    row = field_row(section(BLOCKS, TASK_CARD), "status")
    assert "depends on where the card sits" in row, row
    assert "top-level" in row, row


def test_both_enum_sets_are_recorded_with_the_position_each_applies_to():
    body = section(BLOCKS, TASK_CARD)
    table = [line for line in body.splitlines() if line.startswith("| A ")]
    assert len(table) == 2, table
    standalone, nested = table
    assert "top-level" in standalone and "`pending`" not in standalone, standalone
    assert "plan" in nested and "`pending`" in nested, nested


def test_the_refused_status_spellings_are_recorded():
    body = section(BLOCKS, TASK_CARD)
    for refused in ("`in-progress`", "`done`", "`running`"):
        assert refused in body, refused
    assert "must be a valid enum value" in body


def test_slacks_own_task_card_example_is_flagged_as_invalid_as_written():
    """The example is transcribed unchanged, so the warning is what protects it.

    Leaving it as Slack publishes it is deliberate: this file is a transcription,
    and silently repairing the source hides the discrepancy the reader needs. The
    warning does the work instead, and it has to sit next to the example as well
    as in the prose above it, because an example is what gets copied.
    """
    body = section(BLOCKS, TASK_CARD)
    assert "invalid as written" in body
    fences = re.findall(r"```blockkit\n(.*?)```", body, re.DOTALL)
    assert len(fences) == 1, len(fences)
    assert '"status": "pending"' in fences[0], "the example should be unchanged"
    after = body[body.index(fences[0]) + len(fences[0]) :]
    assert "that example fails" in after, after[:200]


def test_the_inference_about_pending_is_marked_as_inference():
    """Measured behaviour is fact; the explanation for it is not."""
    body = section(BLOCKS, TASK_CARD)
    assert "That is inference." in body
    assert "measured against a live workspace" in body


# ------------------------------------------- the plan's own status does nothing


def test_plan_status_is_documented_as_undocumented_accepted_and_inert():
    body = section(BLOCKS, PLAN)
    row = field_row(body, "status")
    assert "Absent from Slack's field table" in row, row
    assert "inert" in row, row
    assert "derived from the statuses of the task cards" in body
    assert "Do not set it." in body


# ------------------------------------------ details and output are one panel


def test_details_and_output_are_recorded_as_the_same_panel():
    body = section(BLOCKS, TASK_CARD)
    assert "leading dot" in body
    assert "no disclosure control" in body
    assert "Pick one." in body


# ---------------------------------------- rich text does not parse shortcodes


def test_the_text_element_records_that_shortcodes_stay_literal():
    body = section(ELEMENTS, TEXT_ELEMENT)
    assert "Emoji shortcodes are not parsed here" in body
    assert '{ "type": "emoji", "name": "white_check_mark" }' in body
    assert "live workspace" in body


def test_the_trap_is_stated_where_both_halves_of_it_are_visible():
    """The danger is the contrast, not either half on its own."""
    body = section(ELEMENTS, TEXT_ELEMENT)
    assert "`section`" in body and "`mrkdwn`" in body
    assert "silently changes meaning" in body
    summary = read(SKILL_MD)
    assert "does not parse emoji shortcodes" in summary
    assert "*does* parse the\n  same shortcode" in summary


def test_the_emoji_element_is_recorded_as_the_way_to_do_it():
    body = section(ELEMENTS, EMOJI_ELEMENT)
    assert "not parsed" in body
    assert "without its colons" in body
    assert "does render, and is a workable fallback" in body


# ------------------------------------------------ what was not established
#
# A measurement that stopped somewhere must keep saying where it stopped. These
# two are the ones most likely to be rounded up by a later editor tidying hedges
# out of the prose: one observed rejection is not a rule about non-ASCII, and one
# plan that posted is not a documented maximum.


@pytest.mark.parametrize(
    "path,heading,required",
    [
        (
            ELEMENTS,
            TEXT_ELEMENT,
            ("Only that character was tested.", "untested", "U+00D7"),
        ),
        (BLOCKS, PLAN, ("12 is a floor, not the limit", "untested")),
    ],
)
def test_an_unestablished_rule_stays_marked_as_unestablished(path, heading, required):
    body = section(path, heading)
    for phrase in required:
        assert phrase in body, phrase


def test_the_non_ascii_note_refuses_the_blanket_claim():
    body = section(ELEMENTS, TEXT_ELEMENT)
    assert 'Do not read this as "non-ASCII is rejected"' in body
    assert "emoji in particular are known to render" in body


def test_the_summary_repeats_both_caveats():
    text = read(SKILL_MD)
    assert "Verified but not generalised" in text
    assert "Measured floors, not limits" in text
    assert text.count("**untested**") >= 2
