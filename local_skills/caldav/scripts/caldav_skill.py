#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "caldav==2.1.0",
#     "icalendar>=6,<7",
#     "requests",
#     "vobject",
# ]
# ///
"""Read and write a CalDAV calendar, and render the answer for a chat channel.

One script, four subcommands, all of them talking to one CalDAV server through
the `caldav` library:

  list-calendars   the principal's calendars, with display name, id and URL
  list-events      a date-range query, answered by the server
  create-event     add one VEVENT to a named calendar
  delete-event     remove one VEVENT, by UID

**Every read is a `REPORT`/`calendar-query` with a `time-range` filter, and
every write is a `PUT` through the library.** Neither is an implementation
detail that could be swapped for something simpler:

- A range query asks the *server* which events fall in the window, and asks it
  to expand recurrences into concrete occurrences. Fetching a collection and
  filtering locally would have to reimplement RRULE, EXDATE, RDATE, overriding
  instances and floating-time semantics, and would get a large calendar wrong
  slowly. Server-side matching is the entire reason to speak CalDAV rather than
  read files.
- A write through the API is validated by the server before it is stored: UID
  presence, one logical item per resource, component type matching the
  collection, and recurrence sanity. Writing a file into the collection's
  storage directory skips that check, and an item that fails it poisons every
  later request that touches the collection -- not just the request that wrote
  it. There is no path in this script that writes anything but an HTTP request.

The script holds no chat credential and posts nothing anywhere. It prints its
answer on stdout and exits; delivery is the caller's business.

Dependencies are declared inline, PEP 723, and the shebang runs the file under
`uv run --script`. uv resolves and caches the environment on first run and
reuses it after, so the pins travel with the script and no environment path is
compiled into it.

`caldav` is pinned exactly, and the pin is load-bearing. From 2.2 onward the
library depends on `niquests`, which pulls `urllib3-future`, which installs a
`.pth` file that replaces `urllib3` in the environment at interpreter startup --
outside the package manager and invisible to a freeze. Pinning 2.1.0 keeps that
mechanism out of the environment entirely. `requests` and `vobject` are declared
here because 2.1.0 imports both at module scope while declaring neither in its
own metadata; without them the import fails outright. `icalendar` is pinned to
its 6 series because this script builds VEVENT objects with it directly and 6->7
was a breaking major, while `caldav` itself asks only for `>6.0.0`.
"""

from __future__ import annotations

import argparse
import email.utils
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# ------------------------------------------------------------------ constants

#: Environment variables holding the server and the account. Names are defaults,
#: not literals: every one of them can be pointed elsewhere with a flag, so a
#: deployment that already names its variables differently does not have to
#: rename them to use this skill.
DEFAULT_URL_ENV = "CALDAV_URL"
DEFAULT_USERNAME_ENV = "CALDAV_USERNAME"
DEFAULT_PASSWORD_ENV = "CALDAV_PASSWORD"
DEFAULT_TIMEZONE_ENV = "CALDAV_TIMEZONE"

#: Block Kit limits, verified against a live workspace rather than read off
#: Slack's type tables. See the slack-block-kit-reference skill.
CARD_TITLE_CHARACTERS = 150
CARD_SUBTITLE_CHARACTERS = 150
CARD_BODY_CHARACTERS = 200
CARD_SUBTEXT_CHARACTERS = 200
CAROUSEL_MAX_CARDS = 10

#: How much table a single message may carry before rows are dropped. A chat
#: message has a hard character ceiling and a table that crosses it is not
#: truncated, it is refused -- so the count is bounded here, where the run can
#: say how many rows it dropped, rather than at the transport, where it cannot.
TABLE_CHARACTER_BUDGET = 3200

#: Every event this script writes carries this PRODID. It names the software,
#: not the installation: a PRODID travels inside the event to every other client
#: that ever reads the calendar.
PRODID = "-//caldav skill//CalDAV skill//EN"

#: What a `--uid` may contain. A UID becomes part of the resource path on the
#: server, so a value with a slash, a space or a percent in it either lands
#: somewhere unintended or fails to round-trip. Generated UIDs are always inside
#: this set; the check exists for the ones a caller supplies.
UID_ALLOWED = re.compile(r"^[A-Za-z0-9._@:+-]{1,255}$")

EVENT_TABLE_COLUMNS = ("When", "Summary", "Where", "UID")
ATTENDEES_COLUMN = "Attendees"

#: How much of a table cell an attendee list may fill. Independent of the
#: overall TABLE_CHARACTER_BUDGET, which drops whole rows: a cap here stops one
#: event with a long attendee list from making every other cell in its row look
#: reasonable while it alone runs past a sane width.
ATTENDEE_CELL_CHARACTERS = 160

#: What `--attendee` accepts once a display name has been stripped off: a
#: local part, an `@`, and a domain with at least one dot. Not a full RFC 5322
#: validator -- it exists to keep obvious non-addresses ("phone me", a bare
#: name) from being written into a URI property that every other client on the
#: calendar will try to read as one.
ATTENDEE_ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: Weekday names, spelled out here rather than taken from ``strftime``, whose
#: ``%a`` follows whatever locale the host happens to be set to. A weekday
#: printed in one language on one host and another language elsewhere stops
#: being the cross-check it is printed to be.
WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# ------------------------------------------------------------------- plumbing


def _configure_utf8_stdio() -> None:
    """Write UTF-8 whatever the ambient locale says.

    Event summaries carry whatever the person who wrote them typed, and a run
    under a C locale would die on the first non-ASCII character in somebody's
    calendar -- after the writes, before the output.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


class Refusal(SystemExit):
    """A stop with a message the operator can act on.

    Every failure this script chooses -- a missing credential, an unknown
    calendar, an unparseable date -- is raised as one of these with the fix in
    the text. Nothing is downgraded to an empty result: an empty agenda and a
    calendar that could not be reached read identically in a channel, and only
    one of them is true.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ------------------------------------------------------------- configuration


def resolve_setting(env_name: str, override: str | None) -> str:
    value = (override or os.environ.get(env_name, "")).strip()
    return value


