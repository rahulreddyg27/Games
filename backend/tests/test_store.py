from app.store import RoomStore


def test_player_can_rejoin_active_game_with_same_name_and_code():
    store = RoomStore()
    room, original = store.create_room("Rahul", 2, "individual")
    room.phase = "playing"
    original.connected = False

    returned_room, returned_player = store.join_room(room.code, "rahul", original.rejoin_pin)

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


def test_duplicate_name_requires_the_original_rejoin_pin():
    store = RoomStore()
    room, sam = store.create_room("Sam", 3, "individual")

    for attempted_pin in (None, "000000"):
        try:
            store.join_room(room.code, "SAM", attempted_pin)
        except ValueError as exc:
            assert "already taken" in str(exc)
        else:
            raise AssertionError("Expected duplicate name to require the original PIN")

    _, returned = store.join_room(room.code, "sam", sam.rejoin_pin)
    assert returned.id == sam.id
