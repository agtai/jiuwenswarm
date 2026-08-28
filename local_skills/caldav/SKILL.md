---
name: caldav
description: >-
  Read and write calendars on a CalDAV server: list the account's calendars,
  answer a date-range question with a server-side calendar-query, add an event,
  and delete an event by UID. Use when asked what is on the calendar, what is on
  a given day or week, whether a time is free, when asked to put something in
  the calendar, book, schedule or add an appointment or meeting, when asked to
  cancel or remove something already in it, when asked which calendars exist,
  or when asked to add an attendee to an event or say who an event is for.
  Covers one CalDAV account across all of its calendars. Calendars only --
  contacts and address books are not in scope. Adding an attendee records them
  on the event and does not send an invitation. Every answer is printed as a
  finished, fenced blockkit block: relay it exactly as printed, fence and all,
  instead of summarising it. Query every day the reply names, in the same turn
  it names them; and when the reply asks the user to pick between candidate
  times, ask a question with options rather than listing them in prose.
---

# CalDAV

One script talks to one CalDAV server on behalf of one account. It answers
questions about what is in a calendar and it writes events into one.

`<skill>` below means this skill's own directory. Resolve it to an absolute path
before running anything; the script does not infer it.

**The server's address is configuration and is not in this skill.** Nor is the
account, nor the password. All three are read from the environment, and a run
that cannot find them stops and says which are missing rather than reporting an
empty calendar.

## Prerequisites

`uv` must be on the path. The script declares its own dependencies inline (PEP
723) and its shebang runs it under `uv run --script`, so there is no environment
to create, activate or maintain: uv resolves the pins on first run, caches the
result, and reuses it every run after. Invoke the script directly, or with
`uv run --script <skill>/scripts/caldav_skill.py ...` if the executable bit has
been lost.

**The `caldav` pin is exact and must stay exact.** From 2.2 onward the library
pulls a transitive dependency that installs a `.pth` file replacing `urllib3` in
whatever environment it lands in, at interpreter startup, outside the package
manager. Pinning 2.1.0 keeps that out. Two of 2.1.0's own runtime imports are
missing from its metadata and are declared in the script instead; see the header
comment in the script for which and why. Do not "fix" an import error by
loosening the pin.

## Configuration

Three variables, read from the process environment:

| Variable | Holds |
|---|---|
| `CALDAV_URL` | the server's base URL, or the account's collection home |
| `CALDAV_USERNAME` | the account to authenticate as |
| `CALDAV_PASSWORD` | that account's password |

A fourth, `CALDAV_TIMEZONE`, is optional: an IANA zone name such as
`Europe/Paris`, used to read times given without one and to print every time in
the output. Without it the host's own zone is used.

Set them wherever this host loads the environment its tools inherit. **The names
are defaults, not literals** — a deployment that already names its variables
something else points the script at them with `--url-env`, `--username-env`,
`--password-env` and `--timezone-env` rather than renaming anything.

A missing variable is a hard stop naming every one that is absent, with what to
set. This is deliberate and is not a rough edge: an unauthenticated CalDAV
request returns either a refusal or a different principal's empty calendar, and
"you have nothing on" is not a safe thing to say by accident.

The password is read from the environment and never printed, never logged and
never written anywhere.

## Entry points

One script, `<skill>/scripts/caldav_skill.py`, with four subcommands. Every one
of them accepts the connection flags above, plus `--timezone` and `--json`.

`--json` prints the same answer as data instead of as rendered blocks. Use it
when the result is going to be computed on, or when the channel the answer is
going to cannot draw Block Kit — see *Where the answer is going*. Use the
default, the fenced rendering, when it is going to be shown.

### `list-calendars` — what this account has

```bash
<skill>/scripts/caldav_skill.py list-calendars
```

Every calendar under the account, with its display name, the id that
`--calendar` matches on, and its URL. Address books are not listed: this skill
is calendars.

Run this first when a calendar's name is not already known. `--calendar` matches
a path id exactly, then a display name case-insensitively, then a unique
substring of either — and **an ambiguous name is refused rather than guessed**,
because an event written into the wrong calendar does not look wrong to the
person who asked for it.

