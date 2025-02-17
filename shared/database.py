import sqlite3
import os
from pathlib import Path

def get_db_connection():
    """Create a database connection."""
    db_path = Path(__file__).parent.parent / 'database' / 'painter.db'
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        raise Exception(f"Database connection error: {e}")

def init_db():
    """Initialize the database with schema."""
    conn = get_db_connection()
    try:
        with conn:
            with open(Path(__file__).parent.parent / 'database' / 'schema.sql') as f:
                conn.executescript(f.read())
    except sqlite3.Error as e:
        raise Exception(f"Database initialization error: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
