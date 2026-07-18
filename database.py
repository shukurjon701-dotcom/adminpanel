"""
database.py — общая база данных (SQLite) для bot.py и admin_panel.py.

Хранит:
- users: пользователи бота (для дашборда "сколько людей", "кто онлайн")
- messages: лог всех вопросов/ответов (для раздела "какие запросы были")
- knowledge: база знаний, в которую администратор "обучает" ИИ
  (текстом, файлом или картинкой) — подмешивается в системный промпт бота.

Один файл базы (academy_bot.db) используется и ботом, и веб-панелью,
поэтому важно, чтобы оба процесса запускались из одной и той же папки.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# На хостинге путь к базе можно переопределить переменной окружения DB_PATH.
# Локально — рядом с файлами, как и раньше. На Render диск эфемерный, поэтому
# база живёт в рабочей папке и обнуляется при передеплое (это осознанно).
DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "academy_bot.db")))
# Убеждаемся, что папка под базу существует (важно, если DB_PATH указывает в подкаталог).
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

ONLINE_WINDOW_MINUTES = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                full_name TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL,
                username TEXT,
                text TEXT NOT NULL,
                answer TEXT,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


def upsert_user(telegram_id: int, username: Optional[str], full_name: str):
    now = _now()
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE users SET username=?, full_name=?, last_seen=? WHERE telegram_id=?",
                (username, full_name, now, telegram_id),
            )
        else:
            conn.execute(
                "INSERT INTO users (telegram_id, username, full_name, first_seen, last_seen, message_count) "
                "VALUES (?, ?, ?, ?, ?, 0)",
                (telegram_id, username, full_name, now, now),
            )


def log_message(telegram_id: int, username: Optional[str], text: str, answer: Optional[str]):
    now = _now()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO messages (telegram_id, username, text, answer, created_at) VALUES (?, ?, ?, ?, ?)",
            (telegram_id, username, text, answer, now),
        )
        conn.execute(
            "UPDATE users SET message_count = message_count + 1, last_seen = ? WHERE telegram_id = ?",
            (now, telegram_id),
        )


def get_stats() -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ONLINE_WINDOW_MINUTES)).isoformat()
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_connection() as conn:
        total_users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        online_now = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE last_seen >= ?", (cutoff,)
        ).fetchone()["c"]
        total_messages = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
        messages_today = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE created_at >= ?", (today_start,)
        ).fetchone()["c"]
    return {
        "total_users": total_users,
        "online_now": online_now,
        "total_messages": total_messages,
        "messages_today": messages_today,
    }


def get_users(limit: int = 300) -> list:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ONLINE_WINDOW_MINUTES)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT telegram_id, username, full_name, first_seen, last_seen, message_count "
            "FROM users ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for r in rows:
        result.append({
            "telegram_id": r["telegram_id"],
            "username": r["username"],
            "full_name": r["full_name"],
            "first_seen": r["first_seen"],
            "last_seen": r["last_seen"],
            "message_count": r["message_count"],
            "online": r["last_seen"] >= cutoff,
        })
    return result


def get_recent_messages(limit: int = 50) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT telegram_id, username, text, answer, created_at "
            "FROM messages ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_knowledge(title: str, content: str, source_type: str) -> int:
    with get_connection() as conn:
        cur = conn.execute(
            "INSERT INTO knowledge (title, content, source_type, created_at) VALUES (?, ?, ?, ?)",
            (title, content, source_type, _now()),
        )
        return cur.lastrowid


def get_knowledge(limit: int = 200) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, content, source_type, created_at FROM knowledge "
            "ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_knowledge(knowledge_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM knowledge WHERE id = ?", (knowledge_id,))


def get_knowledge_as_prompt_block(limit: int = 100) -> str:
    entries = get_knowledge(limit=limit)
    if not entries:
        return ""
    parts = ["=== QO'SHIMCHA O'RGATILGAN MA'LUMOTLAR ==="]
    for e in reversed(entries):
        parts.append(f"[{e['title']}]\n{e['content']}")
    return "\n\n".join(parts)
