"""Tests for the parts of the skill that are decidable without a server.

Everything here is pure logic: argument handling, date parsing, calendar
matching, iCalendar construction, the Block Kit the script emits, and the
missing-credential hard stop. **Nothing in this file opens a socket.** A test
that needed a CalDAV server to be up would fail for reasons that have nothing to
do with this code, and would stop being run.

What is therefore *not* covered here, and has to be exercised against a real
server: that a `calendar-query` REPORT comes back with the events a `time-range`
matched, that the server expands recurrences when asked, that a `PUT` passes the
server's validation, and that a delete removes the resource. Those are named in
SKILL.md under *Checking it against a server*.

`caldav` itself is never imported: the script defers that import into the two
functions that dial out, precisely so that the verb surface stays testable in a
bare environment. `icalendar` is imported, by the builder under test.

Run:
    python3 -m pytest <skill>/tests -q
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import caldav_skill as cs  # noqa: E402

PARIS = ZoneInfo("Europe/Paris")
UTC = timezone.utc
NOW = datetime(2026, 8, 19, 15, 30, tzinfo=PARIS)


def namespace(**kwargs):
    """An argparse namespace with the connection defaults filled in."""
    import argparse

    base = {
        "base_url": None,
        "url_env": cs.DEFAULT_URL_ENV,
        "username_env": cs.DEFAULT_USERNAME_ENV,
        "password_env": cs.DEFAULT_PASSWORD_ENV,
        "timezone": None,
        "timezone_env": cs.DEFAULT_TIMEZONE_ENV,
        "json": False,
    }
    base.update(kwargs)
    return argparse.Namespace(**base)


def blocks_of(text: str) -> list[dict]:
    """The blocks out of a ```blockkit fence, failing loudly if it is not one."""
    assert text.startswith("```blockkit\n"), text[:40]
    body = text.split("```blockkit\n", 1)[1].split("\n```", 1)[0]
    return json.loads(body)["blocks"]


# ------------------------------------------------------------- verb surface


def test_every_verb_parses_with_its_required_arguments():
    parser = cs.build_parser()
    assert parser.parse_args(["list-calendars"]).func is cs.cmd_list_calendars
    events = parser.parse_args(
        ["list-events", "--calendar", "work", "--from", "today", "--to", "+7d"]
    )
    assert events.func is cs.cmd_list_events
    assert (events.calendar, events.range_from, events.range_to) == ("work", "today", "+7d")
    created = parser.parse_args(
        [
            "create-event",
            "--calendar", "work",
            "--start", "2026-09-01T09:00",
            "--end", "2026-09-01T10:00",
            "--summary", "Standup",
            "--location", "Room A",
            "--description", "Daily",
        ]
    )
    assert created.func is cs.cmd_create_event
    assert (created.location, created.description) == ("Room A", "Daily")
    assert created.attendee == []
    deleted = parser.parse_args(["delete-event", "--calendar", "work", "--uid", "abc"])
    assert deleted.func is cs.cmd_delete_event


def test_attendee_is_repeatable_on_create_event():
    parser = cs.build_parser()
    created = parser.parse_args(
        [
            "create-event",
            "--calendar", "work",
            "--start", "2026-09-01T09:00",
            "--end", "2026-09-01T10:00",
            "--summary", "Standup",
            "--attendee", "alice@example.org",
            "--attendee", "Bob <bob@example.org>",
        ]
    )
    assert created.attendee == ["alice@example.org", "Bob <bob@example.org>"]


def test_show_attendees_is_a_flag_on_list_events_and_off_by_default():
    parser = cs.build_parser()
    default = parser.parse_args(
        ["list-events", "--calendar", "work", "--from", "today", "--to", "today"]
    )
    assert default.show_attendees is False
    shown = parser.parse_args(
        ["list-events", "--calendar", "work", "--from", "today", "--to", "today",
         "--show-attendees"]
    )
    assert shown.show_attendees is True


@pytest.mark.parametrize(
    "argv",
    [
        ["list-events", "--from", "today", "--to", "today"],
        ["list-events", "--calendar", "work", "--to", "today"],
        ["list-events", "--calendar", "work", "--from", "today"],
        ["create-event", "--calendar", "work", "--start", "today", "--end", "today"],
        ["delete-event", "--calendar", "work"],
        ["delete-event", "--uid", "abc"],
        [],
    ],
)
def test_missing_required_argument_is_refused(argv):
    with pytest.raises(SystemExit):
        cs.build_parser().parse_args(argv)


def test_environment_variable_names_are_flags_not_literals():
    """A deployment that already names its variables differently is not forced to rename."""
    args = cs.build_parser().parse_args(
        ["list-calendars", "--url-env", "MY_URL", "--password-env", "MY_SECRET"]
    )
    assert (args.url_env, args.password_env) == ("MY_URL", "MY_SECRET")
    assert args.username_env == cs.DEFAULT_USERNAME_ENV


# ------------------------------------------------------ credentials, hard stop


def test_absent_credentials_stop_the_run_and_name_all_three(monkeypatch):
    for name in (cs.DEFAULT_URL_ENV, cs.DEFAULT_USERNAME_ENV, cs.DEFAULT_PASSWORD_ENV):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(SystemExit) as caught:
        cs.resolve_connection(namespace())
    message = str(caught.value)
    for name in (cs.DEFAULT_URL_ENV, cs.DEFAULT_USERNAME_ENV, cs.DEFAULT_PASSWORD_ENV):
        assert name in message
    assert "Refusing" in message


def test_one_absent_credential_names_only_that_one(monkeypatch):
    monkeypatch.setenv(cs.DEFAULT_URL_ENV, "https://calendar.example.org/")
    monkeypatch.setenv(cs.DEFAULT_USERNAME_ENV, "someone")
    monkeypatch.delenv(cs.DEFAULT_PASSWORD_ENV, raising=False)
    with pytest.raises(SystemExit) as caught:
        cs.resolve_connection(namespace())
    message = str(caught.value)
    assert cs.DEFAULT_PASSWORD_ENV in message
    assert cs.DEFAULT_USERNAME_ENV not in message


