"""The standing-mandate registry (PR2b, D2/D3/D9).

One entry per (document, agent-connection): the deployment owner's standing
delegation for that document, at one of two levels — ``reply_only`` (answer in
threads, never write the body) or ``apply_scoped`` (bounded direct edits). No
entry means no delegation: adoption alone dispatches nothing (D2).

Storage follows the cursor-store precedent: one JSON file under the workspace
config dir, guarded by a portalocker file lock, so the gateway (dispatch gate)
and the agentserver (pre-write checkpoint, IC-3) read the same truth without a
private channel. Terms are snapshotted into the turn payload at dispatch; the
pre-write checkpoint reads revocation, suspension and expiry live, and holds the
entry to the tier the turn was dispatched under, so a downgrade intercepts an
in-flight write rather than draining. Budget and ``from`` still drain.

Every lifecycle event — grant / modify / suspend / resume / revoke / lapse —
appends one line to the audit journal (D3: one event, one audit line).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import portalocker

logger = logging.getLogger(__name__)

# E1: standing authority decays by default. A watch issued without an explicit
# term expires after this many seconds; "permanent" exists but only as the
# owner's explicit word (expires_at=None passed on purpose), never as the
# silence of a default parameter.
DEFAULT_WATCH_TTL_SECONDS = 30 * 24 * 3600

# The rolling-window loop brake (§16.14). Generous enough that a lively document with
# several live threads never trips it, tight enough that a runaway pointer loop stops
# within one poll cycle rather than exhausting a day's budget first.
DEFAULT_DISPATCH_RATE_MAX = 10
DEFAULT_DISPATCH_RATE_WINDOW_SECONDS = 120.0

# Distinguishes "caller said nothing" (default term) from "caller said None"
# (permanent). A plain None default cannot carry both meanings.
_UNSET: Any = object()

MODES = ("reply_only", "apply_scoped")

_LOCK_TIMEOUT_S = 10.0


def get_watch_registry_path() -> Path:
    from jiuwenswarm.common.utils import get_user_workspace_dir

    return get_user_workspace_dir() / "config" / "clouddoc-watches.json"


@dataclass(frozen=True)
class WatchVerdict:
    """The dispatch gate's answer for one document at one instant."""

    dispatchable: bool
    mode: str | None
    reason: str  # "ok" | "no_watch" | "suspended" | "global_suspended" | "expired" | "over_budget" | "rate_limited"


