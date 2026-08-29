from __future__ import annotations

import math
import random
import uuid

from .models import Card, GameRoom, Player, RoundSummary, TrickPlay

SUITS = ("clubs", "diamonds", "hearts", "spades")


class GameRuleError(ValueError):
    pass


def decks_needed(player_count: int) -> int:
    """Enough 52-card decks to deal 13 cards to every player. Joker is extra."""
    return max(1, math.ceil((player_count * 13) / 52))


def build_shoe(player_count: int, rng: random.Random | None = None, deck_count: int | None = None) -> list[Card]:
    rng = rng or random.Random()
    cards: list[Card] = []
    count = deck_count if deck_count is not None else decks_needed(player_count)
    for deck_index in range(count):
        for suit in SUITS:
            for rank in range(2, 15):
                cards.append(
                    Card(
                        id=f"d{deck_index}-{suit}-{rank}-{uuid.uuid4().hex[:6]}",
                        suit=suit,  # type: ignore[arg-type]
                        rank=rank,
                        deck_index=deck_index,
                    )
                )
    cards.append(Card(id=f"joker-{uuid.uuid4().hex[:8]}", suit=None, rank=None, is_joker=True))
    rng.shuffle(cards)
    return cards


def start_game(room: GameRoom, rng: random.Random | None = None) -> None:
    if room.phase not in ("lobby", "draw_complete"):
        raise GameRuleError("Game has already started")
    if len(room.players) < 2:
        raise GameRuleError("At least two players, including computer players, are required")
    start_round(room, 1, rng)


def start_card_draw(room: GameRoom, rng: random.Random | None = None) -> None:
    if room.phase != "lobby":
        raise GameRuleError("The seating draw has already started")
    if len(room.players) < 2:
        raise GameRuleError("At least two players are required")
    rng = rng or random.Random()
    room.draw_deck = [
        Card(id=f"draw-{uuid.uuid4().hex}", suit=suit, rank=rank)
        for suit in SUITS
        for rank in range(2, 15)
    ]
    rng.shuffle(room.draw_deck)
    for player in room.players:
        player.draw_card = None
    room.phase = "drawing"
    room.message = "Pick one facedown card to determine the player order"


def draw_order_key(player) -> tuple[int, int]:
    if player.draw_card is None or player.draw_card.rank is None or player.draw_card.suit is None:
        raise GameRuleError("Every player must pick a card")
    suit_order = {"clubs": 0, "diamonds": 1, "hearts": 2, "spades": 3}
    return (player.draw_card.rank, suit_order[player.draw_card.suit])


def seating_order_after_draw(room: GameRoom) -> list[Player]:
    if room.mode != "teams":
        return sorted(room.players, key=draw_order_key)

    teams: dict[str, list[Player]] = {}
    for player in room.players:
        if player.team is None:
            raise GameRuleError("Every player must have a team before the seating draw")
        teams.setdefault(player.team, []).append(player)

    for members in teams.values():
        members.sort(key=draw_order_key)

    # Weakest team maximum goes first; the team with the strongest individual
    # draw owns the final position. Interleaving keeps teammates separated.
    team_order = sorted(teams, key=lambda team: draw_order_key(max(teams[team], key=draw_order_key)))
    member_count = len(room.players) // len(team_order)
    return [teams[team][index] for index in range(member_count) for team in team_order]


def initialize_team_game(room: GameRoom) -> None:
    if room.mode != "teams":
        return
    labels = sorted({player.team for player in room.players if player.team})
    room.team_captains = {
        team: max((player for player in room.players if player.team == team), key=draw_order_key).id
        for team in labels
    }
    for team in labels:
        room.team_scores.setdefault(team, 0)
        room.team_gross_scores.setdefault(team, 0)
        room.team_bags.setdefault(team, 0)
        room.team_total_bags.setdefault(team, 0)


