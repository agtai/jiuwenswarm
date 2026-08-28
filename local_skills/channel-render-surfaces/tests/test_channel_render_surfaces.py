"""Guard tests for the `channel-render-surfaces` skill.

The skill is documentation: it tells a model which rendering surfaces exist and
which fence reaches each one. Documentation of a moving target rots silently —
a renamed fence, a lowered cap or a mark that stopped mapping leaves the skill
confidently wrong, and a model that follows it writes a fence that shows up as
source. So every factual claim in `SKILL.md` is checked here **against the
renderer itself** rather than against a copy of its constants.

The renderer is loaded from this repository by file path rather than imported as
`jiuwenswarm.gateway...`, for two reasons: the module is pure by construction
and needs none of the package around it, and a file-path load keeps this suite
runnable in a bare environment.

Four kinds of check:

1. The `description` carries the vocabulary that decides whether the skill fires
   at all, and the clause that keeps it quiet on ordinary replies.
2. Every fence the skill names is a fence the renderer knows, and no fence is
   documented as rendering which the renderer declines.
3. Every worked example is fed to the real renderer and must produce the block
   the skill claims for it.
4. Nothing in the skill identifies where it was written.

Run:
    python3 -m pytest <skill>/tests -q
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_DIR.parent.parent
RENDERER = (
    REPO_ROOT
    / "jiuwenswarm"
    / "gateway"
    / "channel_manager"
    / "im_platforms"
    / "slack"
    / "slack_blocks.py"
)


def _renderer():
    """The deployed renderer, loaded straight from its file."""
    spec = importlib.util.spec_from_file_location("_slack_blocks_under_test", RENDERER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


blocks = _renderer()


def _skill_md() -> str:
    return (SKILL_DIR / "SKILL.md").read_text()


def _front_matter() -> str:
    text = _skill_md()
    assert text.startswith("---\n")
    return text.split("---\n", 2)[1]


def _description() -> str:
    """The `description:` value, unwrapped from its folded block scalar."""
    body = _front_matter().split("description:", 1)[1]
    body = body.split("\n---", 1)[0]
    # Stop at the next top-level key, if any follows.
    lines = []
    for line in body.splitlines()[1:]:
        if line and not line.startswith("  "):
            break
        lines.append(line.strip())
    return " ".join(part for part in lines if part)


def _examples() -> list[str]:
    """Every worked example, unwrapped from the four-backtick fences quoting it."""
    text = _skill_md()
    found = re.findall(r"^````\n(.*?)^````$", text, re.MULTILINE | re.DOTALL)
    assert found, "the skill must carry worked examples"
    return found


def _example_named(language: str) -> str:
    for example in _examples():
        if example.startswith(f"```{language}\n"):
            return example
    raise AssertionError(f"no worked example for a ```{language} fence")


def _rendered(text: str) -> list[str]:
    """The block types the renderer produces for *text*, or [] for plain text."""
    result = blocks.render_blocks(text)
    return [] if result is None else [block["type"] for block in result]


# ------------------------------------------------------------- the description
#
# The description is read at selection time and is the only part of the skill a
# model sees before deciding to load it. It is therefore the whole of the fix:
# the problem this skill exists for is that a model reaches for ```json because
# nothing told it the other fences exist.


@pytest.mark.parametrize(
    "word",
    [
        # The act the skill is for: choosing a presentation.
        "present",
        "show",
        "draw",
        # The verbs an operator actually types.
        "chart",
        "plot",
        "graph",
        "diagram",
        "visualise",
        # The shapes of data that should make it fire.
        "comparison",
        "breakdown",
        "ranking",
        "trend",
        "distribution",
        # The surfaces themselves, so a model searching for one finds it.
        "table",
        "mermaid",
        "vega-lite",
        "blockkit",
    ],
)
def test_the_description_carries_the_vocabulary_that_makes_it_fire(word):
    assert word in _description().lower(), f"{word!r} is a trigger the skill needs"


def test_the_description_says_when_to_stay_quiet():
    """Too eager and it loads on every message; the negative clause is the brake."""
    description = _description().lower()
    assert "not needed for ordinary prose replies" in description
    assert "no data" in description


def test_the_description_disclaims_the_two_things_it_does_not_teach():
    """Availability, not syntax; and Block Kit fields live in the other skill."""
    description = _description().lower()
    assert "does not teach mermaid or vega-lite syntax" in description
    assert "slack-block-kit-reference" in description


def test_the_description_names_the_caps_that_decide_feasibility():
    description = _description()
    assert str(blocks.MAX_CHART_SEGMENTS) in description
    assert str(blocks.MAX_CHART_TITLE_LENGTH) in description
    assert str(blocks.MAX_CHART_LABEL_LENGTH) in description


# ------------------------------------------------------------------ the fences


def test_every_rendering_fence_the_skill_names_is_one_the_renderer_renders():
    text = _skill_md()
    for language in (
        blocks.MERMAID_FENCE_LANGUAGE,
        blocks.VEGA_LITE_FENCE_LANGUAGE,
        blocks.BLOCK_KIT_FENCE_LANGUAGE,
    ):
        assert f"```{language}" in text, f"{language!r} renders and must be documented"


def test_the_escape_hatch_fence_is_named_by_the_name_the_renderer_reads():
    assert f"```{blocks.RAW_FENCE_LANGUAGE}" in _skill_md()


def test_no_fence_is_documented_as_rendering_that_the_renderer_declines():
    """The set the skill presents as rendering is exactly the renderer's set."""
    known = {
        blocks.MERMAID_FENCE_LANGUAGE,
        blocks.VEGA_LITE_FENCE_LANGUAGE,
        blocks.BLOCK_KIT_FENCE_LANGUAGE,
        blocks.RAW_FENCE_LANGUAGE,
    }
    for example in _examples():
        language = example.splitlines()[0].removeprefix("```").strip()
        assert language in known, f"{language!r} is not a fence the renderer reads"