class WatchRegistry:
    def __init__(
        self,
        path: Path | None = None,
        *,
        now_fn: Callable[[], float] = time.time,
        rate_max: int = DEFAULT_DISPATCH_RATE_MAX,
        rate_window_seconds: float = DEFAULT_DISPATCH_RATE_WINDOW_SECONDS,
    ) -> None:
        self._path = path or get_watch_registry_path()
        self._audit_path = self._path.with_name(self._path.stem + "-audit.jsonl")
        self._now = now_fn
        # The rolling-window loop brake, distinct from the per-watch daily budget: the
        # daily cap is a ceiling, but a tight A@B / B@A pointer loop would burn a whole
        # day's budget in seconds before it trips. This bounds dispatches per document
        # within a short window, so a runaway stops in one cycle rather than a day.
        # A deployment default, not a per-watch grant: it is a safety floor, not a
        # policy the owner tunes per document (§16.14, the liveness brake).
        self._rate_max = int(rate_max)
        self._rate_window = float(rate_window_seconds)

    # ------------------------------------------------------------------ storage

    def _load(self) -> dict:
        if not self._path.is_file():
            return {"version": 1, "global": {"suspended": False}, "watches": {}}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.exception("[clouddoc] watch registry unreadable; treating as empty")
            return {"version": 1, "global": {"suspended": False}, "watches": {}}
        data.setdefault("global", {"suspended": False})
        data.setdefault("watches", {})
        return data

    def _mutate(self, fn: Callable[[dict], Any]) -> Any:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock = self._path.with_suffix(self._path.suffix + ".lock")
        with portalocker.Lock(str(lock), timeout=_LOCK_TIMEOUT_S):
            data = self._load()
            out = fn(data)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self._path)
        return out

    def _audit(self, event: str, doc_id: str | None, **extra: Any) -> None:
        line = {"ts": self._now(), "event": event, "doc_id": doc_id, **extra}
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError:
            logger.exception("[clouddoc] watch audit line lost: %s", line)

    # ---------------------------------------------------------------- lifecycle

    def issue(
        self,
        doc_id: str,
        mode: str,
        *,
        issued_by: str = "manual",
        expires_at: float | None = _UNSET,
        from_list: tuple[str, ...] = (),
        budget: dict | None = None,
    ) -> dict:
        """Grant, or modify by re-issuance (D3: a change terminates the old watch and
        issues a new one; in-flight turns keep the terms snapshotted at dispatch)."""
        if mode not in MODES:
            raise ValueError(f"unknown watch mode: {mode!r}")
        if expires_at is _UNSET:
            expires_at = self._now() + DEFAULT_WATCH_TTL_SECONDS

        def fn(data: dict) -> dict:
            prior = data["watches"].get(doc_id)
            # A revoked entry is a tombstone, not a watch: issuing over it is a fresh
            # grant (the manual act that outranks the owner's earlier termination),
            # not a modification of terms that no longer exist.
            if prior is not None and prior.get("revoked"):
                prior = None
            entry = {
                "mode": mode,
                "issued_at": self._now(),
                "issued_by": issued_by,
                "suspended": False,
                "expires_at": expires_at,
                "from": list(from_list),
                "budget": dict(budget or {}),
                "dispatch_day": "",
                "dispatch_count": 0,
            }
            data["watches"][doc_id] = entry
            self._audit(
                "modify" if prior else "grant", doc_id, mode=mode, issued_by=issued_by
            )
            return entry

        return self._mutate(fn)

    def revoke(self, doc_id: str, *, reason: str | None = None) -> bool:
        """End the delegation and keep the entry, flagged, as its own tombstone.

        Deleting the entry left the journal as the only record of the revocation,
        and the journal's write failure is swallowed (a full disk logs and moves
        on). With no entry and no line, the adoption policy re-issued at the next
        startup. The entry now carries the flag itself; the gate and the pre-write
        checkpoint read it as no watch at all, and only a manual re-issue replaces
        it. Same shape as expiry, for the same reason.
        """

        def fn(data: dict) -> bool:
            entry = data["watches"].get(doc_id)
            if entry is None or entry.get("revoked"):
                return False
            entry["revoked"] = True
            entry["revoked_at"] = self._now()
            self._audit("revoke", doc_id, **({"reason": reason} if reason else {}))
            return True

        return self._mutate(fn)

    def revoke_all(self) -> int:
        """The kill switch (D8): one action, every standing mandate gone. Each
        entry stays as a flagged tombstone, like a single revocation."""

        def fn(data: dict) -> int:
            n = 0
            for doc_id, entry in data["watches"].items():
                if entry.get("revoked"):
                    continue
                entry["revoked"] = True
                entry["revoked_at"] = self._now()
                self._audit("revoke", doc_id, by="kill_switch")
                n += 1
            return n

        return self._mutate(fn)

    def suspend(self, doc_id: str) -> bool:
        return self._set_suspended(doc_id, True)

    def resume(self, doc_id: str) -> bool:
        return self._set_suspended(doc_id, False)

    def _set_suspended(self, doc_id: str, value: bool) -> bool:
        def fn(data: dict) -> bool:
            entry = data["watches"].get(doc_id)
            if entry is None or bool(entry.get("suspended")) == value:
                return False
            entry["suspended"] = value
            self._audit("suspend" if value else "resume", doc_id)
            return True

        return self._mutate(fn)

    def suspend_all(self, *, by: str = "manual") -> None:
        """Global suspend (D3): freeze every watch, keep every registration."""

        def fn(data: dict) -> None:
            if not data["global"].get("suspended"):
                data["global"]["suspended"] = True
                self._audit("suspend_all", None, by=by)

        self._mutate(fn)

    def resume_all(self) -> None:
        def fn(data: dict) -> None:
            if data["global"].get("suspended"):
                data["global"]["suspended"] = False
                self._audit("resume_all", None)

        self._mutate(fn)

    def _expire(self, doc_id: str) -> None:
        """Expiry ends the delegation but keeps the entry as its own tombstone.

        Deleting here is what turned expiry into a no-op: the adoption policy
        re-issues for any document without an entry, so a deleted-on-expiry
        watch came back silently at the next startup. The entry stays, flagged,
        until the owner renews (re-issuance) or revokes; the audit line lands
        exactly once."""

        def fn(data: dict) -> None:
            entry = data["watches"].get(doc_id)
            if entry is not None and not entry.get("expired"):
                entry["expired"] = True
                self._audit("expire", doc_id, mode=entry.get("mode"))

        self._mutate(fn)

    def terminated_by_owner(self, doc_id: str) -> bool:
        """True when the audit journal's last word on this document is revoke.

        The adoption policy consults this before issuing: a revoked watch whose
        entry is gone must not come back as a policy grant at the next startup --
        only a manual grant outranks the owner's own termination."""
        last: str | None = None
        try:
            with self._audit_path.open("r", encoding="utf-8") as f:
                for raw in f:
                    try:
                        line = json.loads(raw)
                    except ValueError:
                        continue
                    if line.get("doc_id") != doc_id:
                        continue
                    ev = line.get("event")
                    if ev in ("grant", "modify", "revoke"):
                        last = ev
        except OSError:
            return False
        return last == "revoke"

    # ------------------------------------------------------------------ queries

    def get(self, doc_id: str) -> dict | None:
        return self._load()["watches"].get(doc_id)

    def snapshot(self) -> dict:
        return self._load()

    def check(self, doc_id: str) -> WatchVerdict:
        """The dispatch gate: one live conjunction, never a cached boolean (D3).

        Remote conditions (document reachable, connection alive) are judged by the
        tick's own API calls succeeding — probing them here would double the quota
        bill for nothing (the admission precedent).
        """
        data = self._load()
        entry = data["watches"].get(doc_id)
        if entry is None or entry.get("revoked"):
            return WatchVerdict(False, None, "no_watch")
        if data["global"].get("suspended"):
            return WatchVerdict(False, entry["mode"], "global_suspended")
        if entry.get("suspended"):
            return WatchVerdict(False, entry["mode"], "suspended")
        exp = entry.get("expires_at")
        if exp is not None and self._now() >= float(exp):
            self._expire(doc_id)
            return WatchVerdict(False, entry["mode"], "expired")
        cap = (entry.get("budget") or {}).get("max_dispatches_per_day")
        if cap is not None and self._today_count(entry) >= int(cap):
            return WatchVerdict(False, entry["mode"], "over_budget")
        # The rolling-window loop brake, checked last: it is the backstop the roster
        # and the self/other-agent filter aim to make unnecessary, not the first line.
        if self._rate_max > 0 and self._recent_count(entry) >= self._rate_max:
            return WatchVerdict(False, entry["mode"], "rate_limited")
        return WatchVerdict(True, entry["mode"], "ok")

    def is_write_live(self, doc_id: str, *, mode: str | None = None) -> bool:
        """The pre-write checkpoint (IC-3): revocation, suspension and expiry
        intercept in-flight writes. With ``mode`` given, the entry must still be
        at that level: a turn dispatched under ``apply_scoped`` whose mandate the
        owner has since changed to ``reply_only`` is intercepted here, at the last
        point before the platform call, rather than draining to completion. The
        budget and the ``from`` list stay snapshotted at dispatch."""
        data = self._load()
        entry = data["watches"].get(doc_id)
        if entry is None or entry.get("revoked"):
            return False
        if entry.get("suspended") or data["global"].get("suspended"):
            return False
        if entry.get("expired"):
            return False
        exp = entry.get("expires_at")
        if exp is not None and self._now() >= float(exp):
            return False
        if mode is not None and entry.get("mode") != mode:
            return False
        return True

    # ------------------------------------------------------------------- budget

    def _day_key(self) -> str:
        t = time.gmtime(self._now())
        return f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"

    def _today_count(self, entry: dict) -> int:
        return entry["dispatch_count"] if entry.get("dispatch_day") == self._day_key() else 0

    def _recent_count(self, entry: dict) -> int:
        """Dispatches on this document within the rolling window ending now."""
        cutoff = self._now() - self._rate_window
        return sum(1 for ts in (entry.get("recent_dispatches") or []) if ts >= cutoff)

    def note_dispatch(self, doc_id: str) -> None:
        """Count a dispatched turn against the day's budget. Persisted, so a restart
        does not refill the budget (a refresh applies to new days, not new processes)."""

        def fn(data: dict) -> None:
            entry = data["watches"].get(doc_id)
            if entry is None:
                return
            day = self._day_key()
            if entry.get("dispatch_day") != day:
                entry["dispatch_day"] = day
                entry["dispatch_count"] = 0
            entry["dispatch_count"] += 1
            # The rolling-window brake's own record: timestamps within the window,
            # pruned on each write so the list cannot grow without bound. Kept separate
            # from the daily counter because the two answer different questions (a day's
            # total vs a burst).
            now = self._now()
            recent = [ts for ts in (entry.get("recent_dispatches") or [])
                      if ts >= now - self._rate_window]
            recent.append(now)
            entry["recent_dispatches"] = recent
            # The daily counter serves the budget; the audit line is what lets
            # the panel show cumulative use against the standing grant (E1's
            # audit view: granted minus used).
            self._audit("dispatch", doc_id, mode=entry.get("mode"))

        self._mutate(fn)

    def note_denied(self, doc_id: str, reason: str) -> None:
        """A refused dispatch, on the record. Frequent denials are the friction
        signal the audit view surfaces (the owner may want to widen or renew);
        without the line the signal does not exist."""
        self._audit("deny", doc_id, reason=reason)

    def usage_summary(self, doc_id: str) -> dict:
        """What the audit journal knows about this document's standing grant:
        issuance history, cumulative dispatches, denials by reason. Receipts --
        the writes themselves -- are the other half and live with the ledger."""
        grants = 0
        dispatches = 0
        last_grant_at: float | None = None
        denials: dict[str, int] = {}
        try:
            with self._audit_path.open("r", encoding="utf-8") as f:
                for raw in f:
                    try:
                        line = json.loads(raw)
                    except ValueError:
                        continue
                    if line.get("doc_id") != doc_id:
                        continue
                    ev = line.get("event")
                    if ev in ("grant", "modify"):
                        grants += 1
                        last_grant_at = line.get("ts")
                    elif ev == "dispatch":
                        dispatches += 1
                    elif ev == "deny":
                        r = str(line.get("reason") or "unknown")
                        denials[r] = denials.get(r, 0) + 1
        except OSError:
            pass
        return {
            "grants": grants,
            "last_grant_at": last_grant_at,
            "dispatches": dispatches,
            "denials": denials,
        }

    # -------------------------------------------------------------------- audit

    def audit_tail(self, limit: int = 100) -> list[dict]:
        if not self._audit_path.is_file():
            return []
        try:
            lines = self._audit_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict] = []
        for ln in lines[-limit:]:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
        return out
