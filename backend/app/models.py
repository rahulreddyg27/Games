from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Suit = Literal["clubs", "diamonds", "hearts", "spades"]
GameMode = Literal["individual", "teams"]
GamePhase = Literal["lobby", "drawing", "draw_complete", "bidding", "playing", "round_complete", "finished"]

SUIT_SYMBOLS = {
    "clubs": "♣",
    "diamonds": "♦",
    "hearts": "♥",
    "spades": "♠",
}

RANK_LABELS = {
    2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7", 8: "8", 9: "9", 10: "10",
    11: "J", 12: "Q", 13: "K", 14: "A",
}


@dataclass(frozen=True)
class Card:
    id: str
    suit: Suit | None
    rank: int | None
    deck_index: int = 0
    is_joker: bool = False

    @property
    def label(self) -> str:
        if self.is_joker:
            return "🃏"
        assert self.suit is not None and self.rank is not None
        return f"{RANK_LABELS[self.rank]}{SUIT_SYMBOLS[self.suit]}"

    def public(self) -> dict:
        return {
            "id": self.id,
            "suit": self.suit,
            "rank": self.rank,
            "deckIndex": self.deck_index,
            "isJoker": self.is_joker,
            "label": self.label,
        }


@dataclass
class Player:
    id: str
    name: str
    seat: int
    team: str | None = None
    connected: bool = True
    is_bot: bool = False
    hand: list[Card] = field(default_factory=list)
    bid: int | None = None
    tricks: int = 0
    total_score: int = 0
    gross_score: int = 0
    bags: int = 0
    total_bags: int = 0
    draw_card: Card | None = None
    rejoin_pin: str = ""


@dataclass
class TrickPlay:
    player_id: str
    card: Card


@dataclass
class RoundSummary:
    round_number: int
    rows: list[dict]


@dataclass
class GameRoom:
    code: str
    host_player_id: str
    max_players: int
    mode: GameMode
    deck_count: int = 2
    players: list[Player] = field(default_factory=list)
    phase: GamePhase = "lobby"
    round_number: int = 0
    leader_seat: int = 0
    turn_seat: int = 0
    current_trick: list[TrickPlay] = field(default_factory=list)
    completed_tricks: int = 0
    round_history: list[RoundSummary] = field(default_factory=list)
    last_trick_winner_id: str | None = None
    last_trick_cards: list[dict] = field(default_factory=list)
    draw_deck: list[Card] = field(default_factory=list)
    message: str = "Waiting for players"

    def player_by_id(self, player_id: str) -> Player:
        for player in self.players:
            if player.id == player_id:
                return player
        raise KeyError(player_id)

    def player_by_seat(self, seat: int) -> Player:
        for player in self.players:
            if player.seat == seat:
                return player
        raise KeyError(seat)