def pick_draw_card(room: GameRoom, player_id: str, card_id: str) -> None:
    if room.phase != "drawing":
        raise GameRuleError("Card picking is not open")
    player = room.player_by_id(player_id)
    if player.draw_card is not None:
        raise GameRuleError("You have already picked a card")
    card = next((item for item in room.draw_deck if item.id == card_id), None)
    if card is None:
        raise GameRuleError("That card has already been picked")
    room.draw_deck.remove(card)
    player.draw_card = card

    if all(item.draw_card is not None for item in room.players):
        room.players = seating_order_after_draw(room)
        for seat, item in enumerate(room.players):
            item.seat = seat
        initialize_team_game(room)
        room.phase = "draw_complete"
        room.message = "Card draw complete. Seating is team-aware; the strongest draw bids last."
    else:
        room.message = "Waiting for every player to pick a card"


def advance_bot_draws(room: GameRoom) -> None:
    if room.phase != "drawing":
        return
    for player in room.players:
        if player.is_bot and player.draw_card is None:
            pick_draw_card(room, player.id, random.choice(room.draw_deck).id)


def bot_bid(room: GameRoom, player_id: str) -> int:
    """Choose a simple bid from the bot's high cards and spades."""
    player = room.player_by_id(player_id)
    likely_tricks = sum(
        1
        for card in player.hand
        if card.is_joker or (card.rank is not None and card.rank >= 13) or (card.suit == "spades" and (card.rank or 0) >= 11)
    )
    return min(room.round_number, likely_tricks)


def bot_card_id(room: GameRoom, player_id: str) -> str:
    """Play the lowest legal normal card, saving the Joker when possible."""
    player = room.player_by_id(player_id)
    legal = legal_card_ids(room, player_id)
    cards = [card for card in player.hand if card.id in legal]
    cards.sort(key=lambda card: (card.is_joker, card_sort_key(card)))
    if not cards:
        raise GameRuleError("Computer player has no legal card")
    return cards[0].id


def advance_bots(room: GameRoom) -> None:
    """Advance automatic bidding and card play until a human decision is needed."""
    while room.phase == "bidding" and (room.mode != "teams" or room.bidding_stage == "estimates"):
        player = room.player_by_seat(room.turn_seat)
        if not player.is_bot:
            break
        submit_bid(room, player.id, bot_bid(room, player.id))

    while room.phase == "bidding" and room.mode == "teams" and room.bidding_stage == "teams":
        team = room.team_bid_order[room.team_turn_index]
        captain = room.player_by_id(room.team_captains[team])
        if not captain.is_bot:
            break
        estimate = sum(int(player.bid or 0) for player in room.players if player.team == team)
        submit_team_bid(room, captain.id, min(room.round_number, estimate))

    while room.phase == "playing" and not room.awaiting_next_trick:
        player = room.player_by_seat(room.turn_seat)
        if not player.is_bot:
            break
        play_card(room, player.id, bot_card_id(room, player.id))


def start_round(room: GameRoom, round_number: int, rng: random.Random | None = None) -> None:
    if round_number < 1 or round_number > 13:
        raise GameRuleError("Round must be between 1 and 13")
    room.round_number = round_number
    room.phase = "cutting"
    room.current_trick = []
    room.completed_tricks = 0
    room.awaiting_next_trick = False
    room.last_trick_winner_id = None
    room.last_trick_cards = []

    shoe = build_shoe(len(room.players), rng, room.deck_count)
    needed = len(room.players) * round_number
    if needed > len(shoe):
        raise GameRuleError("Not enough cards in the configured shoe")

    for player in room.players:
        player.hand = []
        player.bid = None
        player.tricks = 0

    if room.mode == "teams":
        labels = []
        for player in sorted(room.players, key=lambda member: member.seat):
            if player.team and player.team not in labels:
                labels.append(player.team)
        offset = (round_number - 13) % len(labels)
        room.team_bid_order = labels[offset:] + labels[:offset]
        room.team_bids = {team: None for team in labels}
        room.team_turn_index = 0
        room.bidding_stage = "estimates"

    # Anchor the continuous rotation at Round 13: seat 0 bids first and the
    # strongest-draw final seat bids last. Earlier rounds count backward from
    # that arrangement, avoiding a special reset between Rounds 12 and 13.
    room.leader_seat = (round_number - 13) % len(room.players)
    room.turn_seat = room.leader_seat

    dealer_seat = (room.leader_seat - 1) % len(room.players)
    cutter_seat = (dealer_seat - 1) % len(room.players)
    room.dealer_player_id = room.player_by_seat(dealer_seat).id
    room.cutter_player_id = room.player_by_seat(cutter_seat).id
    room.cut_position = None
    room.pending_shoe = shoe
    room.message = f"{room.player_by_seat(cutter_seat).name} cuts the deck; {room.player_by_seat(dealer_seat).name} deals"


