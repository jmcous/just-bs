#!/usr/bin/env python3
"""
SQLite database layer for just-bs.
Manages users, leagues, and subscriptions.
"""

import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).parent.parent / "data" / "justbs.db"


def init_db(leagues: list[str]):
    """
    Initialize database with schema if it doesn't exist.
    Seed the leagues table from the provided list.
    """
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create tables if absent
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            email      TEXT    NOT NULL UNIQUE,
            active     INTEGER NOT NULL DEFAULT 1,
            created_at TEXT    NOT NULL DEFAULT (date('now'))
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS leagues (
            id   INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER NOT NULL REFERENCES users(id),
            league_id INTEGER NOT NULL REFERENCES leagues(id),
            team      TEXT    NOT NULL,
            UNIQUE(user_id, league_id, team)
        )
    """)

    # Seed leagues table with any missing leagues
    for league in leagues:
        cursor.execute("SELECT id FROM leagues WHERE name = ?", (league,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO leagues (name) VALUES (?)", (league,))

    conn.commit()
    conn.close()


def get_active_users() -> list[dict]:
    """Return all active users as list of {id, email}."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM users WHERE active = 1 ORDER BY email")
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return users


def get_teams_for_user(user_id: int) -> dict[str, list[str]]:
    """Return user's subscriptions as {league: [team1, team2, ...]}."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT l.name, s.team
        FROM subscriptions s
        JOIN leagues l ON s.league_id = l.id
        WHERE s.user_id = ?
        ORDER BY l.name, s.team
    """, (user_id,))
    result = {}
    for league, team in cursor.fetchall():
        if league not in result:
            result[league] = []
        result[league].append(team)
    conn.close()
    return result


def add_user(email: str) -> int:
    """Add a new user. Returns user id. Raises if email already exists."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (email) VALUES (?)", (email,))
        user_id = cursor.lastrowid
        conn.commit()
        return user_id
    finally:
        conn.close()


def add_subscription(user_id: int, league: str, team: str):
    """Subscribe a user to a team. Idempotent — ignores if already subscribed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM leagues WHERE name = ?",
            (league,)
        )
        league_row = cursor.fetchone()
        if not league_row:
            raise ValueError(f"League '{league}' not found in database")
        league_id = league_row[0]

        cursor.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, league_id, team) VALUES (?, ?, ?)",
            (user_id, league_id, team)
        )
        conn.commit()
    finally:
        conn.close()


def deactivate_user(email: str):
    """Deactivate a user (soft delete). They won't receive emails."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET active = 0 WHERE email = ?", (email,))
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    """Get user id and email by email address."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_user(email: str):
    """Hard delete user and their subscriptions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
        user_row = cursor.fetchone()
        if not user_row:
            raise ValueError(f"User '{email}' not found")
        user_id = user_row[0]

        cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