def test_a_blank_credential_counts_as_absent(monkeypatch):
    """An emptied variable is the commonest way a deployment loses one."""
    monkeypatch.setenv(cs.DEFAULT_URL_ENV, "https://calendar.example.org/")
    monkeypatch.setenv(cs.DEFAULT_USERNAME_ENV, "someone")
    monkeypatch.setenv(cs.DEFAULT_PASSWORD_ENV, "   ")
    with pytest.raises(SystemExit) as caught:
        cs.resolve_connection(namespace())
    assert cs.DEFAULT_PASSWORD_ENV in str(caught.value)


def test_credentials_present_are_returned_and_the_flag_beats_the_variable(monkeypatch):
    monkeypatch.setenv(cs.DEFAULT_URL_ENV, "https://from-the-environment.example/")
    monkeypatch.setenv(cs.DEFAULT_USERNAME_ENV, "someone")
    monkeypatch.setenv(cs.DEFAULT_PASSWORD_ENV, "secret")
    url, user, password = cs.resolve_connection(
        namespace(base_url="https://from-the-flag.example/")
    )
    assert url == "https://from-the-flag.example/"
    assert (user, password) == ("someone", "secret")


def test_alternate_variable_names_are_honoured(monkeypatch):
    monkeypatch.delenv(cs.DEFAULT_URL_ENV, raising=False)
    monkeypatch.setenv("OTHER_URL", "https://calendar.example.org/")
    monkeypatch.setenv("OTHER_USER", "someone")
    monkeypatch.setenv("OTHER_SECRET", "secret")
    url, user, password = cs.resolve_connection(
        namespace(url_env="OTHER_URL", username_env="OTHER_USER", password_env="OTHER_SECRET")
    )
    assert (url, user, password) == ("https://calendar.example.org/", "someone", "secret")


def test_timezone_falls_back_and_refuses_a_name_that_is_not_a_zone(monkeypatch):
    monkeypatch.setenv(cs.DEFAULT_TIMEZONE_ENV, "Europe/Paris")
    assert cs.zone_label(cs.resolve_timezone(namespace())) == "Europe/Paris"
    assert cs.zone_label(cs.resolve_timezone(namespace(timezone="UTC"))) == "UTC"
    with pytest.raises(SystemExit) as caught:
        cs.resolve_timezone(namespace(timezone="Middle/Earth"))
    assert "IANA" in str(caught.value)


# --------------------------------------------------------------- date parsing


@pytest.mark.parametrize(
    "text,expected,date_only",
    [
        ("2026-09-01", datetime(2026, 9, 1, 0, 0, tzinfo=PARIS), True),
        ("2026-09-01T14:30", datetime(2026, 9, 1, 14, 30, tzinfo=PARIS), False),
        ("2026-09-01 14:30", datetime(2026, 9, 1, 14, 30, tzinfo=PARIS), False),
        ("2026-09-01T14:30:15", datetime(2026, 9, 1, 14, 30, 15, tzinfo=PARIS), False),
        ("today", datetime(2026, 8, 19, 0, 0, tzinfo=PARIS), True),
        ("tomorrow", datetime(2026, 8, 20, 0, 0, tzinfo=PARIS), True),
        ("yesterday", datetime(2026, 8, 18, 0, 0, tzinfo=PARIS), True),
        ("now", datetime(2026, 8, 19, 15, 30, tzinfo=PARIS), False),
        ("+7d", datetime(2026, 8, 26, 0, 0, tzinfo=PARIS), True),
        ("-1d", datetime(2026, 8, 18, 0, 0, tzinfo=PARIS), True),
        ("+2w", datetime(2026, 9, 2, 0, 0, tzinfo=PARIS), True),
        ("+6h", datetime(2026, 8, 19, 21, 30, tzinfo=PARIS), False),
    ],
)
def test_moment_forms(text, expected, date_only):
    got = cs.parse_moment(text, PARIS, now=NOW)
    assert got.value == expected
    assert got.date_only is date_only


def test_naive_input_is_localised_not_converted():
    """The digits somebody typed are the digits that end up in the calendar."""
    got = cs.parse_moment("2026-09-01T09:00", PARIS, now=NOW)
    assert got.value.hour == 9
    assert cs.zone_label(got.value.tzinfo) == "Europe/Paris"


def test_an_explicit_offset_is_respected_over_the_run_zone():
    got = cs.parse_moment("2026-09-01T09:00:00Z", PARIS, now=NOW)
    assert got.value.astimezone(UTC).hour == 9
    assert got.date_only is False


@pytest.mark.parametrize("text", ["wednesday", "", "   ", "next week", "2026-13-01", "+3y"])
def test_unparseable_dates_stop_the_run(text):
    with pytest.raises(SystemExit) as caught:
        cs.parse_moment(text, PARIS, now=NOW)
    assert "YYYY-MM-DD" in str(caught.value) or "Empty date" in str(caught.value)


def test_a_bare_date_in_to_means_the_end_of_that_day():
    """The one place the parse is not literal, and the reason it is not.

    Taken literally a single-day window is midnight to midnight, which returns
    nothing for a day full of events -- and reads in a channel as a free day.
    """
    start, end = cs.range_bounds("2026-09-01", "2026-09-01", PARIS, now=NOW)
    assert start == datetime(2026, 9, 1, 0, 0, tzinfo=PARIS)
    assert end == datetime(2026, 9, 2, 0, 0, tzinfo=PARIS)


def test_a_time_of_day_in_to_is_taken_exactly():
    _, end = cs.range_bounds("2026-09-01", "2026-09-01T18:00", PARIS, now=NOW)
    assert end == datetime(2026, 9, 1, 18, 0, tzinfo=PARIS)


def test_an_inverted_range_stops_the_run():
    with pytest.raises(SystemExit) as caught:
        cs.range_bounds("2026-09-10", "2026-09-01", PARIS, now=NOW)
    assert "Empty range" in str(caught.value)


# ---------------------------------------------------------- calendar matching


