import random

import pytest

from app.game_engine import (
    advance_bots,
    build_shoe,
    cut_deck,
    determine_trick_winner,
    legal_card_ids,
    score_round,
    finish_round,
    initialize_team_game,
    start_card_draw,
    start_game,
    start_round,
    submit_bid,
    submit_team_bid,
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


def test_team_estimates_are_followed_by_captain_combined_bids():
    players = [
        Player(id="a1", name="A1", seat=0, team="A", draw_card=card("a1d", "hearts", 4)),
        Player(id="b1", name="B1", seat=1, team="B", draw_card=card("b1d", "clubs", 5)),
        Player(id="a2", name="A2", seat=2, team="A", draw_card=card("a2d", "spades", 12)),
        Player(id="b2", name="B2", seat=3, team="B", draw_card=card("b2d", "diamonds", 13)),
    ]
    room = GameRoom(code="TEAMB", host_player_id="a1", max_players=4, mode="teams", team_count=2, players=players)
    initialize_team_game(room)
    room.phase = "bidding"
    room.round_number = 3
    room.turn_seat = 0
    room.leader_seat = 0
    room.team_bid_order = ["A", "B"]
    room.team_bids = {"A": None, "B": None}

    for player, estimate in zip(players, [1, 0, 2, 1]):
        submit_bid(room, player.id, estimate)

    assert room.bidding_stage == "teams"
    assert room.team_captains == {"A": "a2", "B": "b2"}
    assert [player.bid for player in players] == [1, 0, 2, 1]
    with pytest.raises(ValueError, match="captain A2"):
        submit_team_bid(room, "a1", 2)
    submit_team_bid(room, "a2", 2)
    submit_team_bid(room, "b2", 1)
    assert room.phase == "playing"
    assert room.team_bids == {"A": 2, "B": 1}


def test_team_round_scores_once_per_team_and_keeps_player_tricks():
    players = [
        Player(id="a1", name="A1", seat=0, team="A", tricks=2),
        Player(id="b1", name="B1", seat=1, team="B", tricks=1),
        Player(id="a2", name="A2", seat=2, team="A", tricks=2),
        Player(id="b2", name="B2", seat=3, team="B", tricks=1),
    ]
    room = GameRoom(code="TEAMS", host_player_id="a1", max_players=4, mode="teams", team_count=2, players=players)
    room.phase = "playing"
    room.round_number = 4
    room.team_bid_order = ["A", "B"]
    room.team_bids = {"A": 3, "B": 3}
    room.team_scores = {"A": 10, "B": 20}
    room.team_gross_scores = {"A": 10, "B": 20}
    room.team_bags = {"A": 4, "B": 0}
    room.team_total_bags = {"A": 4, "B": 0}

    rows = finish_round(room)

    assert [(row["name"], row["won"]) for row in rows] == [("Team A", 4), ("Team B", 2)]
    assert room.team_scores == {"A": -9, "B": -8}
    assert room.team_bags == {"A": 0, "B": 0}
    assert [player.tricks for player in players] == [2, 1, 2, 1]


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


def test_team_draw_separates_teammates_and_keeps_strongest_draw_last():
    players = [
        Player(id="p1", name="P1", seat=0, team="A"),
        Player(id="p2", name="P2", seat=1, team="B"),
        Player(id="p3", name="P3", seat=2, team="C"),
        Player(id="p4", name="P4", seat=3, team="C"),
        Player(id="p5", name="P5", seat=4, team="A"),
        Player(id="p6", name="P6", seat=5, team="B"),
    ]
    room = GameRoom(code="TEAM6", host_player_id="p1", max_players=6, mode="teams", team_count=3, teams_locked=True, players=players)
    start_card_draw(room, random.Random(9))
    chosen = [(3, "hearts"), (13, "clubs"), (4, "diamonds"), (6, "clubs"), (5, "hearts"), (7, "spades")]
    for player, (rank, suit) in zip(players, chosen):
        selected = next(card for card in room.draw_deck if card.rank == rank and card.suit == suit)
        pick_draw_card(room, player.id, selected.id)

    assert [player.id for player in room.players] == ["p1", "p3", "p6", "p5", "p4", "p2"]
    teams = [player.team for player in room.players]
    assert all(teams[index] != teams[(index + 1) % len(teams)] for index in range(len(teams)))
    assert room.players[-1].id == "p2"


def test_round_thirteen_has_final_seat_bid_last():
    players = [Player(id=f"p{i}", name=f"P{i}", seat=i) for i in range(8)]
    room = GameRoom(code="LAST8", host_player_id="p0", max_players=8, mode="individual", deck_count=2, players=players)

    start_round(room, 13, random.Random(10))

    assert room.leader_seat == 0
    assert room.turn_seat == 0


def test_round_rotation_counts_backward_from_round_thirteen_without_reset():
    players = [Player(id=f"p{i}", name=f"P{i}", seat=i) for i in range(5)]
    room = GameRoom(code="ROT5", host_player_id="p0", max_players=5, mode="individual", deck_count=2, players=players)
    expected_last_seats = [3, 4, 5, 1, 2, 3, 4, 5, 1, 2, 3, 4, 5]

    actual_last_seats = []
    for round_number in range(1, 14):
        start_round(room, round_number, random.Random(round_number))
        actual_last_seats.append(((room.leader_seat - 1) % len(players)) + 1)

    assert actual_last_seats == expected_last_seats


def test_backward_anchored_rotation_generalizes_to_other_player_counts():
    for player_count in (7, 8, 9, 16):
        players = [Player(id=f"p{i}", name=f"P{i}", seat=i) for i in range(player_count)]
        room = GameRoom(code=f"R{player_count}", host_player_id="p0", max_players=player_count, mode="individual", deck_count=4, players=players)
        last_seats = []
        for round_number in range(1, 14):
            start_round(room, round_number, random.Random(round_number))
            last_seats.append(((room.leader_seat - 1) % player_count) + 1)

        assert last_seats[-3:] == [player_count - 2, player_count - 1, player_count]
        assert all(current == (previous % player_count) + 1 for previous, current in zip(last_seats, last_seats[1:]))


@pytest.mark.parametrize("player_count", range(2, 17))
def test_every_supported_player_count_has_continuous_round_rotation(player_count):
    players = [Player(id=f"p{i}", name=f"P{i}", seat=i) for i in range(player_count)]
    room = GameRoom(code=f"ALL{player_count}", host_player_id="p0", max_players=player_count, mode="individual", deck_count=4, players=players)
    last_seats = []

    for round_number in range(1, 14):
        start_round(room, round_number, random.Random(round_number))
        last_seats.append(((room.leader_seat - 1) % player_count) + 1)

    assert last_seats[-1] == player_count
    assert all(current == (previous % player_count) + 1 for previous, current in zip(last_seats, last_seats[1:]))


@pytest.mark.parametrize(
    ("player_count", "team_count"),
    [(4, 2), (6, 2), (6, 3), (8, 2), (8, 4), (9, 3), (10, 2), (10, 5),
     (12, 2), (12, 3), (12, 4), (12, 6), (14, 2), (14, 7), (15, 3), (15, 5),
     (16, 2), (16, 4), (16, 8)],
)
def test_every_valid_team_configuration_separates_teammates(player_count, team_count):
    players = [
        Player(id=f"p{i}", name=f"P{i}", seat=i, team=chr(65 + (i % team_count)))
        for i in range(player_count)
    ]
    room = GameRoom(
        code=f"T{player_count}{team_count}",
        host_player_id="p0",
        max_players=player_count,
        mode="teams",
        team_count=team_count,
        teams_locked=True,
        players=players,
    )
    start_card_draw(room, random.Random(player_count * 10 + team_count))
    available = sorted(
        room.draw_deck,
        key=lambda draw: (int(draw.rank or 0), {"clubs": 0, "diamonds": 1, "hearts": 2, "spades": 3}[str(draw.suit)]),
    )
    for player, selected in zip(players, available):
        pick_draw_card(room, player.id, selected.id)

    teams = [player.team for player in room.players]
    assert all(teams[index] != teams[(index + 1) % len(teams)] for index in range(len(teams)))
    strongest_player = max(players, key=lambda player: (int(player.draw_card.rank or 0), {"clubs": 0, "diamonds": 1, "hearts": 2, "spades": 3}[str(player.draw_card.suit)]))
    assert room.players[-1].id == strongest_player.id


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
