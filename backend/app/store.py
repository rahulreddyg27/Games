from __future__ import annotations

import asyncio
import random
import secrets
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

    def next_team(self, room: GameRoom) -> str | None:
        if room.mode != "teams":
            return None
        labels = list(string.ascii_uppercase[:room.team_count])
        counts = {label: sum(1 for player in room.players if player.team == label) for label in labels}
        return min(labels, key=lambda label: counts[label])

    def valid_team_counts(self, player_count: int) -> list[int]:
        return [count for count in range(2, (player_count // 2) + 1) if player_count % count == 0]

    def create_room(self, host_name: str, max_players: int, mode: str, deck_count: int = 2, team_count: int = 2) -> tuple[GameRoom, Player]:
        code = self.new_code()
        player = Player(
            id=uuid.uuid4().hex,
            name=host_name.strip(),
            seat=0,
            team="A" if mode == "teams" else None,
        )
        room = GameRoom(
            code=code,
            host_player_id=player.id,
            max_players=max_players,
            mode=mode,  # type: ignore[arg-type]
            rejoin_pin=f"{secrets.randbelow(1_000_000):06d}",
            team_count=team_count if mode == "teams" else 0,
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
            if rejoin_pin != room.rejoin_pin:
                raise ValueError("That player name is already taken. Enter its rejoin PIN to return.")
            returning_player.connected = True
            room.message = f"{returning_player.name} rejoined the game"
            return room, returning_player
        if room.phase != "lobby":
            raise ValueError("Game has already started. Rejoin with the same player name.")
        if len(room.players) >= room.max_players:
            raise ValueError("Room is full")

        seat = max((p.seat for p in room.players), default=-1) + 1
        team = self.next_team(room)

        player = Player(
            id=uuid.uuid4().hex,
            name=name.strip(),
            seat=seat,
            team=team,
        )
        room.players.append(player)
        room.teams_locked = False
        room.message = f"{player.name} joined ({len(room.players)}/{room.max_players})"
        return room, player

    def set_team_count(self, room: GameRoom, team_count: int) -> None:
        if room.phase != "lobby":
            raise ValueError("Team setup can only be changed before the game starts")
        if room.mode != "teams":
            raise ValueError("This room is not using team mode")
        if room.teams_locked:
            raise ValueError("Unlock the teams before changing the team setup")
        if team_count not in self.valid_team_counts(room.max_players):
            raise ValueError("That number of teams cannot be divided evenly for this room")

        room.team_count = team_count
        labels = list(string.ascii_uppercase[:team_count])
        for index, player in enumerate(sorted(room.players, key=lambda member: member.seat)):
            player.team = labels[index % team_count]
        room.teams_locked = False
        room.message = f"Team setup changed to {team_count} teams"

    def assign_team(self, room: GameRoom, player_id: str, team: str) -> None:
        if room.phase != "lobby":
            raise ValueError("Teams can only be changed before the game starts")
        if room.mode != "teams":
            raise ValueError("This room is not using team mode")
        if room.teams_locked:
            raise ValueError("Unlock the teams before changing assignments")
        labels = list(string.ascii_uppercase[:room.team_count])
        if team not in labels:
            raise ValueError("That team does not exist in this room")

        player = room.player_by_id(player_id)
        previous_team = player.team
        if previous_team == team:
            return

        player.team = team
        room.teams_locked = False
        room.message = f"{player.name} moved from Team {previous_team} to Team {team}"

    def lock_teams(self, room: GameRoom) -> None:
        if room.phase != "lobby" or room.mode != "teams":
            raise ValueError("Teams can only be locked in a team-mode lobby")
        labels = list(string.ascii_uppercase[:room.team_count])
        capacity = room.max_players // room.team_count
        invalid = [player for player in room.players if player.team not in labels]
        if invalid:
            raise ValueError("Every player must be assigned to a valid team")
        counts = {label: sum(1 for player in room.players if player.team == label) for label in labels}
        overfilled = [label for label, count in counts.items() if count > capacity]
        if overfilled:
            details = ", ".join(f"Team {label}: {counts[label]}/{capacity}" for label in overfilled)
            raise ValueError(f"Move players out of full teams before locking ({details})")
        room.teams_locked = True
        room.message = "Team assignments locked. The host can start the game."

    def unlock_teams(self, room: GameRoom) -> None:
        if room.phase != "lobby" or room.mode != "teams":
            raise ValueError("Teams can only be edited in a team-mode lobby")
        room.teams_locked = False
        room.message = "Team assignments unlocked for editing"

    def fill_with_bots(self, room: GameRoom) -> None:
        """Fill open seats when the host starts, allowing solo play."""
        while len(room.players) < room.max_players:
            seat = max((p.seat for p in room.players), default=-1) + 1
            team = self.next_team(room)
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