REFS = [
    cs.CalendarRef("calendar", "Calendar", "https://example.org/p/calendar/"),
    cs.CalendarRef("work", "Work", "https://example.org/p/work/"),
    cs.CalendarRef("workshop", "Workshop planning", "https://example.org/p/workshop/"),
]


def test_calendar_id_is_the_last_path_segment():
    assert cs.calendar_id_from_url("https://example.org/p/work/") == "work"
    assert cs.calendar_id_from_url("https://example.org/p/work") == "work"


@pytest.mark.parametrize(
    "wanted,expected",
    [
        ("work", "work"),
        ("Work", "work"),
        ("workshop", "workshop"),
        ("Workshop planning", "workshop"),
        ("planning", "workshop"),
        ("CALENDAR", "calendar"),
    ],
)
def test_calendar_matching_runs_exact_before_fuzzy(wanted, expected):
    assert cs.pick_calendar(REFS, wanted).ident == expected


def test_an_ambiguous_name_is_refused_not_guessed():
    """Writing into the wrong calendar is not visibly wrong to whoever asked."""
    with pytest.raises(SystemExit) as caught:
        cs.pick_calendar(REFS, "wor")
    message = str(caught.value)
    assert "more than one" in message
    assert "work" in message and "workshop" in message


def test_an_unknown_name_lists_what_there_is():
    with pytest.raises(SystemExit) as caught:
        cs.pick_calendar(REFS, "holidays")
    message = str(caught.value)
    assert all(ref.ident in message for ref in REFS)


def test_no_calendars_at_all_is_its_own_message():
    with pytest.raises(SystemExit) as caught:
        cs.pick_calendar([], "work")
    assert "no calendars" in str(caught.value)


# ------------------------------------------------------------ event building


def ical_of(payload: bytes) -> str:
    return payload.decode("utf-8")


def test_a_timed_event_carries_uid_stamp_and_both_ends():
    payload = build("Standup", "2026-09-01T09:00", "2026-09-01T10:00", uid="fixed-uid")
    text = ical_of(payload)
    assert "BEGIN:VEVENT" in text and "END:VEVENT" in text
    assert "UID:fixed-uid" in text
    assert "DTSTAMP:" in text
    assert "DTSTART;TZID=Europe/Paris:20260901T090000" in text
    assert "DTEND;TZID=Europe/Paris:20260901T100000" in text
    assert "SUMMARY:Standup" in text


def build(summary, start, end, uid="uid-1", **kwargs):
    return cs.build_event(
        summary=summary,
        start=cs.parse_moment(start, PARIS, now=NOW),
        end=cs.parse_moment(end, PARIS, now=NOW),
        location=kwargs.get("location", ""),
        description=kwargs.get("description", ""),
        uid=uid,
        attendees=kwargs.get("attendees", ()),
        now=datetime(2026, 8, 19, 13, 30, tzinfo=UTC),
    )


def test_an_all_day_event_uses_dates_and_an_exclusive_end():
    """iCalendar's own rule: a one-day event ends on the following day."""
    text = ical_of(build("Offsite", "2026-09-16", "2026-09-16"))
    assert "DTSTART;VALUE=DATE:20260916" in text
    assert "DTEND;VALUE=DATE:20260917" in text


def test_a_multi_day_all_day_event_keeps_the_end_it_was_given():
    text = ical_of(build("Conference", "2026-09-16", "2026-09-18"))
    assert "DTEND;VALUE=DATE:20260918" in text


def test_punctuation_in_free_text_is_escaped_not_pasted():
    """An unescaped comma silently turns one property into a list of two."""
    text = ical_of(
        build(
            "Review, part two; final",
            "2026-09-01T09:00",
            "2026-09-01T10:00",
            description="First line\nsecond line",
        )
    )
    assert "SUMMARY:Review\\, part two\\; final" in text
    assert "\\n" in text.split("DESCRIPTION")[1][:60]


def test_the_prodid_names_the_software_and_nothing_else():
    text = ical_of(build("Anything", "2026-09-01T09:00", "2026-09-01T10:00"))
    assert "PRODID:-//caldav skill//CalDAV skill//EN" in text


@pytest.mark.parametrize("uid", ["a/b", "with space", "", "a" * 300, "one%two", "a?b"])
def test_a_uid_that_would_not_survive_a_url_is_refused(uid):
    with pytest.raises(SystemExit) as caught:
        cs.check_uid(uid)
    assert "--uid" in str(caught.value)


@pytest.mark.parametrize(
    "uid", ["abc", "2026-09-01-standup", "a.b_c@example.org", "uid+1", "T:2"]
)
def test_a_usable_uid_passes(uid):
    assert cs.check_uid(uid) == uid


def test_a_created_event_reads_back_through_the_same_row_parser():
    """The reply describes what was stored, not what was asked for."""
    payload = build("Standup", "2026-09-01T09:00", "2026-09-01T10:00", location="Room A")
    rows = cs.event_rows([cs._LocalObject(payload)], PARIS)
    assert len(rows) == 1
    assert rows[0].summary == "Standup"
    assert rows[0].location == "Room A"
    assert rows[0].all_day is False
    assert cs.format_when(rows[0], PARIS) == "Tue 2026-09-01 09:00-10:00"


# ------------------------------------------------------------------ attendees


@pytest.mark.parametrize(
    "raw,expected_email,expected_name",
    [
        ("alice@example.org", "alice@example.org", ""),
        ("Alice Liddell <alice@example.org>", "alice@example.org", "Alice Liddell"),
        ("mailto:alice@example.org", "alice@example.org", ""),
        ("MAILTO:Alice@Example.org", "Alice@Example.org", ""),
        (" bob@example.org ", "bob@example.org", ""),
    ],
)
def test_an_attendee_value_is_parsed_into_address_and_name(raw, expected_email, expected_name):
    attendee = cs.parse_attendee(raw)
    assert attendee.email == expected_email
    assert attendee.name == expected_name


