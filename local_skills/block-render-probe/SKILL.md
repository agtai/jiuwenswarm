---
name: block-render-probe
description: Post one hardcoded fixture message that exercises the Slack rich-block renderer (Markdown tables, mermaid and Block Kit charts, the fence vocabulary, and their negative cases). Temporary, disposable skill for manually verifying the renderer in a live channel. Use only when explicitly asked to probe, test, or verify Slack block-kit / rich-block / data_table / data_visualization rendering.
---

# Block Render Probe

`<skill>/scripts/probe.py` prints one sample message per `--type <kind>`. Run it and post its output as your entire reply, exactly as printed.

## The one rule that matters

**Reply with the script's stdout verbatim, unchanged, as your whole message.** Do not summarize it, describe it, reformat it, fix its Markdown, or wrap it in commentary. Do not add a preamble, a "here is the output" line, or a note about what the fixture is for. Do not paraphrase the pie-chart segments or retype the table by hand.

The thing under test is the path from raw text to Block Kit blocks on the live channel — not your ability to write a good table or a good chart. If you rewrite, tidy, or narrate the fixture instead of relaying it byte-for-byte, that path never gets exercised and the probe proves nothing. A sibling skill has failed exactly this way before: it replied *about* a report instead of relaying the report itself.

Copy the command's stdout into your reply and send it. Nothing else.

## Usage

```bash
python3 <skill>/scripts/probe.py --type <kind>
```

Run with no `--type` (or an unrecognized one) to print the list of valid kinds to stderr.

## The fence vocabulary under test

Five fences decide what is drawn, and nothing else does — no marker beside the fence, and nothing in the reply around it:

- ` ```mermaid ` — drawn as a diagram.
- ` ```vega-lite ` — drawn as a chart, however this connector can draw it.
- ` ```blockkit ` — drawn as the Block Kit blocks its JSON describes.
- ` ```slack-raw ` — never drawn; shown as the source it holds.
- ` ``` ` (unnamed) — never drawn; shown as the source it holds.

Slack draws four chart types — pie, bar, area and line — and four sources reach them: a mermaid `pie`, a mermaid `xychart-beta` (bar and line), a `vega-lite` spec (all four), and hand-written `blockkit`. mermaid has no area chart of any kind, so an area chart comes from `vega-lite` or `blockkit` or not at all. Every parser declines a shape it does not recognise rather than guessing at it, so a fence that must fall through to source is a result and not a bug.

## Available kinds

Tables (row counts are the point — the renderer's threshold sits at 20 data rows):

- `table-small` — 5 data rows, under the threshold. Should stay a plain `table`, shown whole.
- `table-large` — 22 data rows, over the threshold, with an ordinary sentence (not a heading) above it. Should become a paginated `data_table` whose caption falls back to the renderer's generic word.
- `table-heading` — 21 data rows directly under a Markdown heading. Should become a `data_table` whose caption is taken from that heading.
- `table-numeric` — 24 data rows with an all-numeric ID column running 1 through 24, straddling the point where alphabetical and numeric order disagree ("10" before "9"). Should become a `data_table` that sorts the ID column as numbers, not text.

Charts:

- `chart-pie` — a mermaid `pie` chart in a plain ` ```mermaid ` fence with nothing beside it. Should render as a chart.
- `chart-bar` — hand-written Block Kit `data_visualization` (bar) in a ` ```blockkit ` fence. Should render as a chart, with the x and y axes titled `Day` and `Count`. Those two axis titles belong inside `axis_config`; written as siblings of `series` Slack refuses the whole message rather than ignoring them, so an untitled pair of axes here means the payload has regressed.
- `chart-area` — hand-written Block Kit `data_visualization` (area, two series) in a ` ```blockkit ` fence. Should render as a chart, axes titled `Quarter` and `Units`.
- `chart-triple` — three `data_visualization` blocks in one fence, one more than Slack allows per message. Should be declined locally (the whole message falls back to plain text) rather than posted and refused by Slack.
- `chart-xy-bar` — a mermaid `xychart-beta` bar chart in a plain ` ```mermaid ` fence. Should render as a bar chart: `Mon=4  Tue=7  Wed=3  Thu=9`, x axis titled `Day`, y axis `Runs`. The declared `0 --> 10` range is dropped — Slack scales to the data — so a y axis that does not stop at 10 is correct.
- `chart-xy-line` — the same fence with two *named* plots. Should render as a line chart with two lines in the legend, `P50` (12, 15, 11, 14) well below `P99` (88, 94, 76, 91). `line` is the chart type Slack's own summary sentence omits; if this comes back as bars, that omission was right.
- `chart-vega-bar` — a Vega-Lite `bar` spec in a ` ```vega-lite ` fence. Should render as the same chart `chart-xy-bar` does, from a different language: `Mon=4  Tue=7  Wed=3  Thu=9`.
- `chart-vega-area` — a Vega-Lite `area` spec whose `color` channel splits the rows into two series. Should render as an area chart, `Free` (12000, 13500, 15200) layered with `Paid` (4500, 4800, 5100). Area is the one chart type no mermaid fence can reach.
- `chart-vega-pie` — a Vega-Lite `arc` mark, which is Vega-Lite's pie. Should render as a pie of `Done` 3, `In progress` 2, `Blocked` 1 — the same slices `chart-pie` draws.

Block types:

- `section-plain` — a hand-written `section` carrying nothing interactive. Should render on a channel with no configured block-type allow-list, and stay source on one whose allow-list omits `section`.

Shown as source, not drawn — these must all stay visible as text:

- `mermaid-raw` — the same pie chart as `chart-pie`, in a ` ```slack-raw ` fence. Should stay visible as mermaid source.
- `mermaid-bare` — the same pie chart again, in a fence naming no language. Should stay visible as mermaid source.
- `blockkit-raw` — the same bar chart as `chart-bar`, in a ` ```slack-raw ` fence. Should stay visible as JSON source.
- `json-fence` — the same bar chart in a ` ```json ` fence. Should stay visible as JSON source.

Refused — these are valid fences whose contents must be declined, leaving the source on screen:

- `section-button` — a `section` with a button. The type is not what refuses it: `section-plain` renders. Anything a reader could click is refused separately, and by default, because a reader cannot tell a button a reply drew from a real approval prompt in the same channel.
- `hidden-action-id` — an inert block type carrying a stray `action_id` field. Should still be refused: this exercises the field half of the interactive check, which a visible button would not.
- `malformed-json` — invalid JSON in a ` ```blockkit ` fence, sitting beside a valid short table. The fence should degrade to source while the table beside it still renders normally — one bad fence should cost only itself, not the message.
- `vega-scatter` — a Vega-Lite `point` mark, which is a scatter plot. Slack has no scatter and no continuous x-axis, so the spec should stay visible as JSON rather than being redrawn as the nearest chart Slack does have. A bar or line chart appearing here is the failure, not the absence of one.
- `xy-broken` — a mermaid `xychart-beta` with three categories and only two values. Slack requires exactly one data point per category, and filling the gap with a zero nobody wrote would be a wrong chart rather than an incomplete one, so the whole diagram should stay visible as mermaid source. This is also what a future mermaid release would produce if it moved the syntax — an undrawn fence, not a wrong chart — which is the reason the beta diagram type is safe to read at all.

Mixed:

- `mixed-report` — prose, a heading, a mermaid chart, and a table together, the shape a real report takes.