def cut_deck(room: GameRoom, player_id: str, position: int) -> None:
    if room.phase != "cutting":
        raise GameRuleError("The deck is not waiting to be cut")
    if player_id != room.cutter_player_id:
        raise GameRuleError("Only the designated cutter can cut the deck")
    if position < 1 or position > len(room.pending_shoe):
        raise GameRuleError(f"Cut position must be between 1 and {len(room.pending_shoe)}")

    room.pending_shoe = room.pending_shoe[position:] + room.pending_shoe[:position]
    room.cut_position = position
    deal_pending_shoe(room)


def deal_pending_shoe(room: GameRoom) -> None:
    shoe = room.pending_shoe
    needed = len(room.players) * room.round_number
    deal_order = [
        room.player_by_seat((room.leader_seat + offset) % len(room.players))
        for offset in range(len(room.players))
    ]

    # Deal one card at a time, preserving random shoe order.
    cursor = 0
    for _ in range(room.round_number):
        for player in deal_order:
            player.hand.append(shoe[cursor])
            cursor += 1

    for player in room.players:
        player.hand.sort(key=card_sort_key)

    room.pending_shoe = []
    room.phase = "bidding"
    room.turn_seat = room.leader_seat
    room.message = f"Round {room.round_number}: submit your {'public estimate' if room.mode == 'teams' else 'Guess'}"


def advance_bot_cut(room: GameRoom) -> None:
    if room.phase != "cutting" or room.cutter_player_id is None:
        return
    cutter = room.player_by_id(room.cutter_player_id)
    if cutter.is_bot:
        cut_deck(room, cutter.id, random.randint(1, len(room.pending_shoe)))


def submit_bid(room: GameRoom, player_id: str, bid: int) -> None:
    if room.phase != "bidding":
        raise GameRuleError("Bidding is not open")
    player = room.player_by_id(player_id)
    if player.seat != room.turn_seat:
        raise GameRuleError(f"Waiting for {room.player_by_seat(room.turn_seat).name} to submit a Guess")
    if player.bid is not None:
        raise GameRuleError("Your estimate has already been submitted" if room.mode == "teams" else "Your Guess has already been submitted")
    if bid < 0 or bid > room.round_number:
        raise GameRuleError(f"Guess must be between 0 and {room.round_number}")
    player.bid = bid

    if all(p.bid is not None for p in room.players):
        if room.mode == "teams":
            room.bidding_stage = "teams"
            room.team_turn_index = 0
            team = room.team_bid_order[0]
            captain = room.player_by_id(room.team_captains[team])
            room.message = f"All estimates are visible. Team {team} captain {captain.name} submits the combined bid."
        else:
            room.phase = "playing"
            room.turn_seat = room.leader_seat
            room.message = f"All guesses are in. {room.player_by_seat(room.turn_seat).name} leads."
    else:
        next_seat = (room.turn_seat + 1) % len(room.players)
        while room.player_by_seat(next_seat).bid is not None:
            next_seat = (next_seat + 1) % len(room.players)
        room.turn_seat = next_seat
        room.message = f"Waiting for {room.player_by_seat(room.turn_seat).name} to submit a Guess"


def submit_team_bid(room: GameRoom, player_id: str, bid: int) -> None:
    if room.phase != "bidding" or room.mode != "teams" or room.bidding_stage != "teams":
        raise GameRuleError("Combined team bidding is not open")
    team = room.team_bid_order[room.team_turn_index]
    if room.team_captains.get(team) != player_id:
        captain = room.player_by_id(room.team_captains[team])
        raise GameRuleError(f"Waiting for Team {team} captain {captain.name}")
    if bid < 0 or bid > room.round_number:
        raise GameRuleError(f"Team bid must be between 0 and {room.round_number}")
    room.team_bids[team] = bid
    room.team_turn_index += 1
    if room.team_turn_index >= len(room.team_bid_order):
        room.phase = "playing"
        room.turn_seat = room.leader_seat
        room.message = f"All team bids are locked. {room.player_by_seat(room.turn_seat).name} leads."
    else:
        next_team = room.team_bid_order[room.team_turn_index]
        captain = room.player_by_id(room.team_captains[next_team])
        room.message = f"Team {next_team} captain {captain.name} submits the combined bid."