@pytest.mark.parametrize(
    "raw",
    ["not an email", "Alice Liddell", "alice@", "@example.org",
     "alice@example", "tel:+15551234567", "alice example org"],
)
def test_an_unparseable_attendee_is_refused_with_the_value_and_a_remedy(raw):
    """A rejection has to name what to send instead, not just that this failed."""
    with pytest.raises(SystemExit) as caught:
        cs.parse_attendee(raw)
    message = str(caught.value)
    assert "--attendee" in message
    assert repr(raw) in message
    assert "mailto:" in message


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_attendee_is_refused_and_says_what_to_give_instead(raw):
    with pytest.raises(SystemExit) as caught:
        cs.parse_attendee(raw)
    message = str(caught.value)
    assert "--attendee" in message
    assert "email address" in message


def test_each_attendee_becomes_one_atendee_property_with_a_mailto_uri():
    """Spelled out for the reader; the docstring calls the value a URI, and it is one."""
    payload = build(
        "Design review",
        "2026-09-01T09:00",
        "2026-09-01T10:00",
        attendees=[cs.parse_attendee("Alice Liddell <alice@example.org>"),
                   cs.parse_attendee("bob@example.org")],
    )
    text = ical_of(payload)
    assert 'ATTENDEE;CN="Alice Liddell":mailto:alice@example.org' in text
    assert "ATTENDEE:mailto:bob@example.org" in text
    assert "ORGANIZER" not in text, "no defensible source for it -- see SKILL.md"


def test_an_event_with_no_attendees_carries_no_attendee_property():
    payload = build("Standup", "2026-09-01T09:00", "2026-09-01T10:00")
    assert "ATTENDEE" not in ical_of(payload)


def test_a_single_attendee_round_trips_through_the_row_parser():
    """icalendar hands back one vCalAddress for one ATTENDEE, not a list of one."""
    payload = build(
        "1:1", "2026-09-01T09:00", "2026-09-01T10:00",
        attendees=[cs.parse_attendee("alice@example.org")],
    )
    rows = cs.event_rows([cs._LocalObject(payload)], PARIS)
    assert [a.email for a in rows[0].attendees] == ["alice@example.org"]
    assert rows[0].attendees[0].name == ""


def test_several_attendees_round_trip_in_order_with_their_names():
    payload = build(
        "Design review", "2026-09-01T09:00", "2026-09-01T10:00",
        attendees=[
            cs.parse_attendee("Alice Liddell <alice@example.org>"),
            cs.parse_attendee("bob@example.org"),
            cs.parse_attendee("Carol <carol@example.org>"),
        ],
    )
    rows = cs.event_rows([cs._LocalObject(payload)], PARIS)
    attendees = rows[0].attendees
    assert [a.email for a in attendees] == [
        "alice@example.org", "bob@example.org", "carol@example.org"
    ]
    assert [a.name for a in attendees] == ["Alice Liddell", "", "Carol"]
    assert [a.label() for a in attendees] == ["Alice Liddell", "bob@example.org", "Carol"]


def test_the_json_row_carries_attendees_as_email_and_name():
    payload = build(
        "Design review", "2026-09-01T09:00", "2026-09-01T10:00",
        attendees=[cs.parse_attendee("Alice Liddell <alice@example.org>")],
    )
    rows = cs.event_rows([cs._LocalObject(payload)], PARIS)
    data = rows[0].as_dict(PARIS)
    assert data["attendees"] == [{"email": "alice@example.org", "name": "Alice Liddell"}]


def test_an_event_with_no_attendees_has_an_empty_attendees_list_in_json():
    payload = build("Standup", "2026-09-01T09:00", "2026-09-01T10:00")
    rows = cs.event_rows([cs._LocalObject(payload)], PARIS)
    assert rows[0].as_dict(PARIS)["attendees"] == []


# ---------------------------------------------------------------- formatting


def row(**kwargs):
    base = {
        "uid": "u",
        "summary": "Something",
        "location": "",
        "description": "",
        "start": datetime(2026, 9, 1, 9, 0, tzinfo=PARIS),
        "end": datetime(2026, 9, 1, 10, 0, tzinfo=PARIS),
        "all_day": False,
        "recurring": False,
    }
    base.update(kwargs)
    return cs.EventRow(**base)


def test_when_is_written_for_a_reader_not_for_a_parser():
    assert cs.format_when(row(), PARIS) == "Tue 2026-09-01 09:00-10:00"
    assert cs.format_when(row(end=None), PARIS) == "Tue 2026-09-01 09:00"
    crossing = row(end=datetime(2026, 9, 2, 1, 0, tzinfo=PARIS))
    assert cs.format_when(crossing, PARIS) == "Tue 2026-09-01 09:00 - Wed 2026-09-02 01:00"


def test_an_all_day_event_says_so_rather_than_printing_midnight():
    single = row(start=date(2026, 9, 16), end=date(2026, 9, 17), all_day=True)
    assert cs.format_when(single, PARIS) == "Wed 2026-09-16 (all day)"
    spanning = row(start=date(2026, 9, 16), end=date(2026, 9, 19), all_day=True)
    assert cs.format_when(spanning, PARIS) == "Wed 2026-09-16 - Fri 2026-09-18 (all day)"


def test_times_are_shown_in_the_run_zone():
    utc_row = row(
        start=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        end=datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
    )
    assert cs.format_when(utc_row, PARIS) == "Tue 2026-09-01 11:00-12:00"


# --------------------------------------------------------------- the weekday
#
# Observed in use: a run queried 2026-08-21 and reported on it as "Thursday",
# with 2026-08-20 labelled "Wednesday". Both are a day out -- the 20th is a
# Thursday and the 21st a Friday -- and neither is visible as wrong in a
# sentence that gives only the weekday. Date to weekday is a fixed function, so
# the script prints it and the answer quotes it instead of counting it off.


def test_the_weekday_is_computed_not_read_off_the_host_locale():
    """``strftime('%a')`` follows the host's locale; these names must not."""
    assert cs.WEEKDAY_NAMES == ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    assert cs.day_label(date(2026, 8, 19)) == "Wed 2026-08-19"
    assert cs.day_label(date(2026, 8, 20)) == "Thu 2026-08-20"
    assert cs.day_label(date(2026, 8, 21)) == "Fri 2026-08-21"


