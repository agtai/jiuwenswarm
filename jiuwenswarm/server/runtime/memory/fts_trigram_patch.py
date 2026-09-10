# coding: utf-8
"""Stop openjiuwen emptying the BM25 index on every backend restart.

Why this exists. ``MemoryIndexManager._ensure_schema`` creates ``chunks_fts``
with ``tokenize='trigram'`` -- SQLite stores the CREATE statement verbatim, so
the quotes are part of the stored text. ``_fts_table_is_legacy`` then decides
whether the table predates the trigram migration with::

    return "tokenize=trigram" not in row["sql"].lower()   # unquoted

The substring never matches, so a table the manager itself just created in
trigram mode is reported as legacy and ``DROP``ped -- on every startup, not
once.

That alone would be survivable, because ``initialize()`` force-reindexes after
a migration. But the force-reindex is gated on ``_needs_fts_migration_reindex``,
which returns True only while the ``ftsTrigram`` flag is absent from ``meta``.
The first startup therefore behaves correctly (drop, reindex, record the flag)
and every startup after it drops the table and declines to refill it, because
the flag is now set. ``chunks`` still holds every row -- the incremental sync
skips files whose hash has not changed -- so the damage is invisible: no
exception, no warning, and hybrid search keeps answering from the vector
channel alone. The only trace is an INFO line, "Migrating chunks_fts from
unicode61 to trigram", which reads like a one-time migration notice and in fact
repeats on every boot.

The cost is the whole lexical channel, which is the half that matches exact
identifiers -- acronyms, model names, author names, version numbers.

This patch restores the kernel's intent with two predicate replacements; it
adds no indexing logic of its own and leaves the repair to the kernel's own
``sync(force=True)`` path:

  A. ``_fts_table_is_legacy`` compares against a normalised DDL, so a trigram
     table is recognised whether the tokenizer was written quoted or not, and a
     genuinely legacy (unicode61) table is still detected and still migrated.
     This stops the bleeding but cannot refill a table earlier startups emptied.

  B. ``_needs_fts_migration_reindex`` additionally returns True when the FTS
     table is empty while ``chunks`` is not. That is the signature of an index
     emptied by (A)'s absence, and it makes ``initialize()`` run the same
     ``sync(reason="fts_migration", force=True)`` the kernel already uses after
     a real migration. Re-embedding is not repeated: ``embedding_cache`` is
     keyed by text hash and survives. On a healthy index both counts agree and
     the predicate stays False, so a normal restart pays nothing.

Applied once per process from ``JiuWenSwarmDeepAdapter.__init__``, alongside the
other kernel patches. Remove this module once the upstream check accepts the
quoted form.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["apply_fts_trigram_patch"]

_PATCHED = False


def _tokenizer_is_trigram(create_sql: str) -> bool:
    """Whether a stored fts5 CREATE names the trigram tokenizer.

    Compared with quotes and whitespace stripped, so ``tokenize='trigram'``,
    ``tokenize = "trigram"`` and ``tokenize=trigram`` all read alike. SQLite
    accepts every one of those spellings and stores whichever was written.
    """
    normalised = create_sql.lower().replace("'", "").replace('"', "")
    normalised = "".join(normalised.split())
    return "tokenize=trigram" in normalised


def apply_fts_trigram_patch() -> None:
    """Apply the FTS trigram predicates patch. Idempotent per process."""
    global _PATCHED
    if _PATCHED:
        return

    from openjiuwen.core.memory.lite.manager import FTS_TABLE, MemoryIndexManager

    for name in ("_fts_table_is_legacy", "_needs_fts_migration_reindex"):
        if not hasattr(MemoryIndexManager, name):
            # Fail loudly rather than silently no-op: a rename upstream most
            # likely means the bug was fixed and this module should be deleted,
            # but it could also mean the patch is quietly no longer applied.
            raise AttributeError(
                f"fts_trigram_patch expected MemoryIndexManager.{name}; upstream has "
                "changed. Re-check whether this patch is still needed before removing it."
            )

    _PATCHED = True

    def _fts_table_is_legacy(self: Any) -> bool:
        if not getattr(self, "db", None):
            return False
        try:
            row = self.db.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?",
                (FTS_TABLE,),
            ).fetchone()
        except Exception as exc:
            logger.debug("[fts-trigram] could not introspect %s: %s", FTS_TABLE, exc)
            return False
        if not row or not row["sql"]:
            # A missing table is not legacy; _ensure_schema creates it.
            return False
        return not _tokenizer_is_trigram(row["sql"])

    def _fts_is_empty_while_chunks_exist(self: Any) -> bool:
        """True when the index holds chunks the FTS table does not carry."""
        if not getattr(self, "db", None):
            return False
        try:
            chunks = self.db.execute("SELECT count(*) FROM chunks").fetchone()[0]
            if not chunks:
                return False
            fts = self.db.execute(f"SELECT count(*) FROM {FTS_TABLE}").fetchone()[0]
        except Exception as exc:
            logger.debug("[fts-trigram] could not compare index counts: %s", exc)
            return False
        if fts:
            return False
        logger.warning(
            "[fts-trigram] %s is empty while chunks holds %d row(s); forcing a reindex "
            "to restore the BM25 channel: %s",
            FTS_TABLE,
            chunks,
            getattr(self, "db_path", "?"),
        )
        return True

    original_needs_reindex = MemoryIndexManager._needs_fts_migration_reindex

    def _needs_fts_migration_reindex(self: Any) -> bool:
        if original_needs_reindex(self):
            return True
        return _fts_is_empty_while_chunks_exist(self)

    MemoryIndexManager._fts_table_is_legacy = _fts_table_is_legacy
    MemoryIndexManager._needs_fts_migration_reindex = _needs_fts_migration_reindex
    logger.info("[fts-trigram] patched MemoryIndexManager FTS migration predicates")
