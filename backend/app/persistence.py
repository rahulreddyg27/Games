from __future__ import annotations

import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "spades.db"


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS completed_games (
                room_code TEXT PRIMARY KEY,
                finished_at TEXT DEFAULT CURRENT_TIMESTAMP,
                snapshot_json TEXT NOT NULL
            )
            """
        )


def save_completed_game(room_code: str, snapshot: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT INTO completed_games(room_code, snapshot_json)
            VALUES (?, ?)
            ON CONFLICT(room_code) DO UPDATE SET
              finished_at = CURRENT_TIMESTAMP,
              snapshot_json = excluded.snapshot_json
            """,
            (room_code, json.dumps(snapshot)),
        )


def delete_completed_game(room_code: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM completed_games WHERE room_code = ?", (room_code.upper(),))
