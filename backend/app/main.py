from __future__ import annotations

from contextlib import asynccontextmanager
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .game_engine import (
    GameRuleError,
    advance_bots,
    advance_bot_draws,
    advance_bot_cut,
    cut_deck,
    continue_after_trick,
    legal_card_ids,
    next_round,
    play_card,
    pick_draw_card,
    start_game,
    start_card_draw,
    submit_bid,
    team_totals,
)
from .models import GameRoom
from .persistence import (
    delete_all_completed_games,
    delete_completed_game,
    init_db,
    list_completed_games,
    save_completed_game,
)
from .store import store

ADMIN_KEY = "Qwerty@123"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Friends Spades API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    maxPlayers: int = Field(default=4, ge=2, le=16)
    mode: str = Field(default="individual", pattern="^(individual|teams)$")
    deckCount: int = Field(default=2, ge=1, le=4)


class JoinRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    rejoinPin: Optional[str] = Field(default=None, pattern="^[0-9]{6}$")


class CloseRoomRequest(BaseModel):
    name: str = Field(min_length=1, max_length=24)
    rejoinPin: str = Field(pattern="^[0-9]{6}$")


class AdminRequest(BaseModel):
    adminKey: str = Field(min_length=1, max_length=256)


class AdminCleanupRequest(AdminRequest):
    scope: str = Field(pattern="^(active|completed|all)$")


def verify_admin(admin_key: str) -> None:
    if not secrets.compare_digest(admin_key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail="Invalid admin key")


async def remove_active_room(code: str, reason: str) -> bool:
    code = code.upper()
    if code not in store.rooms:
        return False
    for websocket in list(store.connections[code].values()):
        try:
            await websocket.close(code=4400, reason=reason)
        except Exception:
            pass
    store.connections.pop(code, None)
    store.rooms.pop(code, None)
    return True


def serialize_room(room: GameRoom, viewer_id: str | None = None) -> dict:
    current_player = None
    if room.players and room.phase in ("bidding", "playing"):
        try:
            current_player = room.player_by_seat(room.turn_seat).id
        except KeyError:
            current_player = None
    elif room.phase == "cutting":
        current_player = room.cutter_player_id

    players = []
    for p in sorted(room.players, key=lambda item: item.seat):
        players.append(
            {
                "id": p.id,
                "name": p.name,
                "seat": p.seat,
                "team": p.team,
                "connected": p.connected,
                "isBot": p.is_bot,
                "bid": p.bid,
                "bidSubmitted": p.bid is not None,
                "tricks": p.tricks,
                "totalScore": p.total_score,
                "grossScore": p.gross_score,
                "bags": p.bags,
                "totalBags": p.total_bags,
                "cardCount": len(p.hand),
                "drawCard": p.draw_card.public() if room.phase == "draw_complete" and p.draw_card else None,
                "drawSubmitted": p.draw_card is not None,
            }
        )

    hand = []
    legal = []
    if viewer_id:
        try:
            viewer = room.player_by_id(viewer_id)
            hand = [card.public() for card in viewer.hand]
            legal = list(legal_card_ids(room, viewer_id))
        except KeyError:
            pass

    individual_ranking = [
        {"playerId": p.id, "name": p.name, "team": p.team, "score": p.total_score, "bags": p.bags}
        for p in sorted(room.players, key=lambda item: item.total_score, reverse=True)
    ]

    return {
        "code": room.code,
        "hostPlayerId": room.host_player_id,
        "maxPlayers": room.max_players,
        "deckCount": room.deck_count,
        "mode": room.mode,
        "phase": room.phase,
        "roundNumber": room.round_number,
        "leaderSeat": room.leader_seat,
        "message": room.message,
        "players": players,
        "currentPlayerId": current_player,
        "currentTrick": [
            {"playerId": play.player_id, "card": play.card.public()} for play in room.current_trick
        ],
        "lastTrickWinnerId": room.last_trick_winner_id,
        "lastTrickCards": room.last_trick_cards,
        "drawChoices": [card.id for card in room.draw_deck] if room.phase == "drawing" else [],
        "cutCardCount": len(room.pending_shoe) if room.phase == "cutting" else 0,
        "cutterPlayerId": room.cutter_player_id,
        "dealerPlayerId": room.dealer_player_id,
        "cutPosition": room.cut_position,
        "completedTricks": room.completed_tricks,
        "awaitingNextTrick": room.awaiting_next_trick,
        "hand": hand,
        "legalCardIds": legal,
        "roundHistory": [
            {"roundNumber": summary.round_number, "rows": summary.rows} for summary in room.round_history
        ],
        "individualRanking": individual_ranking,
        "teamRanking": team_totals(room),
    }


