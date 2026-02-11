import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # .../Truco
DB_PATH = BASE_DIR / "data" / "truco.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_connection():
    return sqlite3.connect(str(DB_PATH))


def create_tables():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)


def ensure_schema_or_raise():
    """Falha cedo com mensagem clara se o banco for antigo."""
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(users);")
        cols = {row[1] for row in cur.fetchall()}  # row[1] = nome da coluna
    required = {"id", "username", "password_hash", "role", "created_at"}
    missing = required - cols
    if missing:
        raise RuntimeError(
            "Seu banco está com schema antigo. Apague data/truco.db (e server/truco.db se existir) "
            f"e rode o servidor de novo. Faltando colunas: {sorted(missing)}"
        )


def create_user(username: str, password_hash: str, role: str = "user") -> bool:
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, password_hash, role),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def get_user_by_username(username: str):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        )
        return cur.fetchone()
