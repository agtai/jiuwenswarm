# The findings

The render step reads one JSON object, either passed on the command
(`--findings - <<'JSON' … JSON`) or read from a file. It holds the judgement half
of the report and nothing else: which changes mattered, which way a theme is
moving, what to do about it.

**The object below is the whole document.** Nothing wraps it. The fetch prints
this same shape on stdout under `template`, with every key present and one worked
example under each; copying that and filling it in is the shortest correct route,
and a key of your own beside these — a `generated_at_utc`, a `findings` holding
the rest — makes the file carry none of the schema, so the report renders with
everything missing.

**Every value in `template` is marked `PLACEHOLDER-REPLACE-THIS`, and nothing
carrying that marker is ever published.** The examples are there to show what an
item's own fields are called, which an empty array cannot do. They are not
findings and cannot become one by being left where they are: the renderer drops
every entry still holding the marker, names the drop under *Reporting
Shortfalls*, and refuses outright if one somehow reaches the rendered text.
Replace each example with what this run found, or delete it.

**There is no field for a count anywhere in this schema, and that is deliberate.**
Every number the report states — issues, pull requests, merges, commits, releases,
per window — is read by the renderer out of the run's own file. A count written
by hand reads exactly like a measured one once it is in the text, and the observed
failure was per-theme figures invented to fill a template: real-looking daily
numbers beside sevens and thirties that were all zero, in a window where neither
was. Removing the field removes the failure.

The renderer also supplies, without being asked: the title and date, the
repository and window line, the coverage verdict, the activity table, the section
order, the brief/detail split, and a note when the window had to be widened to
cover one an earlier run missed. None of that is yours to write, and none of it
can be omitted by forgetting it.

It also appends, to *Evidence Gaps*, everything the run itself could not cover:
each coverage warning, each summary list that showed fewer records than it
counted, and the number of items active in the window that the deep-read sample
was too small to inspect. These are the gaps nothing in the material reminds a
writer of, which is exactly why they come from the run and not from you.

A separate section, *Reporting Shortfalls*, says where the report fell short of
its own rules — an unlinked conclusion, an untitled item. That is a different
statement from an evidence gap: a gap says what could not be established about
the repository, a shortfall says what this document failed to state properly, and
filing the second under the first would let a reporting failure read as a fact
about the project. It is written entirely by the renderer; see below.

**Every section is rendered on every run.** A key you leave out does not remove
its section; it renders the section with a line saying nothing was found. So the
question each key asks you is only ever "what did this run find?", never "is this
section worth having today" — that second question is already answered, the same
way, for every run. Leaving a key out is a positive statement that the run looked
and found nothing, and it will be published as one.

## Shape

```json
{
  "tldr": [
    {"severity": "critical", "text": "…", "original": "…"}
  ],
  "significant_changes": [
    {
      "title": "…",
      "label": "fact",
      "text": "…",
      "original": "…",
      "evidence": [{"label": "PR #123", "url": "https://…"}]
    }
  ],
  "risks": [
    {"severity": "critical", "text": "…", "evidence": [{"label": "#123", "url": "https://…"}]}
  ],
  "actions": [{"text": "…"}],
  "trends": [
    {
      "theme": "…",
      "direction": "rising",
      "text": "…",
      "confidence": "high",
      "evidence": [{"label": "#123", "url": "https://…"}]
    }
  ],
  "missing_capabilities": {
    "explicit": [{"text": "…"}],
    "inferred": [{"text": "…", "confidence": "medium"}],
    "insufficient": [{"text": "…"}]
  },
  "opportunities": [
    {
      "title": "…",
      "kind": "Systems engineering",
      "user_value": "High",
      "research_value": "Medium",
      "effort": "Medium",
      "risk": "Low",
      "recommendation": "…"
    }
  ],
  "evidence_gaps": {
    "known": [{"text": "…"}],
    "unknown": [{"text": "…"}],
    "needed": [{"text": "…"}]
  }
}
```

