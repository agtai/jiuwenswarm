from __future__ import annotations

import sqlite3
import types

import pytest

from openjiuwen.core.memory.lite.manager import FTS_TABLE, META_KEY, MemoryIndexManager

from jiuwenswarm.server.runtime.memory.fts_trigram_patch import apply_fts_trigram_patch

TRIGRAM_DDL = f"""
    CREATE VIRTUAL TABLE {FTS_TABLE} USING fts5(
        id UNINDEXED, path UNINDEXED, source UNINDEXED, text,
        content='', contentless_delete=1, tokenize='trigram'
    )
"""
LEGACY_DDL = f"""
    CREATE VIRTUAL TABLE {FTS_TABLE} USING fts5(
        id UNINDEXED, path UNINDEXED, source UNINDEXED, text,
        content='', contentless_delete=1
    )
"""


def _manager(ddl: str | None, *, chunks: int = 0, fts_rows: int = 0, meta: str | None = None):
    """A stand-in carrying only what the two patched predicates read."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE chunks (id TEXT, path TEXT, text TEXT)")
    db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
    if ddl:
        db.execute(ddl)
    for i in range(chunks):
        db.execute("INSERT INTO chunks VALUES (?,?,?)", (f"c{i}", "p.md", "text"))
    for i in range(fts_rows):
        db.execute(
            f"INSERT INTO {FTS_TABLE} (rowid,id,path,source,text) VALUES (?,?,?,?,?)",
            (i + 1, f"c{i}", "p.md", "memory", "text"),
        )
    if meta is not None:
        db.execute("INSERT INTO meta VALUES (?,?)", (META_KEY, meta))
    m = types.SimpleNamespace(db=db, _fts_migrated=False, db_path=":memory:")
    m._fts_table_is_legacy = types.MethodType(MemoryIndexManager._fts_table_is_legacy, m)
    m._needs_fts_migration_reindex = types.MethodType(
        MemoryIndexManager._needs_fts_migration_reindex, m
    )
    return m


def test_the_upstream_check_cannot_see_a_quoted_tokenizer():
    """Documents the defect itself, independently of whether the patch is loaded.

    _ensure_schema writes tokenize='trigram' and SQLite stores the CREATE verbatim,
    so the quotes are in the stored text. The upstream predicate looks for the
    unquoted spelling, so the substring never matches and the table the manager
    just created in trigram mode is dropped again on every startup.

    Asserted on the stored DDL rather than through the (possibly already patched)
    method, so this test does not depend on import or execution order.
    """
    db = sqlite3.connect(":memory:")
    db.execute(TRIGRAM_DDL)
    stored = db.execute(
        "SELECT sql FROM sqlite_master WHERE name = ?", (FTS_TABLE,)
    ).fetchone()[0]

    assert "tokenize='trigram'" in stored          # what the kernel writes
    assert "tokenize=trigram" not in stored.lower()  # what the kernel looks for


def test_a_trigram_table_is_not_legacy_after_patching():
    apply_fts_trigram_patch()
    assert _manager(TRIGRAM_DDL)._fts_table_is_legacy() is False


def test_a_real_legacy_table_is_still_detected():
    """The patch must not disable the migration it is protecting."""
    apply_fts_trigram_patch()
    assert _manager(LEGACY_DDL)._fts_table_is_legacy() is True


def test_a_missing_table_is_not_legacy():
    apply_fts_trigram_patch()
    assert _manager(None)._fts_table_is_legacy() is False


def test_an_emptied_index_is_repaired_even_though_meta_says_migrated():
    """The already-damaged case: chunks present, FTS empty, flag already set.

    Preventing the drop does not refill a table that earlier startups emptied,
    and the kernel's own repair is gated on a meta flag that is already true.
    """
    apply_fts_trigram_patch()
    m = _manager(TRIGRAM_DDL, chunks=5, fts_rows=0, meta='{"ftsTrigram": true}')
    assert m._needs_fts_migration_reindex() is True


def test_a_healthy_index_is_not_reindexed_on_every_start():
    apply_fts_trigram_patch()
    m = _manager(TRIGRAM_DDL, chunks=5, fts_rows=5, meta='{"ftsTrigram": true}')
    assert m._needs_fts_migration_reindex() is False


def test_an_empty_corpus_is_not_mistaken_for_damage():
    """No chunks means nothing to index, not a broken index."""
    apply_fts_trigram_patch()
    m = _manager(TRIGRAM_DDL, chunks=0, fts_rows=0, meta='{"ftsTrigram": true}')
    assert m._needs_fts_migration_reindex() is False


def test_applying_twice_is_a_no_op():
    apply_fts_trigram_patch()
    apply_fts_trigram_patch()
    assert _manager(TRIGRAM_DDL)._fts_table_is_legacy() is False