async def broadcast(room: GameRoom) -> None:
    dead: list[str] = []
    for player_id, ws in list(store.connections[room.code].items()):
        try:
            await ws.send_json({"type": "state", "state": serialize_room(room, player_id)})
        except Exception:
            dead.append(player_id)
    for player_id in dead:
        store.connections[room.code].pop(player_id, None)
        try:
            room.player_by_id(player_id).connected = False
        except KeyError:
            pass


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/rooms")
async def create_room(body: CreateRoomRequest) -> dict:
    if body.mode == "teams" and (body.maxPlayers < 4 or body.maxPlayers % 2 != 0):
        raise HTTPException(status_code=400, detail="Team mode requires an even player count from 4 through 16")
    if body.maxPlayers >= 13:
        deck_count = 4
    elif body.maxPlayers >= 8:
        deck_count = 3
    elif body.maxPlayers >= 4:
        deck_count = 2
    else:
        deck_count = min(body.deckCount, 2)
    room, player = store.create_room(body.name, body.maxPlayers, body.mode, deck_count)
    return {"roomCode": room.code, "playerId": player.id, "rejoinPin": player.rejoin_pin, "state": serialize_room(room, player.id)}


@app.post("/rooms/{code}/join")
async def join_room(code: str, body: JoinRoomRequest) -> dict:
    try:
        room, player = store.join_room(code, body.name, body.rejoinPin)
    except KeyError:
        raise HTTPException(status_code=404, detail="Room not found")
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await broadcast(room)
    return {"roomCode": room.code, "playerId": player.id, "rejoinPin": player.rejoin_pin, "state": serialize_room(room, player.id)}


@app.delete("/rooms/{code}")
async def close_room(code: str, body: CloseRoomRequest) -> dict:
    code = code.upper()
    room = store.rooms.get(code)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    host = room.player_by_id(room.host_player_id)
    if host.name.casefold() != body.name.strip().casefold() or host.rejoin_pin != body.rejoinPin:
        raise HTTPException(status_code=403, detail="Host name or rejoin PIN is incorrect")
    for websocket in list(store.connections[code].values()):
        await websocket.close(code=4400, reason="Game closed by host")
    store.connections.pop(code, None)
    store.rooms.pop(code, None)
    delete_completed_game(code)
    return {"closed": True}


@app.post("/admin/games")
def admin_list_games(body: AdminRequest) -> dict:
    verify_admin(body.adminKey)
    completed = {game["code"]: game for game in list_completed_games()}
    games = []
    for room in store.rooms.values():
        host = room.player_by_id(room.host_player_id)
        if room.phase == "finished":
            status = "completed"
        elif room.phase == "lobby":
            status = "open"
        else:
            status = "in_progress"
        stored = completed.pop(room.code, None)
        games.append(
            {
                "code": room.code,
                "status": status,
                "hostName": host.name,
                "playerCount": len([player for player in room.players if not player.is_bot]),
                "botCount": len([player for player in room.players if player.is_bot]),
                "connectedCount": len([player for player in room.players if player.connected and not player.is_bot]),
                "roundNumber": room.round_number,
                "finishedAt": stored.get("finishedAt") if stored else None,
                "storage": "memory + sqlite" if stored else "memory",
            }
        )
    games.extend(completed.values())
    status_order = {"in_progress": 0, "open": 1, "completed": 2}
    games.sort(key=lambda game: (status_order.get(game["status"], 9), game["code"]))
    return {"games": games}