def test_the_skill_does_not_send_a_model_back_to_a_json_fence():
    """The measured failure was ```json every time; it must not be offered here."""
    assert "```json" not in _skill_md()


# ------------------------------------------------------- the examples themselves
#
# The strongest guard in the file: the worked examples are run through the real
# renderer. An example that stopped rendering would otherwise teach a model to
# write a fence that arrives as source.


def test_the_markdown_table_example_renders_without_any_fence():
    section = _skill_md().split("### Markdown table")[1].split("###")[0]
    table = re.search(r"^```\n(.*?)^```$", section, re.MULTILINE | re.DOTALL)
    assert table is not None, "the table example must be present"
    rendered = _rendered(table.group(1))
    assert rendered and rendered[-1] in ("table", "data_table"), rendered


def test_the_mermaid_pie_example_renders_as_a_pie_chart():
    result = blocks.render_blocks(_example_named("mermaid"))
    assert result is not None
    assert result[0]["type"] == "data_visualization"
    assert result[0]["chart"]["type"] == blocks.PIE_CHART


def test_the_mermaid_xychart_example_renders_as_a_bar_chart():
    example = next(
        text for text in _examples() if "xychart-beta" in text.splitlines()[1]
    )
    result = blocks.render_blocks(example)
    assert result is not None
    assert result[0]["chart"]["type"] == blocks.BAR_CHART


def test_the_documented_bar_to_line_swap_actually_produces_a_line_chart():
    """The skill tells a model to swap the keyword; the swap has to work."""
    example = next(
        text for text in _examples() if "xychart-beta" in text.splitlines()[1]
    )
    result = blocks.render_blocks(example.replace("\n    bar [", "\n    line ["))
    assert result is not None
    assert result[0]["chart"]["type"] == blocks.LINE_CHART


