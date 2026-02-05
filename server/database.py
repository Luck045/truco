import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "truco.db"

def get_connection():
    return sqlite3.connect(str(DB_PATH))

def create_tables():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL
            )
        """)


def get_or_create_user(username):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        if row:
            return row[0]

        cur.execute("INSERT INTO users (username) VALUES (?)", (username,))
        return cur.lastrowid
