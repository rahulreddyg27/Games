import random

from app.game_engine import continue_after_trick, cut_deck, legal_card_ids, next_round, play_card, start_game, submit_bid
from app.models import GameRoom, Player


def test_full_eight_player_thirteen_round_game_completes():
    players = [Player(id=f"p{i}", name=f"P{i+1}", seat=i) for i in range(8)]
    room = GameRoom(
        code="FULL8",
        host_player_id="p0",
        max_players=8,
        mode="individual",
        players=players,
    )
    rng = random.Random(2026)
    start_game(room, rng)

    for round_no in range(1, 14):
        assert room.round_number == round_no
        assert room.phase == "cutting"
        assert room.cutter_player_id is not None
        cut_deck(room, room.cutter_player_id, round_no)
        assert room.phase == "bidding"

        while room.phase == "bidding":
            player = room.player_by_seat(room.turn_seat)
            submit_bid(room, player.id, min(player.seat % 3, round_no))

        while room.phase == "playing":
            current = room.player_by_seat(room.turn_seat)
            legal = legal_card_ids(room, current.id)
            card_id = next(card.id for card in current.hand if card.id in legal)
            play_card(room, current.id, card_id)
            if room.awaiting_next_trick:
                continue_after_trick(room)

        if round_no < 13:
            next_round(room, rng)

    assert room.phase == "finished"
    assert len(room.round_history) == 13
    assert all(len(player.hand) == 0 for player in players)
