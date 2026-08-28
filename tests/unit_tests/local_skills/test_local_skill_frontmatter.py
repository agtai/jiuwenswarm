"""Every skill under ``local_skills/`` must ship frontmatter the runtime can read.

A ``SKILL.md`` whose YAML frontmatter fails to parse is not a broken skill. It is
a skill the model cannot find. The runtime catches the parse error, logs it, and
substitutes ``"Skill located in <directory>"`` for the description -- so the skill
still registers, still appears in the roster, and simply never matches anything,
because ``description`` is the whole selection surface. Nothing fails loudly and
no run reports an error; the skill is just never chosen.

That is exactly what happened to ``slack-block-kit-reference``. Its description
was one unquoted YAML scalar containing ``payload: a `blocks` array``, and an
unquoted scalar with a colon-space inside it parses as a nested mapping, so the
whole block died with ``mapping values are not allowed here``. It shipped that
way -- through several deploy branches -- and the only trace was a warning line
repeating once per skill load.

The guard is here rather than in any one skill for the usual reason: the defect
is a property of the file format, so every skill has it available, and the skill
that happened to trip it shipped no tests at all. It is also cheap and total:
nine files, one parse each.

What is checked mirrors what the runtime actually does, not a tidier version of
it:

* **The block is split the way the loader splits it** -- ``text.split("---", 2)``
  on a string that must *start* with ``---``. This is deliberately not a
  line-anchored regex. The loader's split is naive, so a bare ``---`` appearing
  early in a description would truncate the block for the loader while a stricter
  parser here would still read it whole, and the guard would pass on a file the
  runtime cannot load. A guard that is more forgiving than the thing it guards is
  worse than none.
* **The result must be a mapping.** ``yaml.safe_load`` of a malformed block can
  return a string or a list rather than raise, and ``"description" in data`` on a
  string is a substring test that quietly succeeds.
* **``name`` and ``description`` must both be present and non-empty.** An empty
  description reaches the model as an empty selection surface, which is the same
  outcome as the parse failure by a different route.

``name`` is additionally required to match the directory name. The runtime takes
the skill's name from the *directory*, ignoring the frontmatter field entirely,
so a disagreement between the two is invisible at load time and misleads every
later reader -- including the skill's own prose, which refers to itself by name.
"""

from __future__ import annotations

from pathlib import Path

import yaml

SKILLS = Path(__file__).resolve().parents[3] / "local_skills"

REQUIRED = ("name", "description")

ADVICE = (
    "A SKILL.md whose frontmatter does not parse loses its description, and the "
    "description is what the model selects the skill on -- so the skill loads, "
    "lists, and is never chosen. Nothing fails at the time.\n"
    "The usual cause is an unquoted YAML scalar containing a colon followed by a "
    "space, which parses as a nested mapping and takes the whole block down with "
    "it. Wrap the value in single quotes, or reword so the colon-space is gone. "
    "Quoting is preferable: it leaves the text the model matches on byte for "
    "byte, and a reworded description is a different selection surface.\n"
    "Other scalars that need quoting for the same reason: a value starting with "
    "`*`, `&`, `[`, `{`, `>`, `|`, `%`, `@` or `` ` ``, and one containing ` #`."
)


def skill_files() -> list[Path]:
    """Every ``SKILL.md`` the repository ships, one per skill directory."""
    return sorted(SKILLS.glob("*/SKILL.md"))


def frontmatter_of(text: str) -> dict | list | str | None:
    """The frontmatter block, parsed the way ``SkillUseRail._load_yaml`` parses it.

    Returns ``None`` when the runtime would find no frontmatter at all. Raises
    whatever ``yaml.safe_load`` raises, so the caller can name the parse error.
    """
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    return yaml.safe_load(parts[1]) or {}


