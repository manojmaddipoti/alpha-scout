import sqlite3
import uuid
import os
from datetime import datetime

# CRITICAL FIX: Use /tmp directory for App Runner (filesystem is read-only elsewhere)
DB_NAME = os.getenv("DB_PATH", "/tmp/data/chat_history.db")

print(f"📁 Database path: {DB_NAME}", flush=True)

def get_connection():
    """Create database connection with proper error handling"""
    try:
        # Ensure the directory exists
        db_dir = os.path.dirname(DB_NAME)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            print(f"✅ Created database directory: {db_dir}", flush=True)
        
        conn = sqlite3.connect(DB_NAME, check_same_thread=False, timeout=10.0)
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}", flush=True)
        raise

def init_db():
    """Initialize database with proper error handling"""
    try:
        print("🗄️ Initializing database...", flush=True)
        conn = get_connection()
        cursor = conn.cursor()
        
        # Table 1: Sessions (The list in the sidebar)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Table 2: Messages (Linked to a session)
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
        print("✅ Database initialized successfully", flush=True)
    except Exception as e:
        print(f"❌ Database initialization failed: {e}", flush=True)
        raise

# --- Session Management ---
def create_session(title="New Chat"):
    """Create a new chat session"""
    try:
        session_id = str(uuid.uuid4())
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions (id, title) VALUES (?, ?)", (session_id, title))
        conn.commit()
        conn.close()
        print(f"✅ Created session: {session_id}", flush=True)
        return session_id
    except Exception as e:
        print(f"❌ Session creation error: {e}", flush=True)
        raise

def get_all_sessions():
    """Returns a list of all chat sessions sorted by newest first."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM sessions ORDER BY created_at DESC")
        sessions = cursor.fetchall()
        conn.close()
        return sessions
    except Exception as e:
        print(f"❌ Error fetching sessions: {e}", flush=True)
        return []  # Return empty list instead of crashing

def update_session_title(session_id, new_title):
    """Update the title of an existing session"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE sessions SET title = ? WHERE id = ?", (new_title, session_id))
        conn.commit()
        conn.close()
        print(f"✅ Updated session title: {session_id}", flush=True)
    except Exception as e:
        print(f"❌ Session update error: {e}", flush=True)
        raise

def delete_session(session_id):
    """Delete a session and all its messages"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        print(f"✅ Deleted session: {session_id}", flush=True)
    except Exception as e:
        print(f"❌ Session deletion error: {e}", flush=True)
        raise

# --- Message Management ---
def save_message(session_id, role, content):
    """Save a message to the database"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)", 
                       (session_id, role, content))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Message save error: {e}", flush=True)
        # Don't raise - allow app to continue even if save fails

def load_messages(session_id):
    """Load all messages for a session"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC", (session_id,))
        messages = [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
        conn.close()
        return messages
    except Exception as e:
        print(f"❌ Message load error: {e}", flush=True)
        return []  # Return empty list instead of crashing

def clear_all_data():
    """Wipes everything (Factory Reset)"""
    try:
        print("🗑️ Clearing all data...", flush=True)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS sessions")
        cursor.execute("DROP TABLE IF EXISTS messages")
        conn.commit()
        conn.close()
        init_db()
        print("✅ All data cleared", flush=True)
    except Exception as e:
        print(f"❌ Data clear error: {e}", flush=True)
        raise

# Test database connection on import
try:
    print(f"🔍 Testing database connection to {DB_NAME}...", flush=True)
    test_conn = get_connection()
    test_conn.close()
    print("✅ Database connection test successful", flush=True)
except Exception as e:
    print(f"⚠️ Database connection test failed: {e}", flush=True)
    print("   App will attempt to initialize on first use", flush=True)