import sqlite3
import uuid
import os

DB_NAME = os.getenv("DB_PATH", "/tmp/data/chat_history.db")

def get_connection():
    """Create database connection."""
    try:
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=10.0)
        return conn
    except Exception as e:
        raise Exception(f"Database connection error: {e}")

def init_db():
    """Initialize database tables."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                role TEXT,
                content TEXT,
                FOREIGN KEY(session_id) REFERENCES sessions(id)
            )
        ''')
        conn.commit()
        conn.close()
    except Exception as e:
        raise Exception(f"Database initialization failed: {e}")

# Session Management
def create_session(title="New Chat"):
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sessions (id, title) VALUES (?, ?)", (session_id, title))
    conn.commit()
    conn.close()
    return session_id

def get_all_sessions():
    """Get all chat sessions sorted by newest first."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM sessions ORDER BY created_at DESC")
        sessions = cursor.fetchall()
        conn.close()
        return sessions
    except Exception:
        return []

def update_session_title(session_id, new_title):
    """Update session title."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, session_id))
    conn.commit()
    conn.close()

def delete_session(session_id):
    """Delete a session and its messages."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
    cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    conn.commit()
    conn.close()

# Message Management
def save_message(session_id, role, content):
    """Save a message to the database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                       (session_id, role, content))
        conn.commit()
        conn.close()
    except Exception:
        pass

def load_messages(session_id):
    """Load all messages for a session."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
        messages = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
        conn.close()
        return messages
    except Exception:
        return []

def clear_all_data():
    """Clear all sessions and messages."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS sessions")
    cursor.execute("DROP TABLE IF EXISTS messages")
    conn.commit()
    conn.close()
    init_db()