What it prints is a fenced `blockkit` block. **Relay it exactly as printed,
fence and all** — do not list the calendars again in prose.

### `list-events` — what is on, between two dates

```bash
<skill>/scripts/caldav_skill.py list-events \
  --calendar <id-or-name> \
  --from 2026-09-01 --to 2026-09-07
```

**The server answers this, not the script.** It is a `REPORT` carrying a
`calendar-query` with a `time-range` filter, and the server is also asked to
expand recurrences, so a weekly meeting inside the window comes back as one row
per week rather than as one master event whose start is months earlier. Nothing
is fetched and filtered locally, and that is the entire reason to speak CalDAV
rather than read the collection: reimplementing RRULE, EXDATE, RDATE, overriding
instances and floating time on the client is a way to be wrong slowly.

The output says which expansion was used. A server that will not expand is not a
failure — the same query's results are expanded client-side instead — but the
run says so rather than quietly changing what the rows mean.

- `--limit N` shows at most N events. The count in the header stays what the
  server matched, and how many were not shown is stated.
- `--no-expand` returns a recurring series as its master event, one row for the
  whole series. Faster, and much harder to read.
- `--show-attendees` adds a fifth column, `Attendees`, to the table. **Off by
  default**: most events have none, an attendee list has no natural upper
  length the way a location does, and no later command takes an attendee as an
  argument the way it takes a UID — so the column is there for the run where
  someone actually asked who is on an event, not on every run. `--json` carries
  each row's attendees regardless of this flag, for a caller computing on them
  rather than reading the table.

What it prints is a fenced `blockkit` block. **Relay it exactly as printed,
fence and all** — do not retype the table as sentences.

Two rules govern what the answer around it may say, and both are below in full:
**every day the answer names has to have been queried in this turn** — two days
is two runs, or one run whose window spans both — and **a weekday is resolved to
a date before it is queried, and printed beside it**. Rows and the window line
both carry the weekday already; reuse that spelling rather than working one out.
See *Naming a day*. If the answer then asks which slot to take, see *Offering a
choice*: that is a question with options, not a bulleted list.

### `create-event` — put something in

```bash
<skill>/scripts/caldav_skill.py create-event \
  --calendar <id-or-name> \
  --start 2026-09-01T09:00 --end 2026-09-01T10:00 \
  --summary "Design review" \
  --location "Room B" \
  --description "Agenda in the thread"
```

`--location` and `--description` are optional. `--uid` is optional and supplies
the event's UID instead of a generated one; giving the same UID twice **replaces**
the event rather than adding a second, which is what makes a repeated run safe.

Give both `--start` and `--end` as bare dates for an all-day event. Its end is
exclusive, which is iCalendar's rule and not this script's: a one-day event ends
on the following day, and `--start 2026-09-16 --end 2026-09-16` is written out as
the sixteenth alone. Mixing a bare date with a date-time is refused rather than
interpreted.

`--attendee` records who the event is for. Repeat it for more than one:

```bash
<skill>/scripts/caldav_skill.py create-event \
  --calendar work \
  --start 2026-09-01T09:00 --end 2026-09-01T10:00 \
  --summary "Design review" \
  --attendee "Alice Liddell <alice@example.org>" \
  --attendee bob@example.org
```

Give a plain email address, `Display Name <email>` (RFC 5322 mailbox form), or
an explicit `mailto:<email>`. Each becomes one `ATTENDEE` property on the event,
its value the `mailto:` URI, with a `CN` parameter carrying the name when one
was given:

```
ATTENDEE;CN="Alice Liddell":mailto:alice@example.org
ATTENDEE:mailto:bob@example.org
```

`mailto:` is the value written for anything shaped like an address, because it
is the only URI an address turns into without guessing. Anything that isn't --
a phone number, a name with no address, a URI in another scheme -- is **refused
rather than written**: `ATTENDEE` is a URI property, and a value that is not
one breaks every other client that reads the event afterward, not just this run.

No `ORGANIZER` is written. The only account-shaped value this script has is the
CalDAV username, which authenticates the connection; nothing says it is also an
address, and there is no other configured value documented as one. Inventing an
address for it would write something no other client could act on, so none is
set.