@app.delete("/admin/games/{code}")
async def admin_delete_game(code: str, body: AdminRequest) -> dict:
    verify_admin(body.adminKey)
    code = code.upper()
    removed_active = await remove_active_room(code, "Game closed by administrator")
    completed_codes = {game["code"] for game in list_completed_games()}
    removed_completed = code in completed_codes
    delete_completed_game(code)
    if not removed_active and not removed_completed:
        raise HTTPException(status_code=404, detail="Game not found")
    return {"closed": True}


@app.post("/admin/games/cleanup")
async def admin_cleanup_games(body: AdminCleanupRequest) -> dict:
    verify_admin(body.adminKey)
    active_count = 0
    completed_count = 0
    if body.scope in ("active", "all"):
        for code in list(store.rooms):
            if await remove_active_room(code, "Games cleaned up by administrator"):
                active_count += 1
    elif body.scope == "completed":
        for code, room in list(store.rooms.items()):
            if room.phase == "finished" and await remove_active_room(code, "Completed games cleaned up by administrator"):
                active_count += 1
    if body.scope in ("completed", "all"):
        completed_count = delete_all_completed_games()
    return {"activeClosed": active_count, "completedDeleted": completed_count}


@app.get("/rooms/{code}/players/{player_id}")
def resume_room(code: str, player_id: str) -> dict:
    room = store.rooms.get(code.upper())
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    try:
        room.player_by_id(player_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Player not found")
    return {"state": serialize_room(room, player_id)}


@app.websocket("/ws/{code}/{player_id}")
async def room_socket(websocket: WebSocket, code: str, player_id: str) -> None:
    code = code.upper()
    room = store.rooms.get(code)
    if room is None:
        await websocket.accept()
        await websocket.close(code=4404)
        return
    try:
        player = room.player_by_id(player_id)
    except KeyError:
        await websocket.accept()
        await websocket.close(code=4404)
        return

    await websocket.accept()
    store.connections[code][player_id] = websocket
    player.connected = True
    await broadcast(room)

    try:
        while True:
            payload = await websocket.receive_json()
            action = payload.get("action")
            try:
                if action == "start_game":
                    if player_id != room.host_player_id:
                        raise GameRuleError("Only the host can start the game")
                    store.fill_with_bots(room)
                    start_card_draw(room)
                    advance_bot_draws(room)
                elif action == "pick_draw_card":
                    pick_draw_card(room, player_id, str(payload.get("cardId")))
                    advance_bot_draws(room)
                elif action == "confirm_order":
                    if player_id != room.host_player_id:
                        raise GameRuleError("Only the host can confirm the player order")
                    start_game(room)
                    advance_bot_cut(room)
                    advance_bots(room)
                elif action == "cut_deck":
                    cut_deck(room, player_id, int(payload.get("position")))
                    advance_bots(room)
                elif action == "submit_bid":
                    submit_bid(room, player_id, int(payload.get("bid")))
                    advance_bots(room)
                elif action == "play_card":
                    play_card(room, player_id, str(payload.get("cardId")))
                    advance_bots(room)
                    if room.phase == "finished":
                        save_completed_game(room.code, serialize_room(room, None))
                elif action == "continue_trick":
                    continue_after_trick(room)
                    advance_bots(room)
                elif action == "next_round":
                    if player_id != room.host_player_id:
                        raise GameRuleError("Only the host can start the next round")
                    next_round(room)
                    advance_bot_cut(room)
                    advance_bots(room)
                elif action == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                else:
                    raise GameRuleError("Unknown action")
                await broadcast(room)
            except (GameRuleError, ValueError, TypeError) as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
    except WebSocketDisconnect:
        store.connections[code].pop(player_id, None)
        player.connected = False
        await broadcast(room)