def card_sort_key(card: Card) -> tuple[int, int, int]:
    if card.is_joker:
        return (5, 99, card.deck_index)
    suit_order = {"clubs": 1, "diamonds": 2, "hearts": 3, "spades": 4}
    assert card.suit is not None and card.rank is not None
    return (suit_order[card.suit], card.rank, card.deck_index)


def led_suit(room: GameRoom) -> str | None:
    if not room.current_trick:
        return None
    # If Joker leads, the trick intentionally has no required suit.
    if room.current_trick[0].card.is_joker:
        return None
    return room.current_trick[0].card.suit


def legal_card_ids(room: GameRoom, player_id: str) -> set[str]:
    player = room.player_by_id(player_id)
    if room.phase != "playing" or room.awaiting_next_trick or player.seat != room.turn_seat:
        return set()

    required = led_suit(room)
    if required is None:
        return {c.id for c in player.hand}

    has_required_normal = any((not c.is_joker and c.suit == required) for c in player.hand)
    if not has_required_normal:
        return {c.id for c in player.hand}

    # Joker is always legal; otherwise must follow suit.
    return {c.id for c in player.hand if c.is_joker or c.suit == required}


def play_card(room: GameRoom, player_id: str, card_id: str) -> dict | None:
    if room.phase != "playing":
        raise GameRuleError("Cards cannot be played right now")
    if room.awaiting_next_trick:
        raise GameRuleError("Review the completed trick before continuing")
    player = room.player_by_id(player_id)
    if player.seat != room.turn_seat:
        raise GameRuleError("It is not your turn")

    card = next((c for c in player.hand if c.id == card_id), None)
    if card is None:
        raise GameRuleError("That card is not in your hand")
    if card.id not in legal_card_ids(room, player_id):
        raise GameRuleError("You must follow the led suit. The Joker is always allowed.")

    player.hand.remove(card)
    room.current_trick.append(TrickPlay(player_id=player_id, card=card))

    if len(room.current_trick) < len(room.players):
        room.turn_seat = (room.turn_seat + 1) % len(room.players)
        room.message = f"{room.player_by_seat(room.turn_seat).name}'s turn"
        return None

    winner_id = determine_trick_winner(room.current_trick)
    winner = room.player_by_id(winner_id)
    winner.tricks += 1
    winner.contribution_tricks += 1
    room.completed_tricks += 1
    room.last_trick_winner_id = winner_id
    room.last_trick_cards = [
        {"playerId": play.player_id, "card": play.card.public()} for play in room.current_trick
    ]
    room.current_trick = []

    if room.completed_tricks >= room.round_number:
        summary = finish_round(room)
        return {"trickWinnerId": winner_id, "roundSummary": summary}

    room.leader_seat = winner.seat
    room.turn_seat = winner.seat
    room.awaiting_next_trick = True
    room.message = f"{winner.name} won the trick. Review the cards, then continue."
    return {"trickWinnerId": winner_id}


def continue_after_trick(room: GameRoom) -> None:
    if room.phase != "playing" or not room.awaiting_next_trick:
        raise GameRuleError("There is no completed trick waiting to continue")
    room.awaiting_next_trick = False
    room.message = f"{room.player_by_seat(room.turn_seat).name} leads the next trick"


def determine_trick_winner(plays: list[TrickPlay]) -> str:
    if not plays:
        raise GameRuleError("Cannot score an empty trick")

    # Exactly one Joker exists in the shoe. If present, it wins unconditionally.
    for play in plays:
        if play.card.is_joker:
            return play.player_id

    first = plays[0].card
    if first.is_joker:
        return plays[0].player_id
    led = first.suit

    spades = [play for play in plays if play.card.suit == "spades"]
    candidates = spades if spades else [play for play in plays if play.card.suit == led]

    # Search from the end so the last identical highest card played wins a tie.
    winner = max(reversed(candidates), key=lambda p: int(p.card.rank or 0))
    return winner.player_id