def defect_in(path: Path) -> str | None:
    """The reason the runtime could not read this file's description, or None."""
    text = path.read_text(encoding="utf-8")
    try:
        data = frontmatter_of(text)
    except yaml.YAMLError as exc:
        detail = " ".join(str(exc).split())
        return f"frontmatter does not parse as YAML: {detail}"
    if data is None:
        return (
            "no frontmatter block: the file must start with `---` and close the "
            "block with a second `---`"
        )
    if not isinstance(data, dict):
        return (
            f"frontmatter parsed as {type(data).__name__}, not a mapping; the "
            "runtime reads it with `in` and would find no description"
        )
    for field in REQUIRED:
        if field not in data:
            return f"frontmatter has no `{field}` field"
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            return f"frontmatter field `{field}` is empty or not a string: {value!r}"
    if data["name"] != path.parent.name:
        return (
            f"frontmatter name {data['name']!r} is not the directory name "
            f"{path.parent.name!r}; the runtime names the skill after the "
            "directory, so the field misleads every reader and nothing catches it"
        )
    return None


def test_every_local_skill_has_readable_frontmatter():
    offences = [
        f"{path.relative_to(SKILLS.parent)}: {defect}"
        for path in skill_files()
        if (defect := defect_in(path)) is not None
    ]
    assert not offences, "\n".join([*offences, "", ADVICE])


def test_the_guard_reads_the_skills_it_is_meant_to():
    """A scan that found nothing passes for the wrong reason.

    The skill directory has been renamed once and the tests moved once, so the
    likeliest way this guard stops working is not a skill regressing -- it is
    this file quietly iterating an empty glob.
    """
    assert SKILLS.is_dir(), SKILLS
    directories = sorted(path.name for path in SKILLS.iterdir() if path.is_dir())
    assert len(directories) >= 2, directories

    found = sorted(path.parent.name for path in skill_files())
    assert found == directories, (
        "every skill directory must ship a SKILL.md; missing "
        f"{sorted(set(directories) - set(found))}"
    )


def test_the_guard_catches_the_defect_it_was_written_for(tmp_path):
    """The shape that shipped, and the shapes next to it.

    Each hazard is a block the runtime would fail to read a description from;
    each benign case is one it reads correctly. The first hazard is the exact
    line that shipped in slack-block-kit-reference.
    """
    hazards = (
        # An unquoted scalar with a colon-space: what actually shipped.
        "---\nname: s\ndescription: Use before editing a payload: a blocks array\n---\n",
        # The same defect one field up.
        "---\nname: a: b\ndescription: fine\n---\n",
        "---\nname: s\n---\n",  # no description
        "---\ndescription: fine\n---\n",  # no name
        "---\nname: s\ndescription: ''\n---\n",  # empty description
        "---\nname: s\ndescription: '   '\n---\n",  # whitespace description
        "---\nname: s\ndescription:\n---\n",  # null description
        "---\nname: s\ndescription: fine\n",  # block never closed
        "name: s\ndescription: fine\n",  # no block at all
        # Parses without raising, but not to a mapping. `"description" in data`
        # on this string is a substring test, and it succeeds.
        "---\njust a description string\n---\n",
        # A tab where YAML permits only spaces.
        "---\nname: s\ndescription: fine\n\tindented: with a tab\n---\n",
    )
    for index, block in enumerate(hazards):
        path = _written(tmp_path / f"hazard{index}", block, name="s")
        assert defect_in(path) is not None, block

    benign = (
        "---\nname: s\ndescription: A plain one-line description.\n---\n",
        # The fix: the colon survives inside quotes.
        "---\nname: s\ndescription: 'Use before editing a payload: a blocks array'\n---\n",
        # A colon with no space after it never started a mapping.
        "---\nname: s\ndescription: Ratio 16:9 and a `key:value` pair.\n---\n",
        # A `---` in the *body* is a horizontal rule, not a third delimiter, and
        # the loader's split stops before it.
        "---\nname: s\ndescription: fine\n---\n\n# Title\n\n---\n\nmore prose\n",
    )
    for index, block in enumerate(benign):
        path = _written(tmp_path / f"benign{index}", block, name="s")
        assert defect_in(path) is None, block


def _written(root: Path, block: str, name: str) -> Path:
    """``block`` on disk at ``<root>/<name>/SKILL.md``, so defect_in() can read it.

    A file rather than a string because defect_in() compares the frontmatter
    name against the *directory* name, which only a real path carries.
    """
    directory = root / name
    directory.mkdir(parents=True)
    path = directory / "SKILL.md"
    path.write_text(block, encoding="utf-8")
    return path
