<!-- Must hold before anything below is filled in. Delete this block before publishing. -->

**Every URL must appear verbatim in a `free_search` result or a `fetch_webpage`
response from this run.** Never construct a URL from a headline, a domain and a
guess at the slug. Holding a title with no URL is not permission to derive one:
fetch the page to obtain the real link, or drop the item. A guessed slug is
often a working link — that is what makes it dangerous, because it reads as a
citation while pointing somewhere nobody checked. Record each URL as it is
retrieved, and before delivering, verify the finished file against that record:

```bash
python3 <skill>/scripts/check_links.py <digest>.md --retrieved retrieved-urls.txt
```

A non-zero exit means the digest is not ready. `UNSOURCED` names a citation
nobody opened; do not resolve it by opening the link now and keeping the
sentence, because the sentence was written before anything was read.

# AI monitor — {PERIOD_LABEL}

<!-- The three dates on the next line must come from recorded `date -u +%F`
     output, never from memory and never inferred from the material. Run it:

       date -u +%F

     A model's sense of what today is comes from its training data and is
     routinely wrong by months or more, and the window is the one fact in a
     digest that cannot be wrong -- a reader who catches a date they know to be
     off stops trusting every number on the page. If `date` has not been run in
     this session, stop and run it before filling these in. If it cannot be run,
     say the window is unverified rather than guessing one.

     Delete this block before publishing. -->

*Covering {WINDOW_START} – {WINDOW_END} · compiled {COMPILED_DATE}*

## Top line

{Two to four sentences. What changed that a reader acting in this space would
need to know. If nothing did, say so plainly — a quiet week is a real finding
and padding it is how a monitor loses its reader.}

## Headlines

### {Headline — the specific claim, not the topic}
**{Topic}** · {Date} · [{Source}]({URL}){, confirmed with the primary source | , vendor-reported | , self-reported | , paywalled | , claimed, unreplicated | , unconfirmed}

{Two to four sentences: what happened, the number or capability that makes it
matter, and what it changes for someone building on this. Include the caveat
that a careful reader would want — hardware and batch size for a throughput
claim, availability date for a hardware announcement, whether an eval is
self-reported.}

{Repeat per headline — 3 to 6 of them.}

{Use as many tags as apply — a vendor-run benchmark reported behind a paywall is
both. Reach for `unconfirmed` whenever the claim was not checked against its
primary source, rather than leaving the reader to assume it was.}

## Also notable

- **{Topic}** — {One line, with the fact in it.} [{Source}]({URL})

## Watching

- {Thread that has not resolved yet and what would resolve it.}

## Coverage notes

{Only when it affects how far the reader should trust what is above: claims that
could not be checked against a primary source, sources that would not load,
paywalls hit, numbers reported as published rather than re-derived. Leave the
section out entirely when there is nothing to declare.}

---

## Notes for whoever fills this in — delete before publishing

**Topic labels** are the reader-facing names. Use these, never the internal beat
numbering:

`Agents & protocols` · `Inference & serving` · `Hardware` · `Models` ·
`Evaluation` · `Business & infrastructure` · `Policy & security`

**The digest must stand on its own.** Assume the reader has never seen this
skill, its configuration, or its previous runs — they have a page in front of
them and nothing else. So:

- Do not name the process: no beat numbers, no "the sweep", no step names, no
  ledger, no similarity hints, no "first run" or "no prior history".
- Do not list what was searched. The reader wants findings, not a work log. If a
  whole area was quiet, say the reader-facing thing — "nothing shipped in
  hardware this week" — rather than reporting which categories were queried.
- Coverage notes are about **trust in what is printed**, not about scope of
  effort. "This number is as published by the vendor, not re-derived" earns
  trust. "Beats 1–4 were swept" is a work log and means nothing to the reader.
- Continuity is fine when it carries meaning for the reader — "this resolves the
  licensing question left open on 26 July" — and is dead weight when it is only
  bookkeeping.