def test_the_vega_lite_example_renders_as_a_bar_chart_with_both_series():
    result = blocks.render_blocks(_example_named("vega-lite"))
    assert result is not None
    chart = result[0]["chart"]
    assert chart["type"] == blocks.BAR_CHART
    assert len(chart["series"]) == 2, "the example is documented as showing two series"


def test_the_blockkit_example_renders_as_the_block_it_holds():
    result = blocks.render_blocks(_example_named("blockkit"))
    assert result is not None
    assert [block["type"] for block in result] == ["section"]


def test_the_slack_raw_example_is_not_drawn():
    """The escape hatch has to stay an escape hatch."""
    assert blocks.render_blocks(_example_named("slack-raw")) is None


# ----------------------------------------------------------------- the caps
#
# Each row of the caps table is tied to the constant it reports, so lowering a
# limit in the renderer fails here rather than in a channel.


def test_the_caps_table_reports_the_renderer_s_own_numbers():
    text = _skill_md()
    for row in (
        f"| charts per message | **{blocks.MAX_DATA_VISUALIZATIONS_PER_MESSAGE}**",
        f"| pie segments | {blocks.MAX_CHART_SEGMENTS} |",
        f"| series per bar/area/line chart | {blocks.MAX_CHART_SERIES} |",
        f"| x-axis categories | {blocks.MAX_CHART_CATEGORIES} |",
        f"| chart title | {blocks.MAX_CHART_TITLE_LENGTH} characters |",
        "| segment / category / series labels | "
        f"{blocks.MAX_CHART_LABEL_LENGTH} characters |",
        "| axis titles (`x_label`, `y_label`) | "
        f"{blocks.MAX_AXIS_LABEL_LENGTH} characters |",
    ):
        assert row in text, f"the caps table is out of date: {row!r}"


def test_the_chart_cap_is_the_one_the_renderer_enforces():
    """Documented as costing the whole message its rendering, so prove both halves."""
    pie = '```mermaid\npie title P%d\n    "x" : 1\n    "y" : 2\n```\n'
    allowed = "\n".join(pie % index for index in range(1, 3))
    over = "\n".join(pie % index for index in range(1, 4))
    assert _rendered(allowed) == ["data_visualization"] * 2
    assert _rendered(over) == [], "a third chart must drop the whole message to text"


def test_the_segment_cap_is_the_one_the_renderer_enforces():
    def pie(count: int) -> str:
        rows = "".join(f'    "s{n}" : {n + 1}\n' for n in range(count))
        return f"```mermaid\npie\n{rows}```\n"

    assert _rendered(pie(blocks.MAX_CHART_SEGMENTS)) == ["data_visualization"]
    assert _rendered(pie(blocks.MAX_CHART_SEGMENTS + 1)) == []


# ------------------------------------------------------------ the Vega-Lite marks


def test_every_mark_the_skill_says_maps_is_one_the_renderer_maps():
    table = _skill_md().split("## Which Vega-Lite marks map")[1].split("Declined")[0]
    documented = set(re.findall(r"^\| `(\w+)` \|", table, re.MULTILINE))
    assert documented == set(blocks.VEGA_LITE_MARKS), (
        "the mark table must be exactly the renderer's, no more and no less"
    )


def test_every_mark_the_skill_says_declines_really_declines():
    section = _skill_md().split("Declined, each because")[1].split("Also declined")[0]
    declined = set(re.findall(r"`(\w+)`", section))
    assert declined, "the declined list must not be empty"
    for mark in declined:
        assert mark not in blocks.VEGA_LITE_MARKS, f"{mark!r} does map after all"


def test_the_spec_level_declines_name_the_renderer_s_own_keys():
    section = _skill_md().split("Also declined at the spec level")[1]
    for key in blocks.VEGA_LITE_COMPOSITION_KEYS:
        assert f"`{key}`" in section, f"{key!r} declines and must be documented"
    for key in blocks.VEGA_LITE_DERIVED_KEYS:
        assert f"`{key}`" in section, f"{key!r} declines and must be documented"


