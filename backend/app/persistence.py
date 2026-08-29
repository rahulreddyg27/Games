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


def list_completed_games() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT room_code, finished_at, snapshot_json FROM completed_games ORDER BY finished_at DESC"
        ).fetchall()
    games = []
    for row in rows:
        try:
            snapshot = json.loads(row["snapshot_json"])
        except (TypeError, json.JSONDecodeError):
            snapshot = {}
        players = snapshot.get("players", [])
        host_id = snapshot.get("hostPlayerId")
        host = next((player for player in players if player.get("id") == host_id), {})
        games.append(
            {
                "code": row["room_code"],
                "status": "completed",
                "hostName": host.get("name", "Unknown"),
                "playerCount": len([player for player in players if not player.get("isBot")]),
                "botCount": len([player for player in players if player.get("isBot")]),
                "roundNumber": snapshot.get("roundNumber", 13),
                "finishedAt": row["finished_at"],
                "storage": "sqlite",
            }
        )
    return games


def delete_all_completed_games() -> int:
    with sqlite3.connect(DB_PATH) as conn:
        count = int(conn.execute("SELECT COUNT(*) FROM completed_games").fetchone()[0])
        conn.execute("DELETE FROM completed_games")
    return count
