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
    (
        2,
        (
            # Documents: the id is also the document service's document name.
            """CREATE TABLE docs (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                is_instructions INTEGER NOT NULL DEFAULT 0,
                is_pinned INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                archived_at TEXT
            )""",
            "CREATE INDEX docs_workspace ON docs(workspace_id)",
            "CREATE UNIQUE INDEX docs_one_instructions ON docs(workspace_id) WHERE is_instructions = 1",
            # Files members upload to a workspace; stored under references/<workspace id>/.
            """CREATE TABLE references_ (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                kind TEXT NOT NULL CHECK (kind IN ('file', 'image')),
                name TEXT NOT NULL,
                mime TEXT NOT NULL,
                size INTEGER NOT NULL,
                stored_path TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                uploaded_by TEXT NOT NULL REFERENCES users(id),
                uploaded_at TEXT NOT NULL,
                removed_at TEXT
            )""",
            "CREATE INDEX references_workspace ON references_(workspace_id)",
        ),
    ),
    (
        3,
        (
            # An agent's mandate: who asked, from where, what for, within which scope, and its state.
            """CREATE TABLE mandates (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                origin TEXT NOT NULL CHECK (origin IN ('comment', 'workspace_chat', 'workspace_session')),
                origin_ref TEXT NOT NULL,
                requester_id TEXT NOT NULL REFERENCES users(id),
                session_id TEXT,
                instruction TEXT NOT NULL,
                scope TEXT NOT NULL,
                permission_mode TEXT NOT NULL DEFAULT 'suggest' CHECK (permission_mode IN ('suggest', 'direct')),
                reply_target TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN (
                    'queued', 'running', 'waiting_for_answer', 'done', 'failed', 'cancelled', 'refused', 'unknown'
                )),
                status_reason TEXT,
                turn_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                last_activity_at TEXT
            )""",
            "CREATE INDEX mandates_workspace ON mandates(workspace_id, created_at)",
            "CREATE INDEX mandates_session ON mandates(session_id, status)",
            # One batch of edits a mandate sent to one document, applied or not.
            """CREATE TABLE receipts (
                id TEXT PRIMARY KEY,
                mandate_id TEXT NOT NULL REFERENCES mandates(id) ON DELETE CASCADE,
                doc_id TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('pending', 'applied', 'aborted')),
                ops TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                before TEXT,
                after TEXT,
                suggestion_ids TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                applied_at TEXT
            )""",
            "CREATE INDEX receipts_mandate ON receipts(mandate_id, created_at)",
            # Which mandate may write a document; one at a time.
            """CREATE TABLE doc_locks (
                doc_id TEXT PRIMARY KEY REFERENCES docs(id) ON DELETE CASCADE,
                mandate_id TEXT NOT NULL REFERENCES mandates(id) ON DELETE CASCADE,
                acquired_at TEXT NOT NULL
            )""",
            "CREATE INDEX doc_locks_mandate ON doc_locks(mandate_id)",
        ),
    ),
    (
        4,
        (
            # Milestone 5: comment threads, the workspace chat, decisions, and the columns a
            # dispatched mandate needs to track its turns.
            # A thread is anchored to a passage of one document; `anchor` is JSON (see host/api/comments.py).
            """CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                doc_id TEXT NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
                anchor TEXT NOT NULL,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                resolved_at TEXT,
                resolved_by TEXT
            )""",
            "CREATE INDEX threads_doc ON threads(doc_id, created_at)",
            # An agent's comment has the requester as its author and kind 'agent'; the host writes 'system' ones.
            """CREATE TABLE comments (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                author_id TEXT NOT NULL,
                author_kind TEXT NOT NULL CHECK (author_kind IN ('person', 'agent', 'system')),
                body TEXT NOT NULL,
                mentions TEXT NOT NULL DEFAULT '[]',
                scope_switch INTEGER NOT NULL DEFAULT 0,
                mandate_id TEXT,
                decision_id TEXT,
                created_at TEXT NOT NULL,
                edited_at TEXT
            )""",
            "CREATE INDEX comments_thread ON comments(thread_id, created_at)",
            """CREATE TABLE chat_messages (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                author_id TEXT NOT NULL,
                author_kind TEXT NOT NULL CHECK (author_kind IN ('person', 'agent', 'system')),
                kind TEXT NOT NULL CHECK (kind IN ('message', 'notice', 'summary', 'question', 'answer')),
                body TEXT NOT NULL,
                mentions TEXT NOT NULL DEFAULT '[]',
                mandate_id TEXT,
                decision_id TEXT,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX chat_messages_workspace ON chat_messages(workspace_id, created_at)",
            # Where the chat context of the next agent turn starts: the position (rowid) of the
            # newest message an agent turn has been shown.
            """CREATE TABLE workspace_chat_state (
                workspace_id TEXT PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
                seen_up_to INTEGER NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE decisions (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
                mandate_id TEXT NOT NULL REFERENCES mandates(id) ON DELETE CASCADE,
                requester_id TEXT NOT NULL,
                doc_id TEXT,
                block_id TEXT,
                block_digest TEXT,
                quote TEXT,
                question TEXT NOT NULL,
                options TEXT NOT NULL,
                recommended INTEGER,
                status TEXT NOT NULL CHECK (status IN ('open', 'proposed', 'answered', 'cancelled')),
                answer TEXT,
                answered_by TEXT,
                answered_at TEXT,
                accepted_by TEXT,
                accepted_at TEXT,
                created_at TEXT NOT NULL
            )""",
            "CREATE INDEX decisions_workspace ON decisions(workspace_id, created_at)",
            "CREATE INDEX decisions_mandate ON decisions(mandate_id)",
            # A dispatched mandate's current turn: offered to the requester's jiuwenswarm, picked up, and
            # the accepted answer the next turn starts with.
            "ALTER TABLE mandates ADD COLUMN dispatched_at TEXT",
            "ALTER TABLE mandates ADD COLUMN claimed_at TEXT",
            "ALTER TABLE mandates ADD COLUMN turn_id TEXT",
            "ALTER TABLE mandates ADD COLUMN answer TEXT",
            "CREATE INDEX mandates_requester ON mandates(requester_id, status)",
        ),
    ),
    (
        5,
        (
            # The version the document service took after the batch (milestone 6).
            "ALTER TABLE receipts ADD COLUMN version_id TEXT",
        ),
    ),
    (
        6,
        (
            # Shared IM bots, made by the host operator (milestone 7).
            """CREATE TABLE bots (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_by TEXT NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT
            )""",
            # IM accounts people connected to their user; a bot acts for them.
            """CREATE TABLE im_identities (
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                display_name TEXT,
                bot_id TEXT,
                linked_at TEXT NOT NULL,
                PRIMARY KEY (platform, external_id)
            )""",
            "CREATE INDEX im_identities_user ON im_identities(user_id)",
            """CREATE TABLE im_link_codes (
                code TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )""",
        ),
    ),
    (
        7,
        (
            # Hosts created during milestone 2's development have invites with expires_at and
            # max_uses NOT NULL, from before invites could last forever or have no limit; migration 1
            # was changed without a migration of its own. SQLite cannot drop a NOT NULL, so the table
            # is rebuilt with its rows (a no-op in effect where it was already right).
            """CREATE TABLE invites_rebuilt (
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
            """INSERT INTO invites_rebuilt (code, workspace_id, role, created_by, created_at, expires_at, max_uses, uses, revoked_at)
               SELECT code, workspace_id, role, created_by, created_at, expires_at, max_uses, uses, revoked_at FROM invites""",
            "DROP TABLE invites",
            "ALTER TABLE invites_rebuilt RENAME TO invites",
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
