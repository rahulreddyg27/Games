from fastapi.testclient import TestClient

from app.main import app
from app.store import store


def test_admin_key_protects_game_list_and_can_delete_room():
    room, _ = store.create_room("Admin Test Host", 2, "individual")

    with TestClient(app) as client:
        denied = client.post("/admin/games", json={"adminKey": "wrong-key"})
        assert denied.status_code == 403

        listed = client.post("/admin/games", json={"adminKey": "Qwerty@123"})
        assert listed.status_code == 200
        assert any(game["code"] == room.code and game["status"] == "open" for game in listed.json()["games"])

        deleted = client.request(
            "DELETE",
            f"/admin/games/{room.code}",
            json={"adminKey": "Qwerty@123"},
        )
        assert deleted.status_code == 200
        assert room.code not in store.rooms