**Recording an attendee is not sending an invitation.** See *Attendees are not
invitations*, near the end of this document, for what a write with `--attendee`
actually does and does not cause to happen, and how that was established for
the server this skill talks to.

**The write goes through the API, always.** A CalDAV server validates on `PUT` —
one logical item per resource, a component type the collection accepts, a UID,
recurrence bounds that make sense — and that validation is the correctness
guarantee. An item written straight into the server's storage skips it, and an
invalid item there breaks every later request that touches the collection, not
just the one that wrote it. There is no path in this script that writes anything
but an HTTP request, and there must never be one.

What it prints is a fenced `blockkit` block confirming the write. **Relay it
exactly as printed, fence and all** — do not report the booking in prose.

### `delete-event` — take something out

```bash
<skill>/scripts/caldav_skill.py delete-event \
  --calendar <id-or-name> --uid <uid>
```

The UID is the last column of `list-events`. A UID belongs to a calendar, so the
same UID in another calendar is another event; a UID that is not in the named
calendar is a stop that says so rather than a silent no-op.

**Deleting by UID removes a whole recurring series, not one occurrence.** The
reply says so when that is what happened. Removing a single occurrence of a
series is not supported here.

What it prints is a fenced `blockkit` block. **Relay it exactly as printed,
fence and all** — do not confirm the removal in prose instead.

## Dates and times

Every `--from`, `--to`, `--start` and `--end` takes any of:

| Form | Means |
|---|---|
| `2026-09-01` | a date |
| `2026-09-01T14:30` | a time of day, `T` or a space, seconds optional |
| `2026-09-01T14:30:00+02:00`, `…Z` | an instant in the offset it names |
| `now` | this instant, to the minute |
| `today`, `tomorrow`, `yesterday` | dates |
| `+7d`, `-1d`, `+2w` | dates, offset from today |
| `+6h` | an instant, offset from now |

A value with no offset of its own is **localised, not converted**: the digits
typed are the digits stored. The zone used is printed in the output.

**A bare date in `--to` means the end of that day.** So `--from 2026-09-01 --to
2026-09-01` is that whole day, and not the empty midnight-to-midnight window a
literal reading would give. That is the one place the parse is not literal, and
the reason is that an empty answer for a full day reads as a free day. A `--to`
that names a time of day is taken exactly as given.

## Naming a day

**Resolve a weekday name to a date before querying, and then print both.**
"Wednesday" is not an argument; `2026-08-19` is. Work the date out first — the
relative forms in the table above, `today`, `tomorrow`, `+7d`, `-1d`, exist so
that a day named relative to now is anchored by the script rather than counted
by hand — and then say "Wednesday 19 August", never "Wednesday" on its own. A
weekday and its date written together let a reader catch an off-by-one in the
line where it happened. A weekday written alone lets it through, and everything
after it is confidently about a different day than the one asked for.

The rows this script prints already carry the weekday in front of the date, and
so does the window on the context line: `Wed 2026-08-19 → Thu 2026-08-20`. That
is the spelling to reuse. A weekday counted off a date by hand is a computation
with nothing checking it, and it is wrong often enough to matter.

**Every day the answer names must have been queried in the same turn.** One run
per day, or — better — one run whose window covers them all: `--from` and `--to`
take a range precisely so that "Wednesday or Thursday" is a single query rather
than two half-remembered ones. An earlier turn's results are not evidence about
the calendar now. Something can be added, moved or cancelled between one message
and the next, which is the whole reason someone is asking rather than
remembering.

This matters most in the sentence that introduces the answer. "I have checked
your calendar for Wednesday and Thursday" is a claim about what this run did,
and a run that queried one of them, or neither, has made a false one. An answer
asserting a check it did not perform is indistinguishable from a correct answer
until somebody goes and compares it against the calendar — which is the reason
it is worse than an obviously wrong one. If a day was not queried this turn,
query it or leave it out; do not report it from memory and do not say it was
checked.

## What it prints

