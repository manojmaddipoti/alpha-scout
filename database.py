"""SQLite persistence for user-scoped conversations."""

from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path


DB_NAME = os.getenv("DB_PATH", "data/alpha_scout.db")


def get_connection() -> sqlite3.Connection:
    """Create a configured SQLite connection and its parent directory."""
    db_path = Path(DB_NAME).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def init_db() -> None:
    """Create tables and migrate databases created before per-user isolation."""
    with get_connection() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS research_workspaces (user_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute("""CREATE TABLE IF NOT EXISTS research_reports (
            session_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, payload TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE)""")
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "user_id" not in columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN user_id TEXT NOT NULL DEFAULT 'legacy'"
            )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_created "
            "ON sessions(user_id, created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_session_id "
            "ON messages(session_id, id)"
        )


def create_session(user_id: str, title: str = "New Chat") -> str:
    """Create and return a conversation owned by ``user_id``."""
    session_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)",
            (session_id, user_id, title),
        )
    return session_id


def get_all_sessions(user_id: str) -> list[tuple[str, str]]:
    """Return only the authenticated user's sessions, newest first."""
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT id, title
            FROM sessions
            WHERE user_id = ?
            ORDER BY created_at DESC, rowid DESC
            """,
            (user_id,),
        ).fetchall()


def update_session_title(user_id: str, session_id: str, new_title: str) -> bool:
    """Update a session title when the user owns it."""
    with get_connection() as connection:
        cursor = connection.execute(
            "UPDATE sessions SET title = ? WHERE id = ? AND user_id = ?",
            (new_title, session_id, user_id),
        )
    return cursor.rowcount == 1


def delete_session(user_id: str, session_id: str) -> bool:
    """Delete a user-owned session and its messages.

    The explicit message delete also supports databases created before the
    foreign key gained ``ON DELETE CASCADE``.
    """
    with get_connection() as connection:
        connection.execute(
            """
            DELETE FROM messages
            WHERE session_id IN (
                SELECT id FROM sessions WHERE id = ? AND user_id = ?
            )
            """,
            (session_id, user_id),
        )
        cursor = connection.execute(
            "DELETE FROM sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        )
    return cursor.rowcount == 1


def save_message(user_id: str, session_id: str, role: str, content: str) -> None:
    """Save a message only when the user owns the target session."""
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO messages (session_id, role, content)
            SELECT id, ?, ?
            FROM sessions
            WHERE id = ? AND user_id = ?
            """,
            (role, content, session_id, user_id),
        )
    if cursor.rowcount != 1:
        raise PermissionError("Session does not exist or is not owned by this user")


def load_messages(user_id: str, session_id: str) -> list[dict[str, str]]:
    """Load messages only when the user owns the target session."""
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT messages.role, messages.content
            FROM messages
            JOIN sessions ON sessions.id = messages.session_id
            WHERE messages.session_id = ? AND sessions.user_id = ?
            ORDER BY messages.id ASC
            """,
            (session_id, user_id),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in rows]


def clear_all_data() -> None:
    """Delete all stored data. Intended for explicit administrative maintenance."""
    with get_connection() as connection:
        connection.execute("DELETE FROM messages")
        connection.execute("DELETE FROM sessions")
        connection.execute("DELETE FROM research_workspaces")


def load_workspace(user_id: str) -> dict:
    import json
    with get_connection() as connection:
        row = connection.execute('SELECT payload FROM research_workspaces WHERE user_id = ?', (user_id,)).fetchone()
    return json.loads(row[0]) if row else {'context': '', 'entries': []}


def save_workspace(user_id: str, context: str, entries: list) -> None:
    import json
    from research_workspace import validate_workspace
    payload = json.dumps(validate_workspace(context, entries), allow_nan=False)
    with get_connection() as connection:
        connection.execute('INSERT INTO research_workspaces (user_id, payload) VALUES (?, ?) '
                           'ON CONFLICT(user_id) DO UPDATE SET payload = excluded.payload', (user_id, payload))


def save_research_report(user_id: str, payload: str) -> str:
    """Atomically save a ticker-only research run and its conversation."""
    import json
    from stock_research import normalize_ticker
    result = json.loads(payload)
    ticker = normalize_ticker(result['ticker'])
    if not isinstance(result.get('report'), str) or not result['report'].strip():
        raise ValueError('A research report is required')
    session_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute('INSERT INTO sessions (id, user_id, title) VALUES (?, ?, ?)',
                           (session_id, user_id, f'{ticker} independent research'))
        connection.execute('INSERT INTO research_reports (session_id, ticker, payload) VALUES (?, ?, ?)',
                           (session_id, ticker, payload))
        connection.executemany('INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)',
                               [(session_id, 'user', f'Research {ticker} independently'),
                                (session_id, 'assistant', result['report'])])
    return session_id


def load_research_report(user_id: str, session_id: str) -> dict | None:
    import json
    with get_connection() as connection:
        row = connection.execute('SELECT research_reports.payload FROM research_reports JOIN sessions '
                                 'ON sessions.id = research_reports.session_id '
                                 'WHERE sessions.id = ? AND sessions.user_id = ?', (session_id, user_id)).fetchone()
    return json.loads(row[0]) if row else None
