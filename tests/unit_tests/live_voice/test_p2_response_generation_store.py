# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from jiuwenswarm.common.schema.live_voice_contract_v2 import MAX_SAFE_INTEGER
from jiuwenswarm.server.live_voice.formal_task_models import FormalTaskViolation
from jiuwenswarm.server.live_voice.p2_response_generation_store import (
    SqliteP2ResponseGenerationOwner,
)


def test_generation_survives_owner_and_process_registry_restart(tmp_path: Path) -> None:
    database = tmp_path / "response-generations.sqlite3"
    first = SqliteP2ResponseGenerationOwner(database)

    assert first.next_generation("session-a", "interaction-a", -1) == 0
    assert first.next_generation("session-a", "interaction-a", 0) == 1

    restarted = SqliteP2ResponseGenerationOwner(database)
    assert restarted.next_generation("session-a", "interaction-a", -1) == 2
    raw = database.read_bytes()
    assert b"session-a" not in raw
    assert b"interaction-a" not in raw


def test_generation_allocation_is_atomic_across_concurrent_owners(
    tmp_path: Path,
) -> None:
    database = tmp_path / "response-generations.sqlite3"

    def allocate(_: int) -> int:
        owner = SqliteP2ResponseGenerationOwner(database)
        return owner.next_generation("session-concurrent", "interaction-concurrent", -1)

    with ThreadPoolExecutor(max_workers=16) as pool:
        generations = sorted(pool.map(allocate, range(32)))

    assert generations == list(range(32))


def test_exact_capacity_eviction_retains_a_conservative_durable_fence(
    tmp_path: Path,
) -> None:
    database = tmp_path / "response-generations.sqlite3"
    owner = SqliteP2ResponseGenerationOwner(database)
    for index in range(129):
        assert (
            owner.next_generation("session-capacity", f"interaction-{index}", -1) >= 0
        )

    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT count(*) FROM exact_high_water").fetchone()[0]
            == 128
        )
        assert (
            connection.execute("SELECT count(*) FROM fence_high_water").fetchone()[0]
            <= 4
        )

    restarted = SqliteP2ResponseGenerationOwner(database)
    assert restarted.next_generation("session-capacity", "interaction-0", -1) >= 1


def test_generation_exhaustion_and_invalid_input_fail_before_state_mutation(
    tmp_path: Path,
) -> None:
    database = tmp_path / "response-generations.sqlite3"
    owner = SqliteP2ResponseGenerationOwner(database)
    with sqlite3.connect(database) as connection:
        before = connection.execute(
            "SELECT touch_sequence FROM sequence_owner"
        ).fetchone()[0]

    with pytest.raises(FormalTaskViolation) as exhausted:
        owner.next_generation("session-a", "interaction-a", MAX_SAFE_INTEGER)
    assert exhausted.value.reason == "RESPONSE_GENERATION_EXHAUSTED"
    with pytest.raises(FormalTaskViolation) as invalid:
        owner.next_generation("session-a", "interaction-a", True)
    assert invalid.value.reason == "P2_RESPONSE_GENERATION_OWNER_INVALID"

    with sqlite3.connect(database) as connection:
        after = connection.execute(
            "SELECT touch_sequence FROM sequence_owner"
        ).fetchone()[0]
        assert after == before
        assert (
            connection.execute("SELECT count(*) FROM exact_high_water").fetchone()[0]
            == 0
        )


def test_restart_rejects_foreign_schema_and_corrupt_owner_state(
    tmp_path: Path,
) -> None:
    database = tmp_path / "response-generations.sqlite3"
    SqliteP2ResponseGenerationOwner(database)
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE foreign_state(value TEXT)")
    with pytest.raises(FormalTaskViolation) as foreign:
        SqliteP2ResponseGenerationOwner(database)
    assert foreign.value.reason == "P2_RESPONSE_GENERATION_OWNER_UNAVAILABLE"

    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE foreign_state")
        connection.execute(
            "UPDATE sequence_owner SET touch_sequence=-1 WHERE singleton=1"
        )
    with pytest.raises(FormalTaskViolation) as corrupt:
        SqliteP2ResponseGenerationOwner(database)
    assert corrupt.value.reason == "P2_RESPONSE_GENERATION_OWNER_UNAVAILABLE"

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE sequence_owner SET touch_sequence='not-an-integer' "
            "WHERE singleton=1"
        )
    with pytest.raises(FormalTaskViolation) as malformed:
        SqliteP2ResponseGenerationOwner(database)
    assert malformed.value.reason == "P2_RESPONSE_GENERATION_OWNER_UNAVAILABLE"