## Fields

| Key | Required | Cap | Notes |
| --- | --- | --- | --- |
| `tldr` | yes | 3 | `severity` is `critical`, `major` or `stable`; defaults to `stable` |
| `significant_changes` | yes | 5 | at least one item, unless the run measured a completely quiet window (see below); each needs a `title` and at least one evidence link, and an item missing either is published carrying ⚠️ |
| `risks` | no | 5 | renders "None identified in this window." when empty |
| `actions` | no | 5 | renders "None; nothing in this window calls for one." when empty |
| `trends` | no | — | `direction` is `rising`, `stable` or `cooling`; `confidence` and evidence are both required; renders "None; no theme moved enough this window to state a direction." when empty |
| `missing_capabilities` | no | — | three groups; every `inferred` item states a confidence; renders "None identified in this window." when empty |
| `opportunities` | no | — | `title` and `kind` required; each unstated grade renders `Unknown`; renders "None identified in this window." when empty |
| `evidence_gaps` | no | — | three groups; the run's own coverage limits are appended to whatever is here |

Every entry is an object, and every entry that states a sentence states it in
`text` — the one exception is `opportunities`, whose entries are graded fields
and a `recommendation` rather than a sentence. Where the finding rests on source
text in another language, put the rendering in `text` and the source's own
wording in `original`; the renderer places the original in parentheses *after*
the rendering, which is the order the language gate checks and the order a
reader needs.

**The field names above are the only ones read, on every item as well as at the
top level.** A value under any other name is not read, not rendered and not
inferred from — an evidence url written as `link`, a sentence written as
`summary`, a trend written as `name`/`trend`. Nothing is accepted as an alias,
however clear the intent: a second name for a field is permanent once it works,
and the item that carries one goes on reporting itself as having no evidence and
nothing to say. Every populated name the renderer does not read is instead named
under *Reporting Shortfalls*, together with the names it does read for that item,
so the loss is visible in the run that caused it.

`original` is for wording the reader would otherwise not see — a title in another
language, a commit subject your sentence paraphrases. **An `original` that
repeats `text` is dropped**, because "(original: …)" tells a reader the two
differ and printing a sentence after itself says the opposite. There is nothing
to fix when that happens; the field simply has no work to do, and the honest
form is to leave it out.

## What the renderer publishes with a warning

An item that falls short of one of these rules is **still published**, marked
with ⚠️ where it falls short, and named under a *Reporting Shortfalls* section
the renderer writes itself. The render exits 0: it produced a finished report,
and that report is the deliverable exactly as it stands.

- A significant change or trend signal with **no evidence link**. It renders as
  "⚠️ No evidence link — this conclusion is unverified.", which is what the rule
  was for: the reader is told which claim is unbacked, at the claim.
- **A url on the item under a name that is not `evidence`.** The url is named and
  left where it is — it is not read, because that would make the wrong name work
  — and the item renders "⚠️ Evidence not published — a url arrived under `link`,
  not `evidence`." rather than the line above. Seen live under `link`, and under
  a bare `url` sitting on the item instead of inside an evidence entry. The
  distinction is the point: the evidence was gathered, so calling the conclusion
  unverified is false, and it is false in the one direction that hides the cause
  from both the reader and the writer.
- **An evidence reference whose url is under a name that is not `url`**, or which
  is a bare value rather than an object. Dropped, and marked "⚠️ Evidence not
  published — a reference carried its url under `link`, not `url`." for the same
  reason.
- **Any populated key on any item that the renderer does not read.** Named in the
  shortfall alongside the keys that item *is* read for. This is the general case
  of the two above and is not a list of known mistakes: whatever name gets
  invented next is reported the same way.
- An evidence entry with no `url`, or one that is not `http`/`https`. The
  reference is dropped rather than published, because a link nobody can follow
  looks like the guarantee was met.
- An evidence `label` containing `<`, `>` or `|` — those are the link syntax. The
  url takes the label's place, so the reference survives its caption.