def resolve_connection(args: argparse.Namespace) -> tuple[str, str, str]:
    """The server URL, username and password, or a hard stop naming what is missing.

    All three are read from the environment, and all three are checked in one
    pass so an operator setting up the skill is told everything that is absent
    at once rather than discovering them one failed run at a time.

    There is deliberately no anonymous fallback and no prompt. A CalDAV server
    with no credential answers either 401 or -- worse -- a different principal's
    empty calendar, and both of those reach a channel as "you have nothing on".
    The password is read here and never printed, never logged and never written
    to any file this script creates.
    """
    url = resolve_setting(args.url_env, args.base_url)
    username = resolve_setting(args.username_env, None)
    password = resolve_setting(args.password_env, None)

    missing = []
    if not url:
        missing.append((args.url_env, "the CalDAV server's base URL"))
    if not username:
        missing.append((args.username_env, "the account to authenticate as"))
    if not password:
        missing.append((args.password_env, "that account's password"))
    if missing:
        lines = [
            "Cannot reach any calendar: "
            + ", ".join(name for name, _ in missing)
            + (" is" if len(missing) == 1 else " are")
            + " not set in this environment.",
            "",
            "Set the following where this process reads its environment, then run again:",
        ]
        lines += [f"  {name}    {what}" for name, what in missing]
        lines += [
            "",
            f"Refusing to carry on without {'it' if len(missing) == 1 else 'them'}. An "
            "unauthenticated CalDAV request returns either a refusal or somebody "
            "else's empty calendar, and an empty calendar is indistinguishable from "
            "a quiet day once it reaches a reader.",
        ]
        if not url:
            lines += [
                "",
                f"{args.url_env} is the server root or the principal's collection "
                "home, for example https://calendar.example.org/ -- the script "
                "discovers the principal and its calendars from there.",
            ]
        raise Refusal("\n".join(lines))
    return url, username, password


def resolve_timezone(args: argparse.Namespace) -> ZoneInfo | timezone:
    """The zone naive times are read in and every time is printed in.

    A calendar is a local-time object: "the ninth at nine" means nine where the
    person saying it is, and a run that silently read it as UTC would file the
    event an hour or nine out and show every existing event at the wrong time.
    So the zone is explicit -- a flag, or a variable, or the host's own zone --
    and it is printed in the output so a reader can see which one was used.
    """
    name = resolve_setting(args.timezone_env, args.timezone)
    if not name:
        local = datetime.now().astimezone().tzinfo
        return local if local is not None else timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise Refusal(
            f"Unknown time zone {name!r} ({exc}). Give an IANA zone name such as "
            f"Europe/Paris or America/New_York, with --timezone or in "
            f"{args.timezone_env}."
        ) from None


# ----------------------------------------------------------- date parsing


RELATIVE = re.compile(r"^(?P<sign>[+-])(?P<count>\d+)(?P<unit>[hdw])$")

_DATETIME_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


@dataclass(frozen=True)
class Moment:
    """A parsed `--start`/`--from` value, and whether it named a time of day.

    The distinction is the whole point of the type. `2026-09-01` and
    `2026-09-01T00:00` are the same instant and mean different things: the first
    is a day, and a day used as a range end means *the end of* that day, while a
    day used as an event start means an all-day event. Losing that at the parse
    boundary is how a query for "today" comes back empty and a birthday gets
    filed as a midnight appointment.
    """

    value: datetime
    date_only: bool

    @property
    def as_date(self) -> date:
        return self.value.date()


