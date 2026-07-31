import sqlite3

import pytest

import database


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    db_path = tmp_path / "alpha_scout.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path))
    database.init_db()
    return db_path


def test_session_and_message_lifecycle_is_scoped_by_user(isolated_database):
    session_id = database.create_session("user-a", "NVDA thesis")
    database.save_message("user-a", session_id, "user", "Analyze NVDA")
    database.save_message("user-a", session_id, "assistant", "Research result")

    assert database.get_all_sessions("user-a") == [(session_id, "NVDA thesis")]
    assert database.get_all_sessions("user-b") == []
    assert database.load_messages("user-a", session_id) == [
        {"role": "user", "content": "Analyze NVDA"},
        {"role": "assistant", "content": "Research result"},
    ]
    assert database.load_messages("user-b", session_id) == []


def test_user_cannot_write_update_or_delete_another_users_session(
    isolated_database,
):
    session_id = database.create_session("owner", "Private research")

    with pytest.raises(PermissionError):
        database.save_message("intruder", session_id, "user", "Overwrite")

    assert database.update_session_title("intruder", session_id, "Changed") is False
    assert database.delete_session("intruder", session_id) is False
    assert database.get_all_sessions("owner") == [(session_id, "Private research")]


def test_deleting_session_cascades_to_messages(isolated_database):
    session_id = database.create_session("owner")
    database.save_message("owner", session_id, "user", "Hello")

    assert database.delete_session("owner", session_id) is True

    with sqlite3.connect(isolated_database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    assert count == 0


def test_init_db_migrates_legacy_sessions(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "INSERT INTO sessions (id, title) VALUES ('old-session', 'Old chat')"
        )
        connection.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO messages (session_id, role, content)
            VALUES ('old-session', 'user', 'Legacy message')
            """
        )

    monkeypatch.setattr(database, "DB_NAME", str(db_path))
    database.init_db()

    assert database.get_all_sessions("legacy") == [("old-session", "Old chat")]
    assert database.delete_session("legacy", "old-session") is True
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