The script emits the finished rendering, already wrapped in a fenced `blockkit`
block. **Emit it exactly as printed, fence and all.** It is an artifact to pass
through, not a format to compose: do not rewrite the blocks, do not summarise
the table into prose, and do not hand-write Block Kit around it. The shape of
each of these four answers is fully determined, so the script decides it once,
in code that is tested, rather than being composed again on every run.

The shapes, and why each one:

- **A carousel of cards** for the calendar list. A small set of *entities* to
  pick from, each with a name and an identifier — which is what a card is for.
  Past ten calendars, Block Kit's own ceiling on a carousel, the same data is
  rendered as a table instead: a reader with thirty calendars wants to search,
  not to swipe.
- **A Markdown table** for a range of events, under a `context` block. Events in
  a window are homogeneous records read by scanning one column, which is what a
  table is for, and a connector that converts a Markdown table into a sortable
  one gives that for free. A carousel would cap at ten, and a working week has
  more. The UID column is kept, however ugly, because it is the argument
  `delete-event` takes.
- **One standalone card** for a single event, after a write. One entity, so no
  carousel: a carousel of one is a swipe control with nothing to swipe to.
- **`context` blocks** for run metadata — which calendar, which window, how
  many, which zone — never a sentence of prose. A reader checking whether the
  window was the one they meant finds it in the same place every time.

An empty range still prints its `context` line. "You are free" and "the question
was wrong" must not read the same.

**Every date it prints carries its weekday** — `Thu 2026-08-20`, in the table's
`When` column and at both ends of the window on the context line — and `--json`
carries a `weekday` field for the same reason. Date to weekday is a fixed
function with one right answer, so the script computes it once, in code that is
tested, rather than leaving it to be counted off by hand in the sentence that
introduces the answer. Reuse what it printed; see *Naming a day*.

### Where the answer is going

Not every channel draws blocks, and the message being answered already says
which one this is: the inbound envelope carries a `source` field naming the
channel alongside the content and the timezone. Let that pick the form.

- **A channel that renders Block Kit** — a chat connector that draws blocks, a
  Slack workspace being the usual one — takes the rendering as it stands. Relay
  the fenced `blockkit` block exactly as printed. Two runs answering one
  question are relayed as two fenced blocks one after the other; there is no
  need to merge them by hand, and merging them by hand is a way to break them.
- **A channel that carries text only** — a terminal, a log, a mail body, a
  plain webhook — gets `--json` instead. Read the data and write the answer
  yourself, in whatever form that channel does read well.

**The fenced rendering is the default, and is what to send when the channel's
capability is not known.** The two ways of being wrong here are not equally
bad: fenced output on a channel that cannot render it arrives as a code block —
ugly, but every field is still there to read — while prose written in place of
the rendering loses it entirely, and nothing downstream can get it back.

## Offering a choice

**When the reply puts alternatives in front of the user and stops for one to be
picked, that is a question with options — not a bulleted list ending in "let me
know which one".** Finding a time for a meeting is the case this comes up in:
several candidate slots, exactly one of which is going to be booked. Asked as a
question, the reply comes back as a selection that the next run can act on.
Written as prose, it comes back as a sentence that has to be read and guessed
at, and on a channel that draws buttons it does not come back at all until
somebody types.

The harness's question takes a `query` and a list of `questions`. Each question
carries either `options` — between two and four, each with a `label` — or
`inputs`, for a value to be typed rather than chosen. On a channel that renders
them the options are buttons.

Two to four options is the budget, and the ceiling is doing useful work: it
forces the answer to be *the best few* candidates rather than every gap in the
day. A calendar with six free hours does not offer six slots. It offers the two
or three worth taking, and says what it passed over if that is worth saying.

A free-text escape — "or tell me another time" — belongs **inside** the question,
as a further input, not instead of it. Offering the escape in prose alongside a
prose list gives back precisely the unstructured reply the question existed to
avoid.

Two things to check before the options go out:

- **Options have to be genuine alternatives.** `16:30-17:30` and `17:00-18:00`
  overlap, so they are not two choices; they are one free stretch described
  twice, and picking one does not rule the other out. Candidates drawn from the
  same gap have to be far enough apart to be different answers.