def parse_moment(text: str, tz: ZoneInfo | timezone, *, now: datetime | None = None) -> Moment:
    """Parse one date or date-time, in *tz* unless the text carries its own offset.

    Accepted, in the order they are tried:

    - `now` -- this instant, to the minute.
    - `today`, `tomorrow`, `yesterday` -- dates, not instants.
    - `+7d`, `-1d`, `+2w`, `+6h` -- offsets from now. The day and week forms are
      dates (today plus the offset); the hour form is an instant, because an
      offset in hours that rounded to a day would be a silent lie.
    - `2026-09-01` -- a date.
    - `2026-09-01T14:30`, with or without seconds, `T` or a space -- an instant
      in *tz*.
    - anything `datetime.fromisoformat` accepts, including a trailing `Z` and an
      explicit offset -- an instant, in the offset it names.

    A naive value is *localised*, never converted: the digits a caller typed are
    the digits that appear in the calendar.
    """
    raw = text.strip()
    if not raw:
        raise Refusal("Empty date. Give a date, a date-time, or one of now/today/tomorrow.")
    reference = (now or datetime.now(tz)).astimezone(tz)
    lowered = raw.lower()

    if lowered == "now":
        return Moment(reference.replace(second=0, microsecond=0), False)
    if lowered in ("today", "tomorrow", "yesterday"):
        offset = {"today": 0, "tomorrow": 1, "yesterday": -1}[lowered]
        day = reference.date() + timedelta(days=offset)
        return Moment(datetime.combine(day, time(0, 0), tzinfo=tz), True)

    relative = RELATIVE.match(lowered)
    if relative:
        count = int(relative.group("count"))
        if relative.group("sign") == "-":
            count = -count
        unit = relative.group("unit")
        if unit == "h":
            return Moment(
                (reference + timedelta(hours=count)).replace(second=0, microsecond=0), False
            )
        days = count * (7 if unit == "w" else 1)
        day = reference.date() + timedelta(days=days)
        return Moment(datetime.combine(day, time(0, 0), tzinfo=tz), True)

    try:
        day = date.fromisoformat(raw)
    except ValueError:
        pass
    else:
        return Moment(datetime.combine(day, time(0, 0), tzinfo=tz), True)

    for fmt in _DATETIME_FORMATS:
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        return Moment(parsed.replace(tzinfo=tz), False)

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise Refusal(
            f"Cannot read {text!r} as a date or time. Use YYYY-MM-DD, "
            "YYYY-MM-DDTHH:MM, a full ISO 8601 timestamp, or one of "
            "now / today / tomorrow / yesterday / +7d / -1d / +2w / +6h."
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return Moment(parsed, False)


def range_bounds(
    from_text: str, to_text: str, tz: ZoneInfo | timezone, *, now: datetime | None = None
) -> tuple[datetime, datetime]:
    """The half-open window `[start, end)` a `--from`/`--to` pair asks for.

    `--to` given as a bare date means *through the end of that day*, so
    `--from 2026-09-01 --to 2026-09-01` is that whole day and not an empty
    window. Taken literally, a date is midnight, and midnight to midnight is
    nothing -- a range that returns no events for a day full of them, which
    reads in a channel as a free day. The humane reading is the one implemented,
    and it is the only place this script departs from a literal parse.

    A `--to` that names a time of day is used exactly as given: someone who
    wrote `T18:00` meant six, and rounding that up to midnight would hand back
    six hours they excluded on purpose.
    """
    start = parse_moment(from_text, tz, now=now)
    end = parse_moment(to_text, tz, now=now)
    end_value = (
        datetime.combine(end.as_date + timedelta(days=1), time(0, 0), tzinfo=end.value.tzinfo)
        if end.date_only
        else end.value
    )
    if end_value <= start.value:
        raise Refusal(
            f"Empty range: --from {from_text!r} is not before --to {to_text!r} "
            f"({start.value.isoformat()} to {end_value.isoformat()}). A bare date "
            "in --to means the end of that day, so a single day is "
            "--from <day> --to <day>."
        )
    return start.value, end_value


# ------------------------------------------------------------- CalDAV access


@dataclass(frozen=True)
class CalendarRef:
    """One calendar, reduced to what any of this script's output needs."""

    ident: str
    name: str
    url: str
    handle: Any = None

    def as_dict(self) -> dict[str, str]:
        return {"id": self.ident, "name": self.name, "url": self.url}


def connect(url: str, username: str, password: str) -> Any:
    """A `DAVClient` for *url*, or a hard stop explaining what the server said.

    The import sits inside the function so that `--help`, argument validation
    and every unit test run without the library present: nothing about the
    verb surface depends on being able to reach a server.
    """
    try:
        import caldav
    except ModuleNotFoundError as exc:  # pragma: no cover - environment fault
        raise Refusal(
            f"The CalDAV client library is not available ({exc}). This script "
            "declares its own dependencies inline and expects to be run with "
            "`uv run`; run it through its shebang, or with "
            "`uv run --script <this file> ...`."
        ) from None
    return caldav.DAVClient(url=url, username=username, password=password)


def calendar_id_from_url(url: str) -> str:
    """The last path segment of a collection URL -- what `--calendar` matches on.

    A display name is chosen by whoever made the calendar and can be changed,
    repeated across calendars, or absent. The path segment is unique within a
    principal by construction, which makes it the identifier and the display
    name a label.
    """
    return url.rstrip("/").rsplit("/", 1)[-1]


def list_calendars(client: Any) -> list[CalendarRef]:
    """Every calendar under the authenticated principal, in display order.

    Address books are not here and are not an omission: this is a CalDAV skill,
    and the server returns collections of both kinds from the same home.
    Filtering is left to the library, which asks for calendars specifically.
    """
    try:
        principal = client.principal()
        found = principal.calendars()
    except Exception as exc:
        raise Refusal(describe_connection_failure(exc)) from None
    refs = []
    for handle in found:
        url = str(handle.url)
        try:
            name = handle.get_display_name() or ""
        except Exception:
            name = ""
        ident = calendar_id_from_url(url)
        refs.append(CalendarRef(ident=ident, name=name or ident, url=url, handle=handle))
    refs.sort(key=lambda ref: (ref.name.lower(), ref.ident))
    return refs


def describe_connection_failure(exc: Exception) -> str:
    """Turn a library exception into something an operator can act on.

    The three failures worth telling apart are a wrong password, an unreachable
    host and a URL that is not a CalDAV endpoint. They arrive as different
    exception types with unhelpful text, and undistinguished they all read as
    "it did not work".
    """
    text = f"{type(exc).__name__}: {exc}".strip()
    lowered = text.lower()
    if "401" in text or "unauthorized" in lowered or "authoriz" in lowered:
        return (
            "The server refused the credentials. Check the username and password "
            "variables name the right account, and that the password is the "
            f"account's own and not a hash of it.\n\n{text}"
        )
    if "connection" in lowered or "refused" in lowered or "timed out" in lowered:
        return (
            "Could not reach the CalDAV server at all. Check the URL variable and "
            f"that the server is running and reachable from here.\n\n{text}"
        )
    return (
        "The server did not answer as a CalDAV endpoint. Check that the URL "
        "variable points at the server root or the principal's collection home, "
        f"not at a single .ics file or a web UI.\n\n{text}"
    )


def pick_calendar(refs: Sequence[CalendarRef], wanted: str) -> CalendarRef:
    """The one calendar *wanted* names, or a stop that lists the alternatives.

    Matching runs from most to least exact -- path id, then display name, then a
    unique case-insensitive substring of either -- and stops at the first tier
    that matches anything. Falling through tiers rather than merging them means
    a calendar whose id is exactly what was typed always wins over one that
    merely contains it.

    Two matches is a refusal, never a pick. Guessing between "Work" and
    "Workshop" writes an event into somebody else's week, and an event in the
    wrong calendar is not visibly wrong to the person who asked for it.
    """
    if not refs:
        raise Refusal(
            "This account has no calendars. Create one on the server, or check "
            "that the username variable names the right account."
        )
    needle = wanted.strip()
    lowered = needle.lower()
    tiers: list[list[CalendarRef]] = [
        [ref for ref in refs if ref.ident == needle],
        [ref for ref in refs if ref.name.lower() == lowered or ref.ident.lower() == lowered],
        [ref for ref in refs if lowered in ref.name.lower() or lowered in ref.ident.lower()],
    ]
    for tier in tiers:
        if len(tier) == 1:
            return tier[0]
        if len(tier) > 1:
            listed = ", ".join(f"{ref.name} ({ref.ident})" for ref in tier)
            raise Refusal(
                f"--calendar {wanted!r} matches more than one calendar: {listed}. "
                "Name one exactly, by its id."
            )
    listed = "\n".join(f"  {ref.ident}    {ref.name}" for ref in refs)
    raise Refusal(
        f"No calendar matches --calendar {wanted!r}. This account has:\n{listed}\n\n"
        "Match on the id in the first column, or on the display name."
    )


# ------------------------------------------------------------ event handling


@dataclass(frozen=True)
class Attendee:
    """One ATTENDEE property, reduced to what this script ever prints: an
    address and, if the property carried a CN parameter, a display name.

    `email` never carries the `mailto:` prefix -- that belongs to the URI form
    ATTENDEE is written and read as, not to anything this script shows a reader.
    """

    email: str
    name: str = ""

    def label(self) -> str:
        """What to print for one attendee: the name if there is one, else the address."""
        return self.name or self.email

    def as_dict(self) -> dict[str, str]:
        return {"email": self.email, "name": self.name}


def parse_attendee(raw: str) -> Attendee:
    """One `--attendee` value as an address and an optional name, or a refusal.

    ATTENDEE is a URI property -- `mailto:` is the URI this script writes,
    because it is the only address form an email turns into without guessing.
    Three shapes are accepted, tried in this order:

    - `mailto:alice@example.org` -- already the URI ATTENDEE wants.
    - `Alice Liddell <alice@example.org>` -- RFC 5322 mailbox form; the name
      becomes the property's CN parameter.
    - `alice@example.org` -- a bare address, no name.

    Anything else -- a phone number, a name with no address, a URI in another
    scheme -- is refused rather than written. A value ATTENDEE cannot use as a
    URI is not a smaller version of the feature; it is a property that breaks
    every other client reading this event afterward.
    """
    text = raw.strip()
    if not text:
        raise Refusal('--attendee is empty. Give an email address, or "Name <email>".')
    if text.lower().startswith("mailto:"):
        name, address = "", text[len("mailto:") :].strip()
    else:
        name, address = email.utils.parseaddr(text)
        if not address:
            address = text
    if not ATTENDEE_ADDRESS.match(address):
        raise Refusal(
            f"--attendee {raw!r} is not a usable address. Give a plain email "
            'address (alice@example.org), a display name and address '
            '("Alice Liddell <alice@example.org>"), or an explicit '
            "mailto:alice@example.org. ATTENDEE is a URI property, and this "
            "cannot be turned into one, so it is refused rather than written."
        )
    return Attendee(email=address, name=name.strip())


@dataclass(frozen=True)
class EventRow:
    """One occurrence, flattened out of a VEVENT for display and for `--json`."""

    uid: str
    summary: str
    location: str
    description: str
    start: datetime | date
    end: datetime | date | None
    all_day: bool
    recurring: bool
    attendees: tuple[Attendee, ...] = ()

    def as_dict(self, tz: ZoneInfo | timezone) -> dict[str, Any]:
        """The row as data, for `--json`.

        `weekday` is derivable from `start` and is included anyway. `--json` is
        the path taken when the answer is going to be *written* rather than
        relayed, which is exactly where a weekday gets counted off a date by
        hand and comes out a day wrong; handing it over costs one string.
        """
        return {
            "uid": self.uid,
            "summary": self.summary,
            "location": self.location,
            "description": self.description,
            "start": iso_of(self.start, tz),
            "end": iso_of(self.end, tz) if self.end is not None else None,
            "weekday": WEEKDAY_NAMES[as_instant(self.start, tz).date().weekday()],
            "all_day": self.all_day,
            "recurring": self.recurring,
            "attendees": [attendee.as_dict() for attendee in self.attendees],
        }

    def sort_key(self, tz: ZoneInfo | timezone) -> tuple[float, str]:
        return (as_instant(self.start, tz).timestamp(), self.summary.lower())


def as_instant(value: datetime | date, tz: ZoneInfo | timezone) -> datetime:
    """*value* as an aware datetime in *tz*, whether it arrived as a date or not.

    An all-day event's DTSTART is a bare date with no zone at all, and a
    floating event's DTSTART is a naive datetime that means "wherever the reader
    is". Both are pinned to the run's zone here, once, so that everything
    downstream -- sorting, formatting, the range check -- compares like with
    like instead of raising on the first mixed pair.
    """
    if isinstance(value, datetime):
        return value.astimezone(tz) if value.tzinfo is not None else value.replace(tzinfo=tz)
    return datetime.combine(value, time(0, 0), tzinfo=tz)


def iso_of(value: datetime | date, tz: ZoneInfo | timezone) -> str:
    if isinstance(value, datetime):
        return as_instant(value, tz).isoformat()
    return value.isoformat()


def text_of(component: Any, key: str) -> str:
    value = component.get(key)
    if value is None:
        return ""
    return str(value).strip()


def attendees_of(component: Any) -> tuple[Attendee, ...]:
    """Every ATTENDEE on *component*, in the order the property appears.

    `icalendar` hands back a single `vCalAddress` when a property occurs once
    and a list when it occurs more than once -- the same shape it uses for every
    multi-valued property -- so both are normalised into a tuple here rather
    than at every call site.
    """
    raw = component.get("ATTENDEE")
    if raw is None:
        return ()
    values = raw if isinstance(raw, list) else [raw]
    attendees = []
    for value in values:
        text = str(value)
        address = text[len("mailto:") :] if text.lower().startswith("mailto:") else text
        params = getattr(value, "params", {})
        name = str(params.get("CN", "")).strip()
        attendees.append(Attendee(email=address, name=name))
    return tuple(attendees)


def event_rows(objects: Iterable[Any], tz: ZoneInfo | timezone) -> list[EventRow]:
    """Every VEVENT in *objects*, as rows, sorted by when it starts.

    A search result is one object per occurrence once expanded, but a single
    object can still carry several components -- an unexpanded series with
    overriding instances is the usual case -- so every VEVENT in every object is
    walked rather than only the first. An object with none is skipped in
    silence: the server may return a VTIMEZONE-only resource, and that is not a
    problem worth telling a reader about.
    """
    rows: list[EventRow] = []
    for obj in objects:
        try:
            calendar = obj.icalendar_instance
        except Exception:
            continue
        for component in calendar.walk("VEVENT"):
            start_prop = component.get("DTSTART")
            if start_prop is None:
                continue
            start = start_prop.dt
            end_prop = component.get("DTEND")
            end: datetime | date | None = end_prop.dt if end_prop is not None else None
            if end is None and component.get("DURATION") is not None:
                try:
                    end = start + component.get("DURATION").dt
                except Exception:
                    end = None
            rows.append(
                EventRow(
                    uid=text_of(component, "UID"),
                    summary=text_of(component, "SUMMARY") or "(no summary)",
                    location=text_of(component, "LOCATION"),
                    description=text_of(component, "DESCRIPTION"),
                    start=start,
                    end=end,
                    all_day=not isinstance(start, datetime),
                    recurring=component.get("RRULE") is not None
                    or component.get("RECURRENCE-ID") is not None,
                    attendees=attendees_of(component),
                )
            )
    rows.sort(key=lambda row: row.sort_key(tz))
    return rows


def search_range(
    calendar: Any, start: datetime, end: datetime, *, expand: bool
) -> tuple[list[Any], str]:
    """The server's answer to a `calendar-query` over `[start, end)`.

    This is a `REPORT` with a `time-range` filter inside a `VEVENT`
    `comp-filter`, issued by the library; nothing is fetched and filtered here.

    With *expand* set the query also asks the server to expand recurrences into
    concrete occurrences, so a weekly meeting inside the window comes back as
    one row per week rather than as one master event whose start is months
    earlier. A server that will not expand is not a failure: the same expansion
    is redone client-side from the same query's results, and the run says which
    of the two it used rather than quietly changing what the numbers mean.
    """
    if not expand:
        return calendar.search(start=start, end=end, event=True), "not expanded"
    try:
        return (
            calendar.search(start=start, end=end, event=True, expand=True, server_expand=True),
            "expanded by the server",
        )
    except Exception:
        return (
            calendar.search(start=start, end=end, event=True, expand=True),
            "expanded by the client (the server declined)",
        )


def build_event(
    *,
    summary: str,
    start: Moment,
    end: Moment,
    location: str,
    description: str,
    uid: str,
    attendees: Sequence[Attendee] = (),
    now: datetime | None = None,
) -> bytes:
    """One VEVENT in one VCALENDAR, as bytes ready to `PUT`.

    Built with `icalendar` rather than by formatting a string, because a summary
    is arbitrary text and iCalendar's escaping is not obvious: an unescaped
    comma or semicolon in a summary silently splits the property into a list,
    and a newline in a description ends it early and leaves the rest of the file
    to be parsed as garbage. The library gets that right; a format string gets
    it right until the first person types a comma.

    An all-day event is one whose start and end were both given as bare dates.
    Its DTEND is exclusive, which is iCalendar's own rule and not this script's:
    a one-day event on the first ends on the second. The end is nudged forward
    when a caller gives the same date twice, because "all day on the first" is
    what they meant and a zero-length all-day event is what they would get.

    Each attendee becomes one ATTENDEE property carrying a `mailto:` URI, with a
    CN parameter when a display name was given -- see `parse_attendee`.

    No ORGANIZER is written. The only account-shaped value available in here is
    the CalDAV username, which authenticates the connection; nothing says it is
    also an address, and treating it as one would write a value that no other
    client reading this event could act on. There is no other configured value
    that is documented as this account's own address, so none is invented.
    """
    from icalendar import Calendar as ICalendar
    from icalendar import Event as IEvent
    from icalendar import vCalAddress, vText

    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    all_day = start.date_only and end.date_only

    container = ICalendar()
    container.add("prodid", PRODID)
    container.add("version", "2.0")

    event = IEvent()
    event.add("uid", uid)
    event.add("dtstamp", stamp.replace(microsecond=0))
    event.add("summary", summary)
    if all_day:
        finish = end.as_date
        if finish <= start.as_date:
            finish = start.as_date + timedelta(days=1)
        event.add("dtstart", start.as_date)
        event.add("dtend", finish)
    else:
        event.add("dtstart", start.value)
        event.add("dtend", end.value)
    if location:
        event.add("location", location)
    if description:
        event.add("description", description)
    for attendee in attendees:
        value = vCalAddress(f"mailto:{attendee.email}")
        if attendee.name:
            value.params["cn"] = vText(attendee.name)
        event.add("attendee", value)
    container.add_component(event)
    return container.to_ical()


def check_uid(value: str) -> str:
    if not UID_ALLOWED.match(value):
        raise Refusal(
            f"--uid {value!r} is not usable. A UID becomes part of the resource "
            "path on the server, so it is restricted here to letters, digits and "
            ". _ @ : + -, up to 255 characters. Omit --uid to have one generated."
        )
    return value


# ---------------------------------------------------------------- formatting


def day_label(value: date) -> str:
    """A date with its weekday in front of it: ``Thu 2026-08-20``.

    The weekday is printed because it is the half of the question a reader is
    usually asking -- "Wednesday or Thursday" -- and the half most easily got
    wrong when it is worked out from the date by hand instead of read off it.
    Date to weekday is a fixed function, so it is computed once here, where it
    is tested, rather than again by whoever reads the row; and printing the two
    together puts an off-by-one somewhere it can be seen, instead of somewhere
    it silently decides which day the answer was about.
    """
    return f"{WEEKDAY_NAMES[value.weekday()]} {value.isoformat()}"


def format_when(row: EventRow, tz: ZoneInfo | timezone) -> str:
    """One cell saying when an occurrence is, in the run's zone.

    Every date carries its weekday; see `day_label`. All-day events print the
    day and say so, because a date shown as `00:00` is read as a midnight
    appointment. A timed event prints its date once and both ends of its clock
    time, `09:00-10:00`; an event crossing midnight prints the second date too,
    since a bare end time earlier than the start time otherwise looks like a
    mistake.
    """
    if row.all_day:
        start_day = row.start if isinstance(row.start, date) else as_instant(row.start, tz).date()
        end_day = None
        if row.end is not None:
            end_day = row.end if isinstance(row.end, date) else as_instant(row.end, tz).date()
        if end_day is not None and (end_day - timedelta(days=1)) > start_day:
            last = end_day - timedelta(days=1)
            return f"{day_label(start_day)} - {day_label(last)} (all day)"
        return f"{day_label(start_day)} (all day)"

    begins = as_instant(row.start, tz)
    if row.end is None:
        return f"{day_label(begins.date())} {begins.strftime('%H:%M')}"
    finishes = as_instant(row.end, tz)
    if finishes.date() == begins.date():
        return (
            f"{day_label(begins.date())} {begins.strftime('%H:%M')}"
            f"-{finishes.strftime('%H:%M')}"
        )
    return (
        f"{day_label(begins.date())} {begins.strftime('%H:%M')} - "
        f"{day_label(finishes.date())} {finishes.strftime('%H:%M')}"
    )


def zone_label(tz: ZoneInfo | timezone) -> str:
    return getattr(tz, "key", None) or str(tz)


def fit(text: str, limit: int) -> str:
    """*text*, or its first *limit* characters with an ellipsis in place of the rest."""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def attendee_cell(attendees: Sequence[Attendee]) -> str:
    """Every attendee on one row, joined for one cell or one card field.

    Each one prints as its name if it has one, else its bare address -- the
    `mailto:` prefix is a detail of the URI ATTENDEE is stored as, not
    something a reader needs to see. Length is not capped here: the caller
    decides, `event_table` through `ATTENDEE_CELL_CHARACTERS`, a card through
    its own field cap.
    """
    return ", ".join(attendee.label() for attendee in attendees)


def mrkdwn(text: str, limit: int) -> dict[str, Any]:
    """A text object, which is what a card's four text fields actually take.

    Slack's own field table types `title`, `subtitle`, `body` and `subtext` as
    `String`; passing a bare string is rejected with `invalid_blocks: must
    provide an object`, and the rejection takes the whole message with it. This
    is verified against a live workspace -- see the slack-block-kit-reference
    skill, whose worked examples are right where the type tables are not.
    """
    return {"type": "mrkdwn", "text": fit(text, limit), "verbatim": False}


def cell(text: str) -> str:
    """One table cell: never empty, never able to break the row it sits in.

    A pipe inside a cell would end the cell early and shift every column after
    it, so it is replaced rather than escaped -- a table cell is not a place a
    reader needs a literal pipe. A newline does the same to the row and gets the
    same treatment. An empty cell prints an em dash, which no calendar field can
    contain, so an absent value cannot be misread as a present one.
    """
    flattened = " ".join(str(text).split()).replace("|", "│")
    return flattened if flattened else "—"


def fence(payload: dict[str, Any]) -> str:
    return "```blockkit\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n```"


def context_block(text: str) -> dict[str, Any]:
    """One `context` block carrying one text object, however many facts it states.

    A `context` block takes at most ten elements and counts a bare separator as
    an element, so five facts written as five text objects and four separators
    would spend nearly half the budget on punctuation. Composing the whole line
    into a single string spends one element on any number of facts.
    """
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": text, "verbatim": False}]}


# ------------------------------------------------------------------ renderers


def render_calendars(refs: Sequence[CalendarRef], server: str) -> str:
    """The calendar list: a context line, then one card per calendar.

    A carousel of cards rather than a table because this is a small set of
    *entities* a reader picks from, not a series of records they scan or sort.
    Each card carries the display name as its title, the id `--calendar` wants
    as its subtitle, and the collection URL as subtext for anyone pointing
    another client at it.

    A carousel holds at most ten cards, which is Block Kit's own ceiling. Past
    that the set has stopped being something to pick from by eye and the same
    data is rendered as a table, which is also sortable in the channel -- a
    reader with thirty calendars wants to search, not to swipe.
    """
    header = context_block(
        f":calendar: {len(refs)} calendar{'s' if len(refs) != 1 else ''} · {server}"
    )
    if len(refs) > CAROUSEL_MAX_CARDS:
        table = ["| Calendar | id | URL |", "| --- | --- | --- |"]
        table += [f"| {cell(ref.name)} | `{cell(ref.ident)}` | {cell(ref.url)} |" for ref in refs]
        return fence({"blocks": [header]}) + "\n\n" + "\n".join(table)

    cards = [
        {
            "type": "card",
            "slack_icon": {"type": "icon", "name": "calendar"},
            "title": mrkdwn(ref.name, CARD_TITLE_CHARACTERS),
            "subtitle": mrkdwn(f"`{ref.ident}`", CARD_SUBTITLE_CHARACTERS),
            "body": mrkdwn(f"Use `--calendar {ref.ident}` to read or write this one.",
                           CARD_BODY_CHARACTERS),
            "subtext": mrkdwn(ref.url, CARD_SUBTEXT_CHARACTERS),
        }
        for ref in refs
    ]
    blocks: list[dict[str, Any]] = [header]
    if cards:
        blocks.append({"type": "carousel", "elements": cards})
    return fence({"blocks": blocks})


def event_table(
    rows: Sequence[EventRow], tz: ZoneInfo | timezone, *, show_attendees: bool = False
) -> tuple[str, int]:
    """The events as a Markdown table, and how many rows had to be dropped.

    A table, not a carousel, and the choice is about what the data is. Events in
    a window are homogeneous records with the same four fields, read by scanning
    down one column -- which is what a table is for, and what a connector that
    converts a Markdown table into a sortable table gives for free. A carousel
    is the right shape for a handful of distinct entities and the wrong one
    here: it caps at ten, and a working week routinely has more.

    Columns are ordered by what a reader does with them. `When` leads because a
    range query is a question about time. `UID` is last and is kept, however
    ugly, because it is the argument `delete-event` takes -- a report that named
    events a reader cannot then act on would send them back to the server to
    find the identifier by hand.

    Attendees are not in this table by default. Unlike `UID`, no later command
    takes an attendee as an argument, so keeping the column costs width every
    row pays without buying back anything actionable -- and unlike `Where`, an
    attendee list has no natural upper length: a handful of names can dwarf
    every other cell in the row. `--show-attendees` adds a fifth column, `Where`
    it belongs, for the run where a reader actually asked who is on an event;
    `--json` carries attendees on every row regardless, for a caller that means
    to compute on them rather than read the table.
    """
    columns = EVENT_TABLE_COLUMNS + (ATTENDEES_COLUMN,) if show_attendees else EVENT_TABLE_COLUMNS
    header = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    lines = list(header)
    budget = TABLE_CHARACTER_BUDGET - sum(len(line) for line in header)
    dropped = 0
    for index, row in enumerate(rows):
        summary = row.summary + (" ↺" if row.recurring else "")
        cells = [cell(format_when(row, tz)), cell(summary), cell(row.location), f"`{cell(row.uid)}`"]
        if show_attendees:
            cells.append(cell(fit(attendee_cell(row.attendees), ATTENDEE_CELL_CHARACTERS)))
        line = "| " + " | ".join(cells) + " |"
        if budget - len(line) < 0 and index:
            dropped = len(rows) - index
            break
        budget -= len(line) + 1
        lines.append(line)
    return "\n".join(lines), dropped


def render_events(
    ref: CalendarRef,
    rows: Sequence[EventRow],
    start: datetime,
    end: datetime,
    tz: ZoneInfo | timezone,
    expansion: str,
    total: int | None = None,
    show_attendees: bool = False,
) -> str:
    """The range query's answer: a context line saying what was asked, then the table.

    The context line is metadata and stays metadata -- which calendar, which
    window, how many, expanded how -- rather than being written out as a
    sentence above the table. A reader checking whether the window was the one
    they meant finds it in one place every time, and a run that returns nothing
    still says what it looked for, which is the difference between "you are free"
    and "the question was wrong".

    The window is printed the way it was asked for, with the end shown as the
    last day it includes rather than as the exclusive midnight actually sent, so
    a reader comparing it to what they typed sees what they typed. Both ends
    carry their weekday, because the window is the one line that says which days
    this run actually asked about: someone who meant Wednesday and Thursday and
    queried Friday can see it here rather than infer it from the rows.

    The count is what the *server matched*, not what survived `--limit` or the
    message's character budget. A line reading "5 events" above five rows out of
    forty is worse than no count at all, because it is the one number a reader
    would quote; what was cut is stated separately and by how much.
    """
    last_day = (end - timedelta(seconds=1)).date()
    window = f"{day_label(start.date())} → {day_label(last_day)}"
    matched = len(rows) if total is None else total
    facts = [
        f":calendar: {ref.name}",
        window,
        f"{matched} event{'s' if matched != 1 else ''}",
        zone_label(tz),
        expansion,
    ]
    if not rows:
        return fence({"blocks": [context_block(" · ".join(facts))]})
    table, dropped = event_table(rows, tz, show_attendees=show_attendees)
    hidden = dropped + max(0, matched - len(rows))
    if hidden:
        facts.append(f"{hidden} not shown")
    return fence({"blocks": [context_block(" · ".join(facts))]}) + "\n\n" + table


def render_event_card(
    ref: CalendarRef,
    row: EventRow,
    tz: ZoneInfo | timezone,
    *,
    heading: str,
    icon: str,
) -> str:
    """One event as one standalone card -- the shape for a singleton.

    A write touches exactly one event, so what comes back is one entity and not
    a set: a carousel of one card is a swipe control with nothing to swipe to,
    and a table of one row is a header and a row. The card carries the summary
    as its title, when and where as subtitle and body, and the UID as subtext,
    because the UID is what a follow-up command takes and it belongs on the
    reply that created it.

    Attendees, when there are any, join the body. A single card has no width to
    protect the way a table row does, so nothing is held back the way it is in
    `event_table` -- this is "the event's own detail" `--show-attendees`
    documents as the alternative to a table column.

    The heading is a `context` block above the card rather than a line of prose:
    *what happened* is metadata about the card, and the card is the event.
    """
    when = format_when(row, tz)
    body_parts = [when]
    if row.location:
        body_parts.append(row.location)
    if row.description:
        body_parts.append(row.description)
    if row.attendees:
        body_parts.append("with " + attendee_cell(row.attendees))
    return fence(
        {
            "blocks": [
                context_block(f"{heading} · {ref.name} · {zone_label(tz)}"),
                {
                    "type": "card",
                    "slack_icon": {"type": "icon", "name": icon},
                    "title": mrkdwn(row.summary, CARD_TITLE_CHARACTERS),
                    "subtitle": mrkdwn(when, CARD_SUBTITLE_CHARACTERS),
                    "body": mrkdwn(" · ".join(body_parts[1:]) or when, CARD_BODY_CHARACTERS),
                    "subtext": mrkdwn(f"`{row.uid}`", CARD_SUBTEXT_CHARACTERS),
                },
            ]
        }
    )


# ---------------------------------------------------------------- subcommands


def cmd_list_calendars(args: argparse.Namespace) -> int:
    url, username, password = resolve_connection(args)
    refs = list_calendars(connect(url, username, password))
    if args.json:
        print(json.dumps({"calendars": [ref.as_dict() for ref in refs]}, indent=2))
        return 0
    if not refs:
        print(
            "This account has no calendars. Create one on the server, or check "
            "that the username variable names the right account."
        )
        return 0
    print(render_calendars(refs, url.rstrip("/")))
    return 0


def cmd_list_events(args: argparse.Namespace) -> int:
    tz = resolve_timezone(args)
    start, end = range_bounds(args.range_from, args.range_to, tz)
    url, username, password = resolve_connection(args)
    refs = list_calendars(connect(url, username, password))
    ref = pick_calendar(refs, args.calendar)
    try:
        found, expansion = search_range(ref.handle, start, end, expand=not args.no_expand)
    except Exception as exc:
        raise Refusal(describe_connection_failure(exc)) from None
    rows = event_rows(found, tz)
    matched = len(rows)
    if args.limit and len(rows) > args.limit:
        rows = rows[: args.limit]
    if args.json:
        print(
            json.dumps(
                {
                    "calendar": ref.as_dict(),
                    "from": start.isoformat(),
                    "to": end.isoformat(),
                    "timezone": zone_label(tz),
                    "expansion": expansion,
                    "matched": matched,
                    "events": [row.as_dict(tz) for row in rows],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    print(
        render_events(
            ref, rows, start, end, tz, expansion, total=matched, show_attendees=args.show_attendees
        )
    )
    return 0


def cmd_create_event(args: argparse.Namespace) -> int:
    tz = resolve_timezone(args)
    start = parse_moment(args.start, tz)
    end = parse_moment(args.end, tz)
    if start.date_only != end.date_only:
        raise Refusal(
            "--start and --end must agree about whether this is an all-day event: "
            "give both as bare dates for an all-day event, or both with a time of "
            f"day. Got --start {args.start!r} and --end {args.end!r}."
        )
    if not start.date_only and end.value <= start.value:
        raise Refusal(
            f"--end {args.end!r} is not after --start {args.start!r}. An event that "
            "ends before it starts is refused by the server, and one that ends "
            "exactly when it starts is invisible in most clients."
        )
    summary = args.summary.strip()
    if not summary:
        raise Refusal("--summary is empty. An event with no summary shows as a blank row.")
    uid = check_uid(args.uid) if args.uid else str(uuid.uuid4())
    attendees = [parse_attendee(raw) for raw in args.attendee]

    url, username, password = resolve_connection(args)
    refs = list_calendars(connect(url, username, password))
    ref = pick_calendar(refs, args.calendar)
    payload = build_event(
        summary=summary,
        start=start,
        end=end,
        location=(args.location or "").strip(),
        description=(args.description or "").strip(),
        uid=uid,
        attendees=attendees,
    )
    try:
        ref.handle.save_event(payload.decode("utf-8"))
    except Exception as exc:
        raise Refusal(describe_write_failure(exc, uid)) from None

    rows = event_rows([_LocalObject(payload)], tz)
    if args.json:
        print(json.dumps({"calendar": ref.as_dict(), "event": rows[0].as_dict(tz)}, indent=2,
                         ensure_ascii=False))
        return 0
    print(render_event_card(ref, rows[0], tz, heading="Event created", icon="calendar"))
    return 0


def cmd_delete_event(args: argparse.Namespace) -> int:
    tz = resolve_timezone(args)
    uid = check_uid(args.uid)
    url, username, password = resolve_connection(args)
    refs = list_calendars(connect(url, username, password))
    ref = pick_calendar(refs, args.calendar)
    try:
        event = ref.handle.event_by_uid(uid)
    except Exception as exc:
        raise Refusal(
            f"No event with UID {uid!r} in {ref.name} ({ref.ident}). Run list-events "
            "over a window that contains it to read the UID from the last column; "
            "a UID is per calendar, so check this is the calendar holding it.\n\n"
            f"{type(exc).__name__}: {exc}"
        ) from None
    rows = event_rows([event], tz)
    try:
        event.delete()
    except Exception as exc:
        raise Refusal(describe_write_failure(exc, uid)) from None

    if args.json:
        print(
            json.dumps(
                {
                    "calendar": ref.as_dict(),
                    "deleted": rows[0].as_dict(tz) if rows else {"uid": uid},
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0
    if not rows:
        print(fence({"blocks": [context_block(f":calendar: Deleted `{uid}` from {ref.name}")]}))
        return 0
    print(render_event_card(ref, rows[0], tz, heading="Event deleted", icon="trash"))
    if rows[0].recurring:
        print(
            "\nThat was a recurring event: deleting by UID removes the whole "
            "series, not one occurrence."
        )
    return 0


class _LocalObject:
    """Just enough of a caldav object for `event_rows` to read one we just built.

    The alternative is a second parser for the event this run has in its hands,
    which would be the one code path whose output was never compared against the
    server's. Rendering the created event through exactly the same function that
    renders a fetched one keeps the reply honest about what was stored.
    """

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    @property
    def icalendar_instance(self) -> Any:
        from icalendar import Calendar as ICalendar

        return ICalendar.from_ical(self._payload)


def describe_write_failure(exc: Exception, uid: str) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    lowered = text.lower()
    if "403" in text or "forbidden" in lowered:
        return (
            "The server refused the write. Either the account may not write to "
            f"this collection, or it rejected the event as invalid.\n\n{text}"
        )
    if "409" in text or "412" in text or "precondition" in lowered:
        return (
            f"The server refused the write for UID {uid!r}. A CalDAV server "
            "validates on write -- one logical item per resource, a component "
            "type the collection accepts, a UID, and recurrence bounds that make "
            f"sense -- and this did not pass.\n\n{text}"
        )
    return f"The write did not complete.\n\n{text}"


# ------------------------------------------------------------------- parsing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="caldav_skill.py", description=__doc__.splitlines()[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def common(target: argparse.ArgumentParser) -> None:
        target.add_argument(
            "--base-url",
            help="the CalDAV server's base URL, overriding the environment for "
            "this run only. The server address is configuration and is not "
            "compiled into this skill.",
        )
        target.add_argument("--url-env", default=DEFAULT_URL_ENV,
                            help=f"variable holding the base URL (default {DEFAULT_URL_ENV})")
        target.add_argument("--username-env", default=DEFAULT_USERNAME_ENV,
                            help=f"variable holding the username (default {DEFAULT_USERNAME_ENV})")
        target.add_argument("--password-env", default=DEFAULT_PASSWORD_ENV,
                            help=f"variable holding the password (default {DEFAULT_PASSWORD_ENV})")
        target.add_argument(
            "--timezone",
            help="IANA zone naive times are read in and every time is printed in. "
            "Defaults to the timezone variable, then to the host's own zone.",
        )
        target.add_argument("--timezone-env", default=DEFAULT_TIMEZONE_ENV,
                            help=f"variable holding the zone (default {DEFAULT_TIMEZONE_ENV})")
        target.add_argument(
            "--json",
            action="store_true",
            help="print the result as JSON instead of rendered blocks, for a "
            "caller that is going to compute on it rather than show it",
        )

    calendars = sub.add_parser("list-calendars", help="the principal's calendars")
    common(calendars)
    calendars.set_defaults(func=cmd_list_calendars)

    events = sub.add_parser(
        "list-events",
        help="events in a date range, matched and expanded by the server",
    )
    common(events)
    events.add_argument("--calendar", required=True,
                        help="calendar id or display name; see list-calendars")
    events.add_argument("--from", dest="range_from", required=True,
                        help="window start: a date, a date-time, or now/today/tomorrow/+7d")
    events.add_argument(
        "--to",
        dest="range_to",
        required=True,
        help="window end. A bare date means the end of that day, so --from and "
        "--to on the same date is that whole day.",
    )
    events.add_argument("--limit", type=int, default=0,
                        help="show at most this many events; 0 means no limit")
    events.add_argument(
        "--no-expand",
        action="store_true",
        help="return recurring events as their master event rather than as one "
        "row per occurrence in the window. Faster, and much harder to read.",
    )
    events.add_argument(
        "--show-attendees",
        action="store_true",
        help="add an Attendees column to the table. Off by default -- most "
        "events have none, and one that has several can dwarf every other "
        "cell in its row; --json carries attendees on every row regardless.",
    )
    events.set_defaults(func=cmd_list_events)

    create = sub.add_parser("create-event", help="add one event to a calendar")
    common(create)
    create.add_argument("--calendar", required=True)
    create.add_argument("--start", required=True,
                        help="a date for an all-day event, or a date-time")
    create.add_argument("--end", required=True,
                        help="same kind as --start. For an all-day event this is "
                        "exclusive, per iCalendar: a one-day event ends the next day.")
    create.add_argument("--summary", required=True)
    create.add_argument("--location")
    create.add_argument("--description")
    create.add_argument("--uid", help="use this UID instead of a generated one, so "
                        "that re-running replaces the event rather than adding a second")
    create.add_argument(
        "--attendee",
        action="append",
        default=[],
        metavar="ADDRESS",
        help="add one attendee: an email address, \"Display Name <email>\", or "
        "an explicit mailto:<email>. Repeatable. Written as an ATTENDEE "
        "property -- this records who the event is for, and does not send "
        "an invitation; see SKILL.md.",
    )
    create.set_defaults(func=cmd_create_event)

    delete = sub.add_parser("delete-event", help="remove one event, by UID")
    common(delete)
    delete.add_argument("--calendar", required=True)
    delete.add_argument("--uid", required=True,
                        help="the UID from the last column of list-events. For a "
                        "recurring event this removes the whole series.")
    delete.set_defaults(func=cmd_delete_event)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.func
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