def test_live_owner_rejects_post_initialize_corruption_before_any_write(
    tmp_path: Path,
) -> None:
    database = tmp_path / "response-generations.sqlite3"
    owner = SqliteP2ResponseGenerationOwner(database)
    assert owner.next_generation("session-live", "interaction-live", -1) == 0

    def snapshot() -> tuple[tuple[tuple[object, ...], ...], ...]:
        with sqlite3.connect(database) as connection:
            return tuple(
                tuple(connection.execute(f"SELECT * FROM {table}").fetchall())
                for table in (
                    "metadata",
                    "exact_high_water",
                    "fence_high_water",
                    "sequence_owner",
                )
            )

    def rejected_without_write() -> None:
        before = snapshot()
        with pytest.raises(FormalTaskViolation) as rejected:
            owner.next_generation("session-live", "interaction-live", -1)
        assert rejected.value.reason == "P2_RESPONSE_GENERATION_OWNER_UNAVAILABLE"
        assert snapshot() == before

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE exact_high_water SET generation=-1")
    rejected_without_write()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE exact_high_water SET generation=0")

    digest = owner._digest("session-live", "interaction-live")
    bucket = owner._indices(digest)[0]
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO fence_high_water VALUES(0, ?, 0)",
            (bucket,),
        )
    rejected_without_write()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM fence_high_water WHERE row_index=0 AND bucket_index=?",
            (bucket,),
        )

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE sequence_owner SET touch_sequence='invalid'")
    rejected_without_write()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE sequence_owner SET touch_sequence=1")

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE sequence_owner SET touch_sequence=?",
            ((1 << 63) - 1,),
        )
    rejected_without_write()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE sequence_owner SET touch_sequence=1")

    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER foreign_trigger AFTER UPDATE ON exact_high_water "
            "BEGIN SELECT 1; END"
        )
    rejected_without_write()


def test_eviction_rejects_a_corrupt_destination_fence_before_any_write(
    tmp_path: Path,
) -> None:
    database = tmp_path / "response-generations.sqlite3"
    owner = SqliteP2ResponseGenerationOwner(database)
    for index in range(128):
        assert (
            owner.next_generation("session-eviction", f"interaction-{index}", -1) == 0
        )

    evicted_digest = owner._digest("session-eviction", "interaction-0")
    incoming_digest = owner._digest("session-eviction", "interaction-incoming")
    destinations = list(enumerate(owner._indices(evicted_digest)))
    incoming = set(enumerate(owner._indices(incoming_digest)))
    row_index, bucket_index = next(
        item for item in destinations if item not in incoming
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO fence_high_water VALUES(?, ?, 0)",
            (row_index, bucket_index),
        )
        before_sequence = connection.execute(
            "SELECT touch_sequence FROM sequence_owner"
        ).fetchone()[0]

    with pytest.raises(FormalTaskViolation) as rejected:
        owner.next_generation(
            "session-eviction",
            "interaction-incoming",
            -1,
        )
    assert rejected.value.reason == "P2_RESPONSE_GENERATION_OWNER_UNAVAILABLE"
    with sqlite3.connect(database) as connection:
        assert (
            connection.execute("SELECT touch_sequence FROM sequence_owner").fetchone()[
                0
            ]
            == before_sequence
        )
        assert (
            connection.execute("SELECT count(*) FROM exact_high_water").fetchone()[0]
            == 128
        )
        assert (
            connection.execute(
                "SELECT encoded_generation FROM fence_high_water "
                "WHERE row_index=? AND bucket_index=?",
                (row_index, bucket_index),
            ).fetchone()[0]
            == 0
        )
