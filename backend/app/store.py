from __future__ import annotations

import asyncio
import random
import string
import uuid
from collections import defaultdict

from fastapi import WebSocket

from .models import GameRoom, Player


class RoomStore:
    def __init__(self) -> None:
        self.rooms: dict[str, GameRoom] = {}
        self.connections: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        self.lock = asyncio.Lock()

    def new_code(self) -> str:
        while True:
            code = "".join(random.choices(string.ascii_uppercase + string.digits, k=5))
            if code not in self.rooms:
                return code

    def create_room(self, host_name: str, max_players: int, mode: str, deck_count: int = 2) -> tuple[GameRoom, Player]:
        code = self.new_code()
        player = Player(
            id=uuid.uuid4().hex,
            name=host_name.strip(),
            seat=0,
            team="A" if mode == "teams" else None,
            rejoin_pin=f"{random.randint(0, 999999):06d}",
        )
        room = GameRoom(
            code=code,
            host_player_id=player.id,
            max_players=max_players,
            mode=mode,  # type: ignore[arg-type]
            deck_count=deck_count,
            players=[player],
        )
        self.rooms[code] = room
        return room, player

    def join_room(self, code: str, name: str, rejoin_pin: str | None = None) -> tuple[GameRoom, Player]:
        room = self.rooms.get(code.upper())
        if room is None:
            raise KeyError("Room not found")
        normalized_name = name.strip().casefold()
        returning_player = next(
            (p for p in room.players if not p.is_bot and p.name.casefold() == normalized_name),
            None,
        )
        if returning_player is not None:
            if rejoin_pin != returning_player.rejoin_pin:
                raise ValueError("That player name is already taken. Enter its rejoin PIN to return.")
            returning_player.connected = True
            room.message = f"{returning_player.name} rejoined the game"
            return room, returning_player
        if room.phase != "lobby":
            raise ValueError("Game has already started. Rejoin with the same player name.")
        if len(room.players) >= room.max_players:
            raise ValueError("Room is full")

        seat = max((p.seat for p in room.players), default=-1) + 1
        team = None
        if room.mode == "teams":
            counts = {
                "A": sum(1 for p in room.players if p.team == "A"),
                "B": sum(1 for p in room.players if p.team == "B"),
            }
            team = "A" if counts["A"] <= counts["B"] else "B"

        player = Player(
            id=uuid.uuid4().hex,
            name=name.strip(),
            seat=seat,
            team=team,
            rejoin_pin=f"{random.randint(0, 999999):06d}",
        )
        room.players.append(player)
        room.message = f"{player.name} joined ({len(room.players)}/{room.max_players})"
        return room, player

    def fill_with_bots(self, room: GameRoom) -> None:
        """Fill open seats when the host starts, allowing solo play."""
        while len(room.players) < room.max_players:
            seat = max((p.seat for p in room.players), default=-1) + 1
            team = None
            if room.mode == "teams":
                counts = {
                    "A": sum(1 for p in room.players if p.team == "A"),
                    "B": sum(1 for p in room.players if p.team == "B"),
                }
                team = "A" if counts["A"] <= counts["B"] else "B"
            room.players.append(
                Player(
                    id=f"bot-{uuid.uuid4().hex}",
                    name=f"Computer {seat}",
                    seat=seat,
                    team=team,
                    is_bot=True,
                )
            )


store = RoomStore()
