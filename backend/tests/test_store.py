from app.store import RoomStore


def test_player_can_rejoin_active_game_with_same_name_and_code():
    store = RoomStore()
    room, original = store.create_room("Rahul", 2, "individual")
    room.phase = "playing"
    original.connected = False

    returned_room, returned_player = store.join_room(room.code, "rahul", room.rejoin_pin)

    assert returned_room is room
    assert returned_player.id == original.id
    assert returned_player.connected is True


def test_new_name_cannot_join_after_game_starts():
    store = RoomStore()
    room, _ = store.create_room("Rahul", 2, "individual")
    room.phase = "playing"

    try:
        store.join_room(room.code, "Someone Else")
    except ValueError as exc:
        assert "same player name" in str(exc)
    else:
        raise AssertionError("Expected an active room to reject a new player")


def test_duplicate_name_requires_the_game_rejoin_pin():
    store = RoomStore()
    room, sam = store.create_room("Sam", 3, "individual")

    for attempted_pin in (None, "000000"):
        try:
            store.join_room(room.code, "SAM", attempted_pin)
        except ValueError as exc:
            assert "already taken" in str(exc)
        else:
            raise AssertionError("Expected duplicate name to require the game PIN")

    _, returned = store.join_room(room.code, "sam", room.rejoin_pin)
    assert returned.id == sam.id


def test_every_player_uses_the_same_game_rejoin_pin():
    store = RoomStore()
    room, _ = store.create_room("Rahul", 3, "individual")
    _, sam = store.join_room(room.code, "Sam")
    room.phase = "playing"
    sam.connected = False

    _, returned = store.join_room(room.code, "sam", room.rejoin_pin)

    assert returned.id == sam.id


def test_players_are_balanced_across_the_selected_number_of_teams():
    store = RoomStore()
    room, _ = store.create_room("Player 1", 6, "teams", team_count=3)
    for number in range(2, 7):
        store.join_room(room.code, f"Player {number}")

    assert [player.team for player in room.players] == ["A", "B", "C", "A", "B", "C"]


def test_computer_players_use_the_same_team_balancing_rule():
    store = RoomStore()
    room, _ = store.create_room("Player 1", 8, "teams", team_count=4)

    store.fill_with_bots(room)

    assert [player.team for player in room.players] == ["A", "B", "C", "D", "A", "B", "C", "D"]


def test_host_can_edit_assignments_without_automatic_swaps_and_then_lock():
    store = RoomStore()
    room, player_1 = store.create_room("Player 1", 4, "teams", team_count=2)
    _, player_2 = store.join_room(room.code, "Player 2")
    _, player_3 = store.join_room(room.code, "Player 3")
    _, player_4 = store.join_room(room.code, "Player 4")

    store.assign_team(room, player_1.id, "B")

    assert player_1.team == "B"
    assert player_4.team == "B"
    assert player_2.team == "B"
    assert player_3.team == "A"

    try:
        store.lock_teams(room)
    except ValueError as exc:
        assert "Team B: 3/2" in str(exc)
    else:
        raise AssertionError("Expected an overfilled team to be rejected")

    store.assign_team(room, player_4.id, "A")
    store.lock_teams(room)
    assert room.teams_locked is True


def test_host_can_change_team_count_in_the_lobby():
    store = RoomStore()
    room, _ = store.create_room("Player 1", 8, "teams", team_count=2)
    for number in range(2, 9):
        store.join_room(room.code, f"Player {number}")

    store.set_team_count(room, 4)

    assert room.team_count == 4
    assert [player.team for player in room.players] == ["A", "B", "C", "D", "A", "B", "C", "D"]
    assert room.teams_locked is False


def test_team_assignment_is_rejected_after_game_starts():
    store = RoomStore()
    room, player = store.create_room("Player 1", 4, "teams", team_count=2)
    room.phase = "drawing"

    try:
        store.assign_team(room, player.id, "B")
    except ValueError as exc:
        assert "before the game starts" in str(exc)
    else:
        raise AssertionError("Expected team assignment to be locked after the lobby")


def test_locked_teams_reject_assignment_and_team_count_changes():
    store = RoomStore()
    room, player = store.create_room("Player 1", 8, "teams", team_count=2)
    store.lock_teams(room)

    for change in (
        lambda: store.assign_team(room, player.id, "B"),
        lambda: store.set_team_count(room, 4),
    ):
        try:
            change()
        except ValueError as exc:
            assert "Unlock" in str(exc)
        else:
            raise AssertionError("Expected locked team setup to reject edits")


def test_partial_lobby_can_lock_and_bots_fill_every_team_to_capacity():
    store = RoomStore()
    room, _ = store.create_room("Player 1", 12, "teams", team_count=4)
    store.join_room(room.code, "Player 2")
    store.join_room(room.code, "Player 3")
    store.lock_teams(room)

    store.fill_with_bots(room)

    assert {team: sum(player.team == team for player in room.players) for team in "ABCD"} == {"A": 3, "B": 3, "C": 3, "D": 3}
