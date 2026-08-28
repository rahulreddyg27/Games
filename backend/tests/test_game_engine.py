import random

from app.game_engine import (
    advance_bots,
    build_shoe,
    cut_deck,
    determine_trick_winner,
    legal_card_ids,
    score_round,
    start_card_draw,
    start_game,
    submit_bid,
    pick_draw_card,
)
from app.models import Card, GameRoom, Player, TrickPlay


def card(card_id, suit=None, rank=None, joker=False):
    return Card(id=card_id, suit=suit, rank=rank, is_joker=joker)


def room_with_two_players():
    p1 = Player(id="p1", name="One", seat=0)
    p2 = Player(id="p2", name="Two", seat=1)
    room = GameRoom(code="ABCDE", host_player_id="p1", max_players=8, mode="individual", players=[p1, p2])
    room.phase = "playing"
    room.turn_seat = 0
    return room, p1, p2


def test_eight_players_have_enough_cards_for_round_13_plus_joker():
    shoe = build_shoe(8, random.Random(7))
    assert len(shoe) == 105
    assert sum(1 for c in shoe if c.is_joker) == 1


def test_configured_one_and_two_deck_shoes_include_one_joker():
    one_deck = build_shoe(2, random.Random(1), deck_count=1)
    two_decks = build_shoe(2, random.Random(1), deck_count=2)
    assert len(one_deck) == 53
    assert len(two_decks) == 105
    assert sum(card.is_joker for card in one_deck) == 1
    assert sum(card.is_joker for card in two_decks) == 1


def test_three_deck_shoe_has_157_cards_and_one_joker():
    shoe = build_shoe(8, random.Random(1), deck_count=3)
    assert len(shoe) == 157
    assert sum(card.is_joker for card in shoe) == 1


def test_four_deck_shoe_supports_sixteen_players():
    shoe = build_shoe(16, random.Random(1), deck_count=4)
    assert len(shoe) == 209
    assert sum(card.is_joker for card in shoe) == 1


def test_score_made_bid_and_bags():
    assert score_round(3, 5) == (32, 2)


def test_score_missed_bid():
    assert score_round(3, 2) == (-28, 0)


def test_joker_wins_any_trick():
    plays = [
        TrickPlay("p1", card("ace-spades", "spades", 14)),
        TrickPlay("p2", card("joker", joker=True)),
    ]
    assert determine_trick_winner(plays) == "p2"


def test_spade_trumps_led_heart():
    plays = [
        TrickPlay("p1", card("ace-hearts", "hearts", 14)),
        TrickPlay("p2", card("two-spades", "spades", 2)),
    ]
    assert determine_trick_winner(plays) == "p2"


def test_later_duplicate_high_card_wins_tie():
    plays = [
        TrickPlay("p1", card("ace1", "hearts", 14)),
        TrickPlay("p2", card("ace2", "hearts", 14)),
    ]
    assert determine_trick_winner(plays) == "p2"


def test_joker_is_legal_even_when_player_can_follow_suit():
    room, p1, _ = room_with_two_players()
    room.current_trick = [TrickPlay("p2", card("h9", "hearts", 9))]
    p1.hand = [card("h2", "hearts", 2), card("sA", "spades", 14), card("j", joker=True)]
    legal = legal_card_ids(room, "p1")
    assert legal == {"h2", "j"}


def test_five_bags_apply_minus_50_and_reset_bags():
    from app.game_engine import finish_round
    p = Player(id="p1", name="One", seat=0, bid=1, tricks=6)
    room = GameRoom(code="ABCDE", host_player_id="p1", max_players=4, mode="individual", players=[p])
    room.round_number = 6
    room.phase = "playing"
    rows = finish_round(room)
    assert rows[0]["baseScore"] == 15
    assert rows[0]["scoreBefore"] == 0
    assert rows[0]["scoreAfterRound"] == 15
    assert rows[0]["bagsBefore"] == 0
    assert rows[0]["bagsBeforePenalty"] == 5
    assert rows[0]["bagPenalty"] == -50
    assert rows[0]["totalScore"] == -35
    assert p.total_score == -35
    assert p.gross_score == 15
    assert p.bags == 0
    assert p.total_bags == 5


def test_joker_led_means_no_follow_suit_requirement():
    room, p1, _ = room_with_two_players()
    room.current_trick = [TrickPlay("p2", card("j", joker=True))]
    p1.hand = [card("h2", "hearts", 2), card("sA", "spades", 14)]
    assert legal_card_ids(room, "p1") == {"h2", "sA"}


def test_computer_bids_and_plays_until_human_turn():
    human = Player(id="human", name="Human", seat=0)
    computer = Player(id="bot-1", name="Computer 1", seat=1, is_bot=True)
    room = GameRoom(
        code="SOLO1",
        host_player_id=human.id,
        max_players=2,
        mode="individual",
        players=[human, computer],
    )

    start_game(room, random.Random(4))
    assert room.cutter_player_id == human.id
    cut_deck(room, human.id, 7)
    advance_bots(room)
    assert computer.bid is None
    assert room.phase == "bidding"

    submit_bid(room, human.id, 0)
    advance_bots(room)
    assert computer.bid is not None
    assert room.phase == "playing"
    assert room.player_by_seat(room.turn_seat).id == human.id


def test_pre_game_draw_reorders_players_lowest_to_highest():
    players = [Player(id=f"p{i}", name=f"P{i}", seat=i) for i in range(4)]
    room = GameRoom(code="DRAW1", host_player_id="p0", max_players=4, mode="individual", players=players)
    start_card_draw(room, random.Random(8))

    chosen = [(14, "hearts"), (2, "clubs"), (9, "diamonds"), (14, "spades")]
    for player, (rank, suit) in zip(players, chosen):
        card = next(card for card in room.draw_deck if card.rank == rank and card.suit == suit)
        pick_draw_card(room, player.id, card.id)

    assert room.phase == "draw_complete"
    assert [player.id for player in room.players] == ["p1", "p2", "p0", "p3"]
    assert [player.seat for player in room.players] == [0, 1, 2, 3]
    assert len(room.draw_deck) == 48


def test_cut_rotates_deck_and_deals_from_designated_first_recipient():
    players = [Player(id=f"p{i}", name=f"P{i + 1}", seat=i) for i in range(5)]
    room = GameRoom(code="CUT01", host_player_id="p0", max_players=5, mode="individual", players=players)
    room.phase = "cutting"
    room.round_number = 1
    room.leader_seat = 3
    room.turn_seat = 3
    room.dealer_player_id = "p2"
    room.cutter_player_id = "p1"
    room.pending_shoe = [card(f"c{i}", "clubs", i + 2) for i in range(10)]

    cut_deck(room, "p1", 2)

    assert room.phase == "bidding"
    assert [players[index].hand[0].id for index in (3, 4, 0, 1, 2)] == ["c2", "c3", "c4", "c5", "c6"]
