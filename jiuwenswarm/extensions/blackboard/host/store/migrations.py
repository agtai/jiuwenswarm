"""Numbered schema migrations; each milestone appends one."""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[tuple[int, tuple[str, ...]]] = [
    (
        1,
        (
            """CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )""",
            """CREATE TABLE users (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                external_id TEXT UNIQUE,
                is_operator INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                last_seen_at TEXT,
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled'))
            )""",
            """CREATE TABLE workspaces (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                archived_at TEXT
            )""",
            """CREATE TABLE memberships (
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(id),
                role TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'commenter', 'viewer')),
                joined_at TEXT NOT NULL,
                PRIMARY KEY (workspace_id, user_id)
            )""",
            "CREATE INDEX memberships_user ON memberships(user_id)",
            """CREATE TABLE invites (
                code TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('editor', 'commenter', 'viewer')),
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                expires_at TEXT,             -- NULL: never expires
                max_uses INTEGER,            -- NULL: no limit
                uses INTEGER NOT NULL DEFAULT 0,
                revoked_at TEXT
            )""",
            "CREATE INDEX invites_workspace ON invites(workspace_id)",
        ),
    ),
]

LATEST_VERSION = MIGRATIONS[-1][0]


def current_version(conn: sqlite3.Connection) -> int:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0] or 0)


def migrate(conn: sqlite3.Connection) -> int:
    """Apply pending migrations, each in its own transaction. Returns the version reached."""
    version = current_version(conn)
    for number, statements in MIGRATIONS:
        if number <= version:
            continue
        conn.execute("BEGIN IMMEDIATE")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (number,))
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
        version = number
    return version