def score_round(bid: int, tricks: int) -> tuple[int, int]:
    if tricks >= bid:
        bags = tricks - bid
        return (bid * 10) + bags, bags
    return -(bid * 10) + tricks, 0


def finish_round(room: GameRoom) -> list[dict]:
    if room.mode == "teams":
        return finish_team_round(room)
    rows: list[dict] = []
    for player in room.players:
        assert player.bid is not None
        score_before = player.total_score
        bags_before = player.bags
        base_score, new_bags = score_round(player.bid, player.tricks)
        player.gross_score += base_score
        player.total_bags += new_bags
        player.total_score += base_score
        player.bags += new_bags
        score_after_round = player.total_score
        bags_before_penalty = player.bags

        penalty = 0
        while player.bags >= 5:
            player.bags -= 5
            player.total_score -= 50
            penalty -= 50

        rows.append(
            {
                "playerId": player.id,
                "name": player.name,
                "team": player.team,
                "bid": player.bid,
                "won": player.tricks,
                "scoreBefore": score_before,
                "baseScore": base_score,
                "scoreAfterRound": score_after_round,
                "bagsBefore": bags_before,
                "newBags": new_bags,
                "bagsBeforePenalty": bags_before_penalty,
                "bagPenalty": penalty,
                "remainingBags": player.bags,
                "totalScore": player.total_score,
            }
        )

    room.round_history.append(RoundSummary(round_number=room.round_number, rows=rows))
    if room.round_number == 13:
        room.phase = "finished"
        room.message = "Game complete — final results"
    else:
        room.phase = "round_complete"
        room.message = f"Round {room.round_number} complete"
    return rows


def finish_team_round(room: GameRoom) -> list[dict]:
    rows: list[dict] = []
    for team in room.team_bid_order:
        bid = room.team_bids.get(team)
        assert bid is not None
        tricks = sum(player.tricks for player in room.players if player.team == team)
        score_before = room.team_scores.get(team, 0)
        bags_before = room.team_bags.get(team, 0)
        base_score, new_bags = score_round(bid, tricks)
        room.team_gross_scores[team] = room.team_gross_scores.get(team, 0) + base_score
        room.team_total_bags[team] = room.team_total_bags.get(team, 0) + new_bags
        room.team_scores[team] = score_before + base_score
        room.team_bags[team] = bags_before + new_bags
        score_after_round = room.team_scores[team]
        bags_before_penalty = room.team_bags[team]
        penalty = 0
        while room.team_bags[team] >= 5:
            room.team_bags[team] -= 5
            room.team_scores[team] -= 50
            penalty -= 50
        rows.append({
            "playerId": f"team-{team}", "name": f"Team {team}", "team": team,
            "bid": bid, "won": tricks, "scoreBefore": score_before,
            "baseScore": base_score, "scoreAfterRound": score_after_round,
            "bagsBefore": bags_before, "newBags": new_bags,
            "bagsBeforePenalty": bags_before_penalty, "bagPenalty": penalty,
            "remainingBags": room.team_bags[team], "totalScore": room.team_scores[team],
        })
    room.round_history.append(RoundSummary(round_number=room.round_number, rows=rows))
    if room.round_number == 13:
        room.phase = "finished"
        room.message = "Game complete — final team results"
    else:
        room.phase = "round_complete"
        room.message = f"Round {room.round_number} complete"
    return rows


def next_round(room: GameRoom, rng: random.Random | None = None) -> None:
    if room.phase != "round_complete":
        raise GameRuleError("The current round is not complete")
    start_round(room, room.round_number + 1, rng)


def team_totals(room: GameRoom) -> list[dict]:
    if room.mode != "teams":
        return []
    return [
        {"team": team, "score": score, "grossScore": room.team_gross_scores.get(team, 0),
         "bags": room.team_bags.get(team, 0), "totalBags": room.team_total_bags.get(team, 0),
         "bid": room.team_bids.get(team),
         "tricks": sum(player.tricks for player in room.players if player.team == team),
         "captainId": room.team_captains.get(team)}
        for team, score in sorted(room.team_scores.items(), key=lambda item: item[1], reverse=True)
    ]
