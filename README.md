# Friends Spades — Local Multiplayer MVP

A local-first multiplayer implementation of the custom Spades game described in this project.

## Implemented rules

- 2–16 players, with computer players filling empty seats when the host starts.
- 13 rounds.
- Round 1 deals 1 card/player, Round 2 deals 2, ... Round 13 deals 13.
- Rooms with 2–3 players can choose 1 deck (53 cards including Joker) or 2 decks (105 cards including Joker).
- Rooms with 4–7 players always use 2 decks + 1 Joker.
- Rooms with 8–12 players always use 3 decks + 1 Joker (157 cards).
- Rooms with 13–16 players always use 4 decks + 1 Joker (209 cards).
- Before every round, the designated cutter cuts the shuffled shoe before the dealer deals.
- Up to 105 cut positions appear as facedown cards; positions above 105 appear in a dropdown.
- Cards are dealt one at a time beginning with that round's rotating first recipient.
- Exactly **one Joker** is added to the shoe.
- Before Round 1, each player picks one unique facedown card from a separate 52-card deck (no Joker).
- Drawn cards are ranked highest to lowest by rank; suit is considered only for equal ranks, using ♠, ♥, ♦, ♣ from highest to lowest.
- The lowest draw bids first in Round 1 and the highest draw bids last.
- Joker is a **wild card**:
  - It may be played on any turn, even when the player has the led suit.
  - It automatically wins the trick.
  - If Joker is led, that trick has no required suit; everyone may play any card.
- Normal cards must follow the led suit when possible.
- If a player cannot follow suit, they may play any normal card.
- Spades are trump over non-spade led suits.
- If duplicate decks create identical highest cards, the **last identical highest card played wins the tie**.
- Bid/Guess scoring:
  - If `won >= bid`: `round_score = bid * 10 + (won - bid)`
  - If `won < bid`: `round_score = -(bid * 10) + won`
  - Extra tricks above bid are bags.
- Every 5 accumulated bags applies **-50 points** and removes 5 bags.
- After round 13, the highest individual score wins in Individual mode.
- In Team mode, team totals are also calculated and the highest team wins.

## Stack

- Frontend: React + TypeScript + Vite
- Backend: Python + FastAPI
- Multiplayer: WebSockets
- Persistence: SQLite (completed game snapshots)

## Run on a Mac

### Prerequisites

Install:

- Python 3.11+
- Node.js 20+

You can verify:

```bash
python3 --version
node --version
npm --version
```

### One-command setup + run

From the project root:

```bash
chmod +x setup_mac.sh run_local.sh
./setup_mac.sh
./run_local.sh
```

Open:

```text
http://localhost:5173
```

### Admin game cleanup

Open the **Admin** screen from the home page and enter the temporary admin key `Qwerty@123` to list or delete active in-memory rooms and completed SQLite snapshots. This key is hardcoded in the backend for early testing and must be replaced with secret-based configuration before wider use.

The current admin list is instance-local: Azure restarts remove in-memory games and ephemeral SQLite data, and multiple replicas do not share a game list.

The API runs on:

```text
http://localhost:8000
```

API docs:

```text
http://localhost:8000/docs
```

### Test with multiple players on the same Mac

Open multiple browser windows/private windows and join the same room using different player names.

### Test from iPhones on the same Wi-Fi

1. Start the app using `./run_local.sh`.
2. Find your Mac's local IP:

```bash
ipconfig getifaddr en0
```

3. If it returns something like `192.168.1.50`, your friends on the same Wi-Fi can open:

```text
http://192.168.1.50:5173
```

The frontend automatically points its API/WebSocket calls to the same Mac hostname on port 8000.

> macOS Firewall may ask whether Python/Node can accept incoming connections. Allow them for local testing.

## Manual run

Backend:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend (another Terminal):

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

## Run backend tests

```bash
cd backend
source .venv/bin/activate
pytest -q
```

## Current MVP scope

Included:

- Create private room.
- Solo play against computer players.
- Join by room code.
- Host start control.
- Individual or two-team mode.
- Automatic card dealing by round.
- Hidden bidding until everyone bids.
- Server-authoritative card validation.
- Player-controlled deck cutting before every round.
- Follow-suit validation.
- Spade trump logic.
- Wild Joker logic.
- Automatic trick winner.
- Automatic trick counts.
- Automatic score and bag penalties.
- 13-round progression.
- Final individual/team ranking.
- WebSocket live synchronization.
- Browser refresh/reconnect using local session data.
- Case-insensitive unique player names within a room and one shared private 6-digit rejoin PIN per game.
- Host-controlled room closure that removes active memory and completed SQLite data.

Not yet included (good next phase):

- Login/accounts.
- Cloud deployment.
- Voice/video chat.
- Spectators.
- Custom team assignment UI.
- Animations/sounds.
- Native App Store app/PWA install flow.
- Timers/AFK handling.
- Production-grade distributed game-state storage.
- Round 13 strategy suggestions (tracked in `TODO.md`).
- Combined team bidding (tracked in `TODO.md`; final captain/visibility rules pending).

## Important design choice

The backend is authoritative. The browser never decides whether a move is legal, who won a trick, or what score to award. This prevents simple browser-side cheating and keeps all players synchronized.