def test_every_date_in_a_when_cell_carries_its_weekday():
    """Including the far end of a range, which is the one counted off by hand."""
    timed = row(start=datetime(2026, 8, 19, 9, 0, tzinfo=PARIS),
                end=datetime(2026, 8, 19, 10, 0, tzinfo=PARIS))
    assert cs.format_when(timed, PARIS).startswith("Wed 2026-08-19")
    crossing = row(start=datetime(2026, 8, 19, 23, 0, tzinfo=PARIS),
                   end=datetime(2026, 8, 20, 1, 0, tzinfo=PARIS))
    assert cs.format_when(crossing, PARIS) == "Wed 2026-08-19 23:00 - Thu 2026-08-20 01:00"
    spanning = row(start=date(2026, 8, 19), end=date(2026, 8, 22), all_day=True)
    assert cs.format_when(spanning, PARIS) == "Wed 2026-08-19 - Fri 2026-08-21 (all day)"


def test_the_window_names_the_weekday_at_both_ends():
    """The window is the line that says which days the run actually asked about."""
    rendered = cs.render_events(
        REFS[1],
        [],
        datetime(2026, 8, 19, tzinfo=PARIS),
        datetime(2026, 8, 21, tzinfo=PARIS),
        PARIS,
        "expanded by the server",
    )
    assert "Wed 2026-08-19 → Thu 2026-08-20" in rendered


def test_the_json_row_hands_over_the_weekday_rather_than_leaving_it_derived():
    """``--json`` is the path where the answer is written by hand, so it is likeliest there."""
    timed = row(start=datetime(2026, 8, 21, 9, 0, tzinfo=PARIS),
                end=datetime(2026, 8, 21, 10, 0, tzinfo=PARIS))
    assert timed.as_dict(PARIS)["weekday"] == "Fri"
    all_day = row(start=date(2026, 8, 20), end=date(2026, 8, 21), all_day=True)
    assert all_day.as_dict(PARIS)["weekday"] == "Thu"


def test_a_cell_cannot_break_the_row_it_sits_in():
    assert cs.cell("a | b") == "a │ b"
    assert cs.cell("two\nlines") == "two lines"
    assert cs.cell("") == "—"
    assert cs.cell("   ") == "—"


def test_rows_sort_by_start_across_mixed_all_day_and_timed():
    rows = cs.event_rows([], PARIS)
    assert rows == []
    unsorted = [
        row(summary="Late", start=datetime(2026, 9, 1, 18, 0, tzinfo=PARIS)),
        row(summary="Allday", start=date(2026, 9, 1), all_day=True),
        row(summary="Early", start=datetime(2026, 9, 1, 8, 0, tzinfo=PARIS)),
    ]
    ordered = sorted(unsorted, key=lambda item: item.sort_key(PARIS))
    assert [item.summary for item in ordered] == ["Allday", "Early", "Late"]


# ------------------------------------------------------------------ Block Kit


def test_a_card_text_field_is_an_object_and_never_a_bare_string():
    """A bare string is rejected as invalid_blocks and takes the whole message."""
    rendered = cs.render_calendars(REFS, "https://example.org")
    cards = blocks_of(rendered)[1]["elements"]
    for card in cards:
        for field in ("title", "subtitle", "body", "subtext"):
            if field in card:
                assert isinstance(card[field], dict)
                assert card[field]["type"] in ("mrkdwn", "plain_text")
                assert isinstance(card[field]["text"], str)


def test_card_text_fields_stay_inside_their_documented_caps():
    long = "x" * 500
    assert len(cs.mrkdwn(long, cs.CARD_TITLE_CHARACTERS)["text"]) == cs.CARD_TITLE_CHARACTERS
    assert len(cs.mrkdwn(long, cs.CARD_BODY_CHARACTERS)["text"]) == cs.CARD_BODY_CHARACTERS
    assert cs.fit(long, 10).endswith("…")
    assert cs.fit("short", 10) == "short"


def test_the_calendar_icon_is_a_documented_slack_icon_object():
    card = blocks_of(cs.render_calendars(REFS, "https://example.org"))[1]["elements"][0]
    assert card["slack_icon"] == {"type": "icon", "name": "calendar"}
    assert "icon" not in card, "icon and slack_icon render in the same place"


def test_a_context_block_spends_one_element_however_many_facts_it_states():
    """Separators count against the ten-element ceiling; composing them costs one."""
    block = cs.context_block("a · b · c · d · e · f · g")
    assert len(block["elements"]) == 1
    assert block["elements"][0]["type"] == "mrkdwn"


def test_the_carousel_gives_way_to_a_table_past_ten_calendars():
    many = [
        cs.CalendarRef(f"c{index}", f"Calendar {index}", f"https://example.org/p/c{index}/")
        for index in range(cs.CAROUSEL_MAX_CARDS + 1)
    ]
    rendered = cs.render_calendars(many, "https://example.org")
    assert "carousel" not in rendered
    assert "| Calendar | id | URL |" in rendered

    exactly_ten = many[: cs.CAROUSEL_MAX_CARDS]
    rendered = cs.render_calendars(exactly_ten, "https://example.org")
    carousel = blocks_of(rendered)[1]
    assert carousel["type"] == "carousel"
    assert len(carousel["elements"]) == cs.CAROUSEL_MAX_CARDS


def test_an_empty_range_still_says_what_was_looked_for():
    """"You are free" and "the question was wrong" must not read the same."""
    rendered = cs.render_events(
        REFS[1],
        [],
        datetime(2026, 9, 1, tzinfo=PARIS),
        datetime(2026, 9, 2, tzinfo=PARIS),
        PARIS,
        "expanded by the server",
    )
    blocks = blocks_of(rendered)
    assert len(blocks) == 1 and blocks[0]["type"] == "context"
    text = blocks[0]["elements"][0]["text"]
    assert "0 events" in text and "2026-09-01" in text and "Europe/Paris" in text
    assert "| When |" not in rendered