- A `severity`, `direction`, `label` or `confidence` outside its vocabulary. The
  item renders unrated rather than borrowing the default: a green mark beside an
  item its writer called urgent is a wrong answer that looks like a measured one.
- A significant change, opportunity or trend signal missing its `title`, `kind`
  or `theme`. It renders under `(untitled)` and keeps its body and evidence.
- A channel brief over its length budget. Every section is delivered; the host
  chooses the split point instead of the budget.

## What the renderer drops

One case, and it is neither of the two above. **An entry still carrying
`PLACEHOLDER-REPLACE-THIS` is removed rather than published or refused.** It is
not published because nobody wrote it: a ⚠️ beside an unasserted sentence makes it
look reviewed rather than making it true, and the format is the whole reason a
fabricated report was believed here once already. It does not refuse because one
stray example beside four real findings is not a reason to lose the four. The
removal is named under *Reporting Shortfalls*, with the key it came from.

An example *evidence reference* is dropped on its own, one level down, and the
item that carried it survives and renders "⚠️ No evidence link" — the writer's own
sentence is theirs whatever they left attached to it.

A template copied and left entirely unfilled therefore refuses, but on the honest
ground: every entry is dropped, `tldr` is empty, and that is the refusal below.
The drops are printed on stderr before it, so the reason is visible.

## When `significant_changes` may be empty

**Only when the run measured a completely quiet window** — every measure in the
report's own activity table reading zero for the window: issues opened and
updated, PRs opened, updated and merged, closes, commits, releases. The section
then renders "None; this run measured no issue, pull request, commit or release
activity in the window, so there was no change to weigh."

The gate is the run's counts and never what you wrote, which is the distinction
that matters: "nothing happened" is a fact the fetch measured, "nothing was
written" is a fact about the document. A window with any activity in it still
refuses, and the refusal names what was counted — because a window with a real
change in it always offers a truthful item to write, and only a window with none
leaves invention as the only way out. The rule is checkable from the report
itself: the table is in the same message.

`tldr` gets no such allowance. A quiet window can honestly have no significant
change; it cannot honestly have no judgement, because "nothing moved in this
window" *is* the judgement and is one line. The TL;DR is most of what the channel
message carries, and an empty one leaves a reader unable to tell a quiet window
from a run that gave up.

**None of this is suppressible.** There is no findings key that writes to that
section, removes a line from it, or empties it — a check a run can silence is the
same as no check. Fix the findings and render again if you can improve them, but
**never re-run the render unchanged**: the report is finished, an identical
command produces an identical report, and a host that watches for repeated
identical calls ends the run.

## What the renderer refuses

These exit 2 with the reason on stderr. Each means there is nothing worth
rendering — not that one item is weak — so each is fixed in the findings and
rendered again. Rendering consumes nothing.

- **A findings file in another schema**, or one holding content under a *top-level*
  key this renderer does not read. Everything under an unrecognised key is
  dropped, so the report would be missing what the file says. The same mistake
  inside an item is a warning rather than a refusal — the rest of the report is
  intact and deliverable — but it is reported just as plainly.
- **An empty `tldr`**, always. It is most of what the channel message carries, and
  a report whose first section is empty cannot be told apart from a run that
  analysed nothing.
- **An empty `significant_changes` on a window that was not quiet**, as above.
- **A `PLACEHOLDER-REPLACE-THIS` anywhere in the rendered text.** Reaching that
  point means the removal above did not catch it, so there is no entry to drop
  and no honest report to publish around it.
- **A filesystem path anywhere in the rendered text.** A path is input. It
  publishes the host's layout to whoever can read the channel and there is
  nothing the reader can do with it. The refusal is deliberate rather than a
  quiet strip: a sentence written around a path still claims something the reader
  cannot check once the path is gone.
- **Activity that is not a fetcher run**, and a run directory with no manifest.
  Every number in the report is read from that file; without it there is no
  measured half to render.