- **An empty calendar is not the same as an available one.** Nothing is
  scheduled at 07:00 on most calendars, so a query that finds 07:00 free has
  found an absence of evidence. Proposing it is an assumption about when this
  person works, not something the calendar said. Keep candidates inside hours
  the calendar shows them already using, or offer one outside those hours while
  saying plainly that is what it is.

This is a rule about being asked to pick, not a rule about lists. "What is on
Wednesday" is answered with the report the script prints; turning that into a
question asks the reader to choose between things they were not choosing
between, which is worse than the prose it replaced.

## Attendees are not invitations

`--attendee` writes an `ATTENDEE` property onto the event. That is a `PUT`,
exactly like every other write this script makes for `SUMMARY` or `LOCATION` —
storage, and nothing more. Whether the person named actually gets told about
the event depends on something else entirely: whether the *server* implements
CalDAV Scheduling (RFC 6638, sometimes called iTIP/iMIP delivery), which is
what turns an `ATTENDEE` property into an outbound invitation, a free/busy
request, or anything else that leaves the server. Most CalDAV servers do not.

A server that does implement it says so in ways that can be checked without
guessing: its `OPTIONS` response lists `calendar-auto-schedule` in its `DAV`
compliance header, and a `PROPFIND` for `schedule-inbox-URL` and
`schedule-outbox-URL` on the principal returns those URLs rather than a 404.

**Checked directly against the server this skill is written against:** the
`OPTIONS` compliance header lists `calendar-access`, `addressbook` and
`extended-mkcol`, and not `calendar-auto-schedule`; a `PROPFIND` for
`schedule-inbox-URL` and `schedule-outbox-URL` on the principal comes back
`404 Not Found` for both. Scheduling is not implemented. An event written here
with `--attendee` sits on the calendar with that property set and nothing more
happens — no mail is sent, no notification is queued, nobody outside this
script's own process is told anything.

**Do not describe an attendee added this way as having been invited, notified,
or told.** They have been recorded on the event, which is what this skill can
promise; whether they hear about it depends entirely on whether some other
system — separate from this skill, and not verified by it — reads this
calendar and acts on what it finds. Say what happened: the event now names
them. Do not say what has not: nobody has been informed.

## Checking it against a server

The unit tests do not need one; see below. These four do, and they are what to
run against a real server after any change:

1. `list-calendars` returns the account's calendars with their display names.
2. `list-events` over a window containing a recurring event returns one row per
   occurrence, and the header says the expansion was the server's.
3. `create-event` is accepted, and the event comes back from a `list-events` over
   a window containing it.
4. `delete-event` removes it, and a second `delete-event` on the same UID stops
   with the not-found message.

Do this in a scratch calendar made for the purpose, never in one somebody uses.

## Tests

```bash
python3 -m pytest <skill>/tests -q
```

Pure logic over dictionaries, strings and files: the verb surface, date parsing,
calendar matching, iCalendar construction and escaping, the Block Kit shapes and
their character caps, and the missing-credential stop. **Nothing there opens a
socket** — a test that needed a server to be up would fail for reasons unrelated
to this code, and would stop being run. The four things that do need a server
are the list above.

The tests need `pytest` and `icalendar`; they do not need `caldav`, because the
script defers that import into the two functions that dial out precisely so the
verb surface stays testable in a bare environment.

## What it does not do

- **Contacts and address books.** CalDAV only. A server's address books are not
  listed and are never written to.
- **Invitations, free/busy, alarms and availability.** `--attendee` records who
  an event is for, but recording is all it does — see *Attendees are not
  invitations*. There is no verb that returns free slots: finding the gaps in a
  day means reading a `list-events` window and subtracting what is in it. The
  subtraction is easy and the traps are not in the arithmetic — they are in what
  gets offered afterwards, which is why they are written down under *Offering a
  choice* rather than solved with a flag.
- **Editing an event in place.** Re-run `create-event` with the same `--uid` to
  replace one; there is no partial update.
- **A single occurrence of a recurring series.** Deleting hits the whole series.
- **Creating or deleting calendars.** It reads the ones that exist and writes
  events into them.
- **Scheduling itself.** It runs when it is run, and it posts nothing anywhere;
  what it prints on stdout is the answer, and delivering that is the caller's.