def test_the_event_range_renders_a_context_line_and_a_markdown_table():
    rows = [row(uid="a", summary="One"), row(uid="b", summary="Two", location="Room B")]
    rendered = cs.render_events(
        REFS[1],
        rows,
        datetime(2026, 9, 1, tzinfo=PARIS),
        datetime(2026, 9, 2, tzinfo=PARIS),
        PARIS,
        "expanded by the server",
    )
    blocks = blocks_of(rendered)
    assert [block["type"] for block in blocks] == ["context"]
    assert "| When | Summary | Where | UID |" in rendered
    assert rendered.count("\n| ") >= 3
    assert "`a`" in rendered and "`b`" in rendered


def test_the_window_is_shown_as_the_last_day_it_includes():
    rendered = cs.render_events(
        REFS[1],
        [],
        datetime(2026, 9, 1, tzinfo=PARIS),
        datetime(2026, 9, 2, tzinfo=PARIS),
        PARIS,
        "expanded by the server",
    )
    assert "Tue 2026-09-01 → Tue 2026-09-01" in rendered


def test_the_count_is_what_the_server_matched_not_what_survived_the_limit():
    rows = [row(uid=f"u{index}") for index in range(3)]
    rendered = cs.render_events(
        REFS[1],
        rows,
        datetime(2026, 9, 1, tzinfo=PARIS),
        datetime(2026, 9, 2, tzinfo=PARIS),
        PARIS,
        "expanded by the server",
        total=40,
    )
    assert "40 events" in rendered
    assert "37 not shown" in rendered


def test_a_table_too_long_for_one_message_drops_rows_and_says_how_many():
    rows = [row(uid=f"uid-{index:04d}", summary=f"Meeting {index}") for index in range(400)]
    table, dropped = cs.event_table(rows, PARIS)
    assert dropped > 0
    assert len(table) <= cs.TABLE_CHARACTER_BUDGET
    rendered = cs.render_events(
        REFS[1],
        rows,
        datetime(2026, 9, 1, tzinfo=PARIS),
        datetime(2026, 9, 30, tzinfo=PARIS),
        PARIS,
        "expanded by the server",
    )
    assert "not shown" in rendered


def test_a_recurring_occurrence_is_marked_in_the_table():
    table, _ = cs.event_table([row(summary="Standup", recurring=True)], PARIS)
    assert "Standup ↺" in table


ALICE = cs.Attendee(email="alice@example.org", name="Alice Liddell")
BOB = cs.Attendee(email="bob@example.org")


def test_attendees_are_absent_from_the_table_by_default():
    """The column is a squeeze most rows do not need; see SKILL.md."""
    table, _ = cs.event_table([row(attendees=(ALICE, BOB))], PARIS)
    assert "Attendees" not in table
    assert "alice@example.org" not in table


def test_show_attendees_adds_a_fifth_column_with_the_labels():
    table, _ = cs.event_table([row(attendees=(ALICE, BOB))], PARIS, show_attendees=True)
    assert "| When | Summary | Where | UID | Attendees |" in table
    assert "Alice Liddell, bob@example.org" in table


def test_show_attendees_prints_an_em_dash_for_an_event_with_none():
    table, _ = cs.event_table([row()], PARIS, show_attendees=True)
    lines = table.splitlines()
    assert lines[-1].rstrip().endswith("| — |")


def test_an_attendee_cell_is_capped_independent_of_the_row_budget():
    many = tuple(cs.Attendee(email=f"person{i}@example.org") for i in range(30))
    table, _ = cs.event_table([row(attendees=many)], PARIS, show_attendees=True)
    line = table.splitlines()[-1]
    assert len(line) < cs.TABLE_CHARACTER_BUDGET
    assert "…" in line


def test_render_events_threads_show_attendees_through_to_the_table():
    rendered = cs.render_events(
        REFS[1], [row(attendees=(ALICE,))],
        datetime(2026, 9, 1, tzinfo=PARIS), datetime(2026, 9, 2, tzinfo=PARIS),
        PARIS, "expanded by the server", show_attendees=True,
    )
    assert "Alice Liddell" in rendered
    hidden = cs.render_events(
        REFS[1], [row(attendees=(ALICE,))],
        datetime(2026, 9, 1, tzinfo=PARIS), datetime(2026, 9, 2, tzinfo=PARIS),
        PARIS, "expanded by the server",
    )
    assert "Alice Liddell" not in hidden


def test_the_singleton_card_is_a_card_and_not_a_carousel_of_one():
    rendered = cs.render_event_card(
        REFS[1], row(uid="abc", location="Room B"), PARIS,
        heading="Event created", icon="calendar",
    )
    blocks = blocks_of(rendered)
    assert [block["type"] for block in blocks] == ["context", "card"]
    card = blocks[1]
    assert card["title"]["text"] == "Something"
    assert card["subtitle"]["text"] == "Tue 2026-09-01 09:00-10:00"
    assert card["subtext"]["text"] == "`abc`"
    assert card["slack_icon"] == {"type": "icon", "name": "calendar"}


def test_the_singleton_card_lists_attendees_in_its_body():
    """A single card has no row width to protect -- see render_event_card's docstring."""
    rendered = cs.render_event_card(
        REFS[1], row(uid="abc", attendees=(ALICE, BOB)), PARIS,
        heading="Event created", icon="calendar",
    )
    card = blocks_of(rendered)[1]
    assert "Alice Liddell" in card["body"]["text"]
    assert "bob@example.org" in card["body"]["text"]


def test_the_singleton_card_body_omits_the_attendee_clause_when_there_are_none():
    rendered = cs.render_event_card(
        REFS[1], row(uid="abc"), PARIS, heading="Event created", icon="calendar",
    )
    card = blocks_of(rendered)[1]
    assert "with " not in card["body"]["text"]