def test_the_sort_the_skill_says_is_honoured_really_is():
    """Documented as read on ``x`` as an array and declined in every other form."""
    spec = {
        "mark": "bar",
        "data": {"values": [{"d": "Mon", "n": 1}, {"d": "Tue", "n": 2}]},
        "encoding": {
            "x": {"field": "d", "type": "nominal", "sort": ["Tue", "Mon"]},
            "y": {"field": "n", "type": "quantitative"},
        },
    }
    fenced = "```vega-lite\n%s\n```\n"
    assert _rendered(fenced % json.dumps(spec)) == ["data_visualization"]
    spec["encoding"]["x"]["sort"] = "-y"
    assert _rendered(fenced % json.dumps(spec)) == []


def test_an_arc_pie_really_needs_both_theta_and_colour():
    """Documented as "both are required", which is a claim about the renderer."""
    assert "**Both are required**" in _skill_md()
    spec = {
        "mark": "arc",
        "data": {"values": [{"a": "one", "n": 1}, {"a": "two", "n": 2}]},
        "encoding": {
            "theta": {"field": "n", "type": "quantitative"},
            "color": {"field": "a", "type": "nominal"},
        },
    }
    fenced = "```vega-lite\n%s\n```\n"
    assert _rendered(fenced % json.dumps(spec)) == ["data_visualization"]
    for dropped in ("theta", "color"):
        partial = {**spec, "encoding": {
            key: value for key, value in spec["encoding"].items() if key != dropped
        }}
        assert _rendered(fenced % json.dumps(partial)) == [], f"{dropped} is required"


def test_pie_values_really_have_to_be_above_zero():
    def pie(second: int) -> str:
        return f'```mermaid\npie\n    "a" : 1\n    "b" : {second}\n```\n'

    assert _rendered(pie(1)) == ["data_visualization"]
    assert _rendered(pie(0)) == [], "a zero segment is documented as declining"


def test_area_is_documented_as_out_of_reach_from_mermaid():
    """The one asymmetry between the two portable fences."""
    assert blocks.AREA_CHART not in blocks.MERMAID_PLOT_CHARTS.values()
    assert "no area chart of any kind" in _skill_md()


def test_the_mermaid_plot_keywords_are_the_ones_the_skill_names():
    section = _skill_md().split("### mermaid — bar or line")[1].split("###")[0]
    for keyword in blocks.MERMAID_PLOT_CHARTS:
        assert f"`{keyword}`" in section


# --------------------------------------------------------------- self-contained


def test_the_skill_names_no_host_no_operator_and_no_deployment():
    """Someone reading this skill should not be able to tell where it came from."""
    lowered = _skill_md().lower()
    for forbidden in (
        "/home/",
        "/opt/",
        "/data/",
        "127.0.0.1",
        "localhost",
        "jiuwenswarm",
        "venv",
        "site-packages",
        "config.yaml",
        "local/",
        "worktree",
        "http://",
        "https://",
    ):
        assert forbidden not in lowered, f"{forbidden!r} identifies a deployment"


def test_the_skill_names_no_channel_and_no_workspace_identifier():
    """A Slack channel or team id is the commonest way a skill leaks its home."""
    text = _skill_md()
    assert not re.search(r"\b[CDGT][A-Z0-9]{8,}\b", text), "looks like a Slack id"
    assert not re.search(r"\bxox[baprs]-", text), "looks like a token"


def test_the_skill_states_no_operator_configured_value_as_if_it_were_fixed():
    """The row threshold is an operator setting, so no fixed number may be quoted.

    Naming one would be both deployment-identifying and wrong on any other
    deployment, and the renderer's own default is only a default -- the caller
    passes whatever the operator configured.
    """
    section = _skill_md().split("## A Markdown table")[1].split("\n## ")[0]
    assert "is an operator setting" in section
    assert not re.search(r"\d+\s*(?:data\s*)?rows", section), (
        "the row count that switches a table to the paged kind must stay unquoted"
    )
