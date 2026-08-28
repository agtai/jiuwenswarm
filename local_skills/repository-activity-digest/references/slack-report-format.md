# Delivering into a chat channel

`render_report.py` emits the report already in this shape. Nothing here is a
formatting instruction to follow while writing — it is what the renderer does and
why, so that a change to it is made knowingly.

## What the renderer emits, and why that form

Emphasis as `*bold*`, links as `<https://…|label>`, bullets as `•`, and one
Markdown pipe table for the activity counts.

That is Slack's own `mrkdwn` for the parts that carry meaning, rather than
Markdown left to a conversion layer. A host may well convert Markdown — one does,
and converts `**bold**`, `[text](url)`, `#` headings and `-` bullets, and renders
pipe tables as real table blocks. But a report that depends on a conversion layer
renders wrongly the first day it is delivered somewhere without one, and the
failure is silent: the reader sees asterisks and bracket syntax, and nothing
reports an error. The forms above need no conversion anywhere.

The one exception is the table, which `mrkdwn` cannot express at all. It is
written as a Markdown pipe table because a host that renders tables wants exactly
that, and a host that does not shows aligned-enough pipes. Prohibiting tables was
the older advice here and it is no longer right.

## What does not survive, anywhere

Do not reach for these in a finding; the renderer does not emit them and a host
is not obliged to render them.

- **Headings.** Where `#` is converted at all, every level collapses to bold, so
  a heading hierarchy conveys nothing. Sections are bold lines.
- **`*italic*`.** A single asterisk is bold in `mrkdwn`. Emphasis inside prose has
  no reliable form; write the sentence so it does not need one.
- **Nested list depth.** Indentation survives, the glyph does not change, and no
  host promises structure. One level.
- **Ordered-list semantics.** A numbered line is text; nothing renumbers it.
- **Horizontal rules.** `---` renders as three hyphens.

## The brief and its thread

Immediately after the channel brief the renderer emits, on its own line:

```text
<!-- jiuwenswarm:slack-thread-details -->
```

A host that recognises it posts the brief as a top-level channel message and
everything after it in that brief's own thread. A host that does not renders it
as an HTML comment and the report reads as one message — a graceful degradation,
not a failure.

**The split only happens for a message posted at channel top level.** A reply
already inside a thread has nowhere to open a thread of its own, so the marker is
stripped and brief and detail are flattened into one message. Where the host
offers a setting that puts a scheduled result at channel top level rather than in
the thread the job was created from, a recurring channel report wants it on.

## Sizes

The brief is kept under its own budget by the renderer, which refuses to emit an
over-long one rather than letting a delivery layer cut it at an arbitrary point.
Chunking below that is the host's business and is lossless where it is
implemented; what is not recoverable is a writer abbreviating the report by hand.
A report that ends in "(truncated for brevity)" has been cut by the one party in
the chain that had no size limit to obey.