def test_every_rendered_message_stays_inside_the_fifty_block_ceiling():
    many = [
        cs.CalendarRef(f"c{index}", f"Calendar {index}", f"https://example.org/p/c{index}/")
        for index in range(cs.CAROUSEL_MAX_CARDS)
    ]
    for rendered in (
        cs.render_calendars(many, "https://example.org"),
        cs.render_event_card(REFS[1], row(), PARIS, heading="Event created", icon="calendar"),
        cs.render_events(
            REFS[1], [row()], datetime(2026, 9, 1, tzinfo=PARIS),
            datetime(2026, 9, 2, tzinfo=PARIS), PARIS, "expanded by the server",
        ),
    ):
        assert len(blocks_of(rendered)) <= 50


def test_every_fence_holds_valid_json_under_a_blockkit_tag():
    rendered = cs.render_calendars(REFS, "https://example.org")
    assert rendered.startswith("```blockkit\n")
    assert rendered.rstrip().endswith("```")
    json.loads(rendered.split("```blockkit\n", 1)[1].rsplit("\n```", 1)[0])


# ------------------------------------------------------- the relay instruction
#
# The script's output is a finished fenced ``blockkit`` block, and the one way
# this skill fails in practice is a model summarising that block into prose
# instead of passing it through -- at which point the rendering never leaves the
# model at all. The word that survives that instinct, measured over repeated
# runs, is "fenced": naming the mechanism makes the output read as an artifact
# to forward rather than a format to produce. These two tests hold that wording
# in the two places a model actually looks -- the description that decides
# whether the skill fires, and the verb section it reads while forming the
# command -- so it cannot drift back out of them.


def _skill_md() -> str:
    return (Path(__file__).resolve().parent.parent / "SKILL.md").read_text()


def _frontmatter_description(text: str) -> str:
    """The ``description:`` folded scalar, joined back into one line."""
    front = text.split("---\n", 2)[1]
    lines = front.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("description:"))
    body = []
    for line in lines[start + 1 :]:
        if line and not line.startswith((" ", "\t")):
            break
        body.append(line.strip())
    return " ".join(part for part in body if part)


def _verb_sections(text: str) -> dict[str, str]:
    """Each ``### `verb` -- ...`` section's body, keyed by the verb it names."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("### "):
            current = line[4:].split("`")[1] if "`" in line else None
            if current:
                sections[current] = []
        elif line.startswith("## "):
            current = None
        elif current:
            sections[current].append(line)
    return {verb: "\n".join(body) for verb, body in sections.items()}


def test_the_description_frontmatter_carries_the_relay_rule():
    """The description is the one part guaranteed to be read: the rule lives there."""
    description = _frontmatter_description(_skill_md()).lower()
    assert "fenced" in description, "'fenced' is the word that makes it pass through"
    assert "blockkit" in description
    assert "exactly as printed" in description


def test_every_verb_section_restates_the_relay_rule():
    """A model forming a command reads the verb section, not the section at the end."""
    sections = _verb_sections(_skill_md())
    assert set(sections) == {"list-calendars", "list-events", "create-event", "delete-event"}
    for verb, body in sections.items():
        lowered = body.lower()
        assert "fenced" in lowered, f"{verb} does not say the output is fenced"
        assert "blockkit" in lowered, f"{verb} does not name the fence's tag"
        assert "exactly as printed" in lowered, f"{verb} does not say to pass it through"


# ------------------------------------------------- asking, rather than listing
#
# Observed in use: asked to find a slot and let the user pick between the
# options, four runs out of four printed a bulleted list of times ending in
# "let me know which slot you would like", and the harness's question tool was
# never called once. Nothing in the skill said to ask, so prose was the path of
# least resistance -- the same shape as the relay failure above, where the
# instruction existed but not in the place it was needed. These tests hold the
# rule in the description, in the section that argues it, and in the verb
# section a model is reading while it forms the query that produces the slots.


def _flat(text: str) -> str:
    """*text* lowercased, with every run of whitespace collapsed to one space.

    A guard test on wording must not depend on where a paragraph happens to
    wrap. Rewrapping a line is not a change to the instruction, and a test that
    broke on it would be deleted rather than fixed -- taking the instruction it
    was holding in place with it.
    """
    return " ".join(text.split()).lower()


def _named_sections(text: str) -> dict[str, str]:
    """Each top-level ``## Heading`` section's body, keyed by its heading."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return {name: "\n".join(body) for name, body in sections.items()}


def test_the_description_frontmatter_carries_the_asking_rule():
    """The description is read before anything else, and prose is the default otherwise."""
    description = _flat(_frontmatter_description(_skill_md()))
    assert "question with options" in description, "the description does not say to ask"
    assert "rather than listing them in prose" in description


def test_the_skill_argues_for_a_question_rather_than_a_bulleted_list():
    section = _flat(_named_sections(_skill_md())["Offering a choice"])
    assert "question with options" in section
    assert "bulleted list" in section, "the shape being replaced has to be named"
    assert "between two and four" in section, "the option budget is the practical limit"


def test_the_free_text_escape_belongs_inside_the_question_not_instead_of_it():
    """'or tell me another time' written as prose gives back the reply the question avoided."""
    section = _flat(_named_sections(_skill_md())["Offering a choice"])
    assert "or tell me another time" in section
    assert "inside" in section and "not instead of it" in section
    assert "inputs" in section, "a typed value is the other kind of question, and is the escape"


def test_the_asking_rule_is_scoped_to_being_asked_to_pick():
    """Not every answer containing a list is a question: a report stays a report."""
    section = _flat(_named_sections(_skill_md())["Offering a choice"])
    assert "not a rule about lists" in section
    assert "what is on wednesday" in section, "the counter-example keeps the rule from spreading"


def test_the_two_traps_in_a_hand_picked_slot_are_written_down():
    """Overlapping candidates are one slot twice, and an empty hour is not an available one."""
    section = _flat(_named_sections(_skill_md())["Offering a choice"])
    assert "16:30-17:30" in section and "17:00-18:00" in section
    assert "overlap" in section
    assert "07:00" in section
    assert "assumption about when this person works" in section


