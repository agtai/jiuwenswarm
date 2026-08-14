# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Durable bounded owner for formal P2 response generations."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from jiuwenswarm.common.schema.live_voice_contract_v2 import (
    ErrorCode,
    MAX_SAFE_INTEGER,
)

from .formal_task_models import FormalTaskViolation

_SCHEMA_VERSION = "1"
_EXACT_CAPACITY = 128
_FENCE_ROWS = 4
_FENCE_BUCKETS = 1 << 15
_SQLITE_INTEGER_MAX = (1 << 63) - 1
_TABLE_SCHEMA = {
    "metadata": (("key", "value"), ("TEXT", "TEXT"), ("key",)),
    "exact_high_water": (
        ("key_digest", "generation", "touch_sequence"),
        ("TEXT", "INTEGER", "INTEGER"),
        ("key_digest",),
    ),
    "fence_high_water": (
        ("row_index", "bucket_index", "encoded_generation"),
        ("INTEGER", "INTEGER", "INTEGER"),
        ("row_index", "bucket_index"),
    ),
    "sequence_owner": (
        ("singleton", "touch_sequence"),
        ("INTEGER", "INTEGER"),
        ("singleton",),
    ),
}


class SqliteP2ResponseGenerationOwner:
    """Allocate monotonic generations without retaining raw product IDs.

    A small exact LRU covers active interactions.  Evicted high-water marks are
    folded into four fixed hash sketches, so storage stays bounded and hash
    collisions can only advance a generation, never roll it back.
    """

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._require_regular_database_path()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _require_regular_database_path(self) -> None:
        if self.database_path.is_symlink() or (
            self.database_path.exists() and not self.database_path.is_file()
        ):
            raise self._violation(
                "response generation database path is not a regular file"
            )

    @staticmethod
    def _violation(message: str) -> FormalTaskViolation:
        return FormalTaskViolation(
            "P2_RESPONSE_GENERATION_OWNER_UNAVAILABLE",
            message,
            ErrorCode.UNAVAILABLE,
        )

    def _connect(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            self._require_regular_database_path()
            connection = sqlite3.connect(
                self.database_path,
                timeout=10,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 10000")
            return connection
        except sqlite3.Error as exc:
            if connection is not None:
                connection.close()
            raise self._violation(
                "response generation database is unavailable"
            ) from exc

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("BEGIN EXCLUSIVE")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES('schema_version', ?)",
                    (_SCHEMA_VERSION,),
                )
            elif row["value"] != _SCHEMA_VERSION:
                raise self._violation("response generation schema is unsupported")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS exact_high_water "
                "(key_digest TEXT PRIMARY KEY, generation INTEGER NOT NULL, "
                "touch_sequence INTEGER NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS fence_high_water "
                "(row_index INTEGER NOT NULL, bucket_index INTEGER NOT NULL, "
                "encoded_generation INTEGER NOT NULL, "
                "PRIMARY KEY(row_index, bucket_index))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS sequence_owner "
                "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                "touch_sequence INTEGER NOT NULL)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO sequence_owner(singleton, touch_sequence) "
                "VALUES(1, 0)"
            )
            self._verify_database(connection)
            connection.commit()
        except FormalTaskViolation:
            connection.rollback()
            raise
        except (sqlite3.Error, ValueError, TypeError, OverflowError) as exc:
            connection.rollback()
            raise self._violation("response generation schema is unavailable") from exc
        finally:
            connection.close()

    @classmethod
    def _verify_database(cls, connection: sqlite3.Connection) -> None:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise cls._violation("response generation database is corrupt")
        cls._verify_schema(connection)
        sequence = cls._read_sequence(connection)
        cls._verify_exact_rows(connection, sequence)
        invalid_fence = connection.execute(
            "SELECT 1 FROM fence_high_water WHERE "
            "row_index < 0 OR row_index >= ? OR bucket_index < 0 OR "
            "bucket_index >= ? OR encoded_generation < 1 OR "
            "encoded_generation > ? LIMIT 1",
            (_FENCE_ROWS, _FENCE_BUCKETS, MAX_SAFE_INTEGER + 1),
        ).fetchone()
        if invalid_fence is not None:
            raise cls._violation("response generation fence owner is corrupt")

    @classmethod
    def _verify_schema(cls, connection: sqlite3.Connection) -> None:
        tables = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if tables != set(_TABLE_SCHEMA):
            raise cls._violation("response generation schema is unsupported")
        if (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='trigger' LIMIT 1"
            ).fetchone()
            is not None
        ):
            raise cls._violation("response generation schema is unsupported")
        for table, (
            expected_columns,
            expected_types,
            expected_primary_key,
        ) in _TABLE_SCHEMA.items():
            columns = connection.execute(f"PRAGMA table_info({table})").fetchall()
            if tuple(str(row["name"]) for row in columns) != expected_columns:
                raise cls._violation("response generation schema is unsupported")
            if tuple(str(row["type"]).upper() for row in columns) != expected_types:
                raise cls._violation("response generation schema is unsupported")
            primary_key = tuple(
                str(row["name"])
                for row in sorted(columns, key=lambda item: int(item["pk"]))
                if int(row["pk"])
            )
            if primary_key != expected_primary_key:
                raise cls._violation("response generation schema is unsupported")
        metadata = connection.execute(
            "SELECT key, value FROM metadata ORDER BY key"
        ).fetchall()
        if len(metadata) != 1 or tuple(metadata[0]) != (
            "schema_version",
            _SCHEMA_VERSION,
        ):
            raise cls._violation("response generation schema is unsupported")

    @classmethod
    def _read_sequence(cls, connection: sqlite3.Connection) -> int:
        sequence = connection.execute(
            "SELECT singleton, touch_sequence FROM sequence_owner"
        ).fetchall()
        if (
            len(sequence) != 1
            or type(sequence[0]["singleton"]) is not int
            or sequence[0]["singleton"] != 1
            or type(sequence[0]["touch_sequence"]) is not int
            or sequence[0]["touch_sequence"] < 0
            or sequence[0]["touch_sequence"] >= _SQLITE_INTEGER_MAX
        ):
            raise cls._violation("response generation sequence is unavailable")
        return sequence[0]["touch_sequence"]

    @classmethod
    def _verify_exact_rows(
        cls,
        connection: sqlite3.Connection,
        touch_sequence: int,
    ) -> dict[str, int]:
        rows = connection.execute(
            "SELECT key_digest, generation, touch_sequence FROM exact_high_water"
        ).fetchall()
        if len(rows) > _EXACT_CAPACITY:
            raise cls._violation("response generation exact owner is corrupt")
        exact: dict[str, int] = {}
        for row in rows:
            key_digest = row["key_digest"]
            generation = row["generation"]
            touched = row["touch_sequence"]
            if (
                type(key_digest) is not str
                or len(key_digest) != 64
                or any(character not in "0123456789abcdef" for character in key_digest)
                or type(generation) is not int
                or generation < 0
                or generation > MAX_SAFE_INTEGER
                or type(touched) is not int
                or touched < 1
                or touched > touch_sequence
            ):
                raise cls._violation("response generation exact owner is corrupt")
            exact[key_digest] = generation
        return exact

    @classmethod
    def _verify_allocation_state(
        cls,
        connection: sqlite3.Connection,
        digest: bytes,
        key_digest: str,
    ) -> tuple[int, int | None, tuple[int, int, int, int]]:
        cls._verify_schema(connection)
        touch_sequence = cls._read_sequence(connection)
        exact = cls._verify_exact_rows(connection, touch_sequence)
        encoded_fence: list[int] = []
        for row_index, bucket_index in enumerate(cls._indices(digest)):
            rows = connection.execute(
                "SELECT encoded_generation FROM fence_high_water "
                "WHERE row_index=? AND bucket_index=?",
                (row_index, bucket_index),
            ).fetchall()
            if len(rows) > 1:
                raise cls._violation("response generation fence owner is corrupt")
            if not rows:
                encoded_fence.append(0)
                continue
            encoded = rows[0]["encoded_generation"]
            if (
                type(encoded) is not int
                or encoded < 1
                or encoded > MAX_SAFE_INTEGER + 1
            ):
                raise cls._violation("response generation fence owner is corrupt")
            encoded_fence.append(encoded)
        return (
            touch_sequence,
            exact.get(key_digest),
            tuple(encoded_fence),  # type: ignore[return-value]
        )

    @staticmethod
    def _digest(session_id: str, interaction_id: str) -> bytes:
        return hashlib.sha256(
            f"{session_id}\0{interaction_id}".encode("utf-8")
        ).digest()

    @staticmethod
    def _indices(digest: bytes) -> tuple[int, int, int, int]:
        return tuple(
            int.from_bytes(digest[offset : offset + 4], "big") % _FENCE_BUCKETS
            for offset in (0, 4, 8, 12)
        )  # type: ignore[return-value]

    @staticmethod
    def _validate_input(
        session_id: str,
        interaction_id: str,
        local_prior: int,
    ) -> None:
        if (
            type(session_id) is not str
            or not session_id.strip()
            or len(session_id) > 256
            or type(interaction_id) is not str
            or not interaction_id.strip()
            or len(interaction_id) > 256
            or type(local_prior) is not int
            or local_prior < -1
            or local_prior > MAX_SAFE_INTEGER
        ):
            raise FormalTaskViolation(
                "P2_RESPONSE_GENERATION_OWNER_INVALID",
                "response generation owner input is invalid",
                ErrorCode.INVALID_ARGUMENT,
            )

    @staticmethod
    def _record_fence(
        connection: sqlite3.Connection,
        digest: bytes,
        generation: int,
    ) -> None:
        encoded = generation + 1
        for row_index, bucket_index in enumerate(
            SqliteP2ResponseGenerationOwner._indices(digest)
        ):
            existing = connection.execute(
                "SELECT encoded_generation FROM fence_high_water "
                "WHERE row_index=? AND bucket_index=?",
                (row_index, bucket_index),
            ).fetchone()
            if existing is not None and (
                type(existing["encoded_generation"]) is not int
                or existing["encoded_generation"] < 1
                or existing["encoded_generation"] > MAX_SAFE_INTEGER + 1
            ):
                raise SqliteP2ResponseGenerationOwner._violation(
                    "response generation fence owner is corrupt"
                )
            connection.execute(
                """INSERT INTO fence_high_water(
                       row_index, bucket_index, encoded_generation)
                   VALUES(?, ?, ?)
                   ON CONFLICT(row_index, bucket_index) DO UPDATE SET
                       encoded_generation=max(encoded_generation, excluded.encoded_generation)
                """,
                (row_index, bucket_index, encoded),
            )

    def next_generation(
        self,
        session_id: str,
        interaction_id: str,
        local_prior: int,
    ) -> int:
        self._validate_input(session_id, interaction_id, local_prior)
        digest = self._digest(session_id, interaction_id)
        key_digest = digest.hex()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            current_touch, exact_generation, encoded_fence = (
                self._verify_allocation_state(connection, digest, key_digest)
            )
            high_water = max(
                local_prior,
                -1 if exact_generation is None else exact_generation,
                min(encoded_fence) - 1,
            )
            if high_water >= MAX_SAFE_INTEGER:
                raise FormalTaskViolation(
                    "RESPONSE_GENERATION_EXHAUSTED",
                    "product response generation is exhausted",
                    ErrorCode.UNAVAILABLE,
                )
            generation = high_water + 1
            touch_sequence = current_touch + 1
            connection.execute(
                "UPDATE sequence_owner SET touch_sequence=? WHERE singleton=1",
                (touch_sequence,),
            )
            if exact_generation is None:
                count = len(
                    connection.execute(
                        "SELECT key_digest FROM exact_high_water"
                    ).fetchall()
                )
                if count >= _EXACT_CAPACITY:
                    evicted = connection.execute(
                        "SELECT key_digest, generation FROM exact_high_water "
                        "ORDER BY touch_sequence, key_digest LIMIT 1"
                    ).fetchone()
                    if evicted is None:
                        raise self._violation(
                            "response generation eviction is unavailable"
                        )
                    self._record_fence(
                        connection,
                        bytes.fromhex(str(evicted["key_digest"])),
                        int(evicted["generation"]),
                    )
                    connection.execute(
                        "DELETE FROM exact_high_water WHERE key_digest=?",
                        (evicted["key_digest"],),
                    )
                connection.execute(
                    "INSERT INTO exact_high_water(key_digest, generation, touch_sequence) "
                    "VALUES(?, ?, ?)",
                    (key_digest, generation, touch_sequence),
                )
            else:
                connection.execute(
                    "UPDATE exact_high_water SET generation=?, touch_sequence=? "
                    "WHERE key_digest=?",
                    (generation, touch_sequence, key_digest),
                )
            connection.commit()
            return generation
        except FormalTaskViolation:
            connection.rollback()
            raise
        except (sqlite3.Error, ValueError, TypeError) as exc:
            connection.rollback()
            raise self._violation(
                "response generation allocation is unavailable"
            ) from exc
        finally:
            connection.close()


__all__ = ["SqliteP2ResponseGenerationOwner"]