# ------------------------------------------------------- the days an answer names
#
# Observed in use: asked for a slot on Wednesday or Thursday, a run queried
# 2026-08-21 alone -- a Friday -- then reported on 2026-08-20 and 2026-08-21 as
# "Wednesday (Aug 20) and Thursday (Aug 21)", carrying the 20th's events from a
# query fifty minutes earlier, and prefaced all of it with "I've checked your
# Work calendar for Wednesday and Thursday". The data happened to be right. The
# claim to have checked was not, and an answer asserting a check it did not
# perform reads exactly like one that did.


def test_the_description_frontmatter_carries_the_query_every_day_rule():
    description = _flat(_frontmatter_description(_skill_md()))
    assert "query every day the reply names" in description
    assert "in the same turn" in description


def test_the_skill_requires_every_day_named_to_have_been_queried_this_turn():
    section = _flat(_named_sections(_skill_md())["Naming a day"])
    assert "must have been queried in the same turn" in section
    assert "not evidence about the calendar now" in section, "stale results have to be refused"
    assert "false one" in section, "saying it was checked when it was not is the failure"


def test_the_skill_says_two_days_is_one_window_or_two_runs():
    section = _flat(_named_sections(_skill_md())["Naming a day"])
    assert "one run per day" in section
    assert "--from" in section and "--to" in section


def test_the_skill_resolves_a_weekday_to_a_date_before_querying():
    section = _flat(_named_sections(_skill_md())["Naming a day"])
    assert "resolve a weekday name to a date before querying" in section
    assert "never \"wednesday\" on its own" in section, "the date has to be stated alongside"


def test_the_weekday_rule_names_the_relative_forms_the_script_already_accepts():
    """The parser anchors a relative day; counting one by hand is what goes wrong."""
    section = _flat(_named_sections(_skill_md())["Naming a day"])
    for form in ("`today`", "`tomorrow`", "`+7d`", "`-1d`"):
        assert form in section, f"{form} is a form the script accepts and the rule should name"


def test_the_list_events_section_carries_both_day_rules():
    """A model forming the query reads the verb section, not the section at the end."""
    body = _flat(_verb_sections(_skill_md())["list-events"])
    assert "queried in this turn" in body
    assert "resolved to" in body and "date" in body
    assert "naming a day" in body and "offering a choice" in body


def test_the_skill_says_the_script_prints_the_weekday_so_it_is_not_recomputed():
    printed = _flat(_named_sections(_skill_md())["What it prints"])
    assert "every date it prints carries its weekday" in printed
    assert "weekday` field" in printed, "--json carries it too, and that is the riskier path"


def test_the_absent_free_busy_verb_is_a_decision_and_says_where_the_traps_went():
    """No verb returns free slots; the reasoning lives with the rest of the scope."""
    section = _flat(_named_sections(_skill_md())["What it does not do"])
    assert "no verb that returns free slots" in section
    assert "offering a choice" in section


# ------------------------------------------------------- attendees, not invitations
#
# The gap between "recorded on the event" and "the person was told" is exactly
# the kind of thing an operator discovers at the wrong moment, so it has to be
# stated plainly rather than left to be inferred from the absence of a mailer.
# These tests hold the claim in the section that argues it, in the create-event
# section a model reads while forming the write, and in what-it-does-not-do.


def test_the_attendees_section_says_scheduling_was_checked_not_assumed():
    section = _flat(_named_sections(_skill_md())["Attendees are not invitations"])
    assert "checked directly against the server" in section
    assert "calendar-auto-schedule" in section
    assert "schedule-inbox-url" in section and "schedule-outbox-url" in section
    assert "404" in section
    assert "scheduling is not implemented" in section


def test_the_attendees_section_forbids_claiming_notification_happened():
    section = _flat(_named_sections(_skill_md())["Attendees are not invitations"])
    assert "do not describe an attendee added this way as having been invited" in section
    assert "no mail is sent" in section


def test_the_create_event_section_points_at_the_invitation_caveat():
    """A model forming the write reads this section, not the one at the end."""
    body = _flat(_verb_sections(_skill_md())["create-event"])
    assert "recording an attendee is not sending an invitation" in body
    assert "attendees are not invitations" in body


def test_the_create_event_section_documents_the_attendee_value_forms():
    body = _flat(_verb_sections(_skill_md())["create-event"])
    assert "mailto:" in body
    assert "display name" in body or "cn" in body
    assert "refused rather than written" in body


def test_what_it_does_not_do_no_longer_lists_attendees_as_out_of_scope():
    """Attendees moved from unsupported to supported-but-not-delivered."""
    section = _flat(_named_sections(_skill_md())["What it does not do"])
    assert "attendees are not invitations" in section
    assert "invitations, attendees, free/busy" not in section


# ------------------------------------------------------------- self-contained


def test_the_script_names_no_host_no_operator_and_no_server():
    """Someone reading this skill should not be able to tell where it came from."""
    script = (Path(__file__).resolve().parent.parent / "scripts" / "caldav_skill.py").read_text()
    skill_md = (Path(__file__).resolve().parent.parent / "SKILL.md").read_text()
    for text in (script, skill_md):
        lowered = text.lower()
        for forbidden in (
            "/home/",
            "127.0.0.1",
            "localhost",
            "radicale",
            "jiuwenswarm",
            "5232",
            ".jiuwenswarm",
            "/opt/",
        ):
            assert forbidden not in lowered, f"{forbidden!r} identifies a deployment"


def test_the_caldav_pin_is_exact_and_declared_in_the_script_itself():
    script = (Path(__file__).resolve().parent.parent / "scripts" / "caldav_skill.py").read_text()
    header = script.split("# ///")[1]
    assert '"caldav==2.1.0"' in header
    assert '"requests"' in header, "caldav 2.1.0 imports it without declaring it"
    assert '"vobject"' in header
    assert '"icalendar>=6,<7"' in header


def test_the_library_is_not_imported_at_module_scope():
    """The verb surface has to stay testable in an environment with nothing installed."""
    script = (Path(__file__).resolve().parent.parent / "scripts" / "caldav_skill.py").read_text()
    body = script.split('"""', 2)[2]
    for line in body.splitlines():
        if line.startswith("import ") or line.startswith("from "):
            assert "caldav" not in line and "icalendar" not in line, line
