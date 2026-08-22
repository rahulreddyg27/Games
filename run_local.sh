#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACK_PID=""
FRONT_PID=""

if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "Backend virtual environment not found. Run ./setup_mac.sh first."
  exit 1
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Frontend dependencies not found. Run ./setup_mac.sh first."
  exit 1
fi

cleanup() {
  echo
  echo "Stopping local servers..."
  [ -n "$BACK_PID" ] && kill "$BACK_PID" 2>/dev/null || true
  [ -n "$FRONT_PID" ] && kill "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

cd "$ROOT/backend"
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACK_PID=$!

cd "$ROOT/frontend"
npm run dev -- --host 0.0.0.0 &
FRONT_PID=$!

echo
echo "Friends Spades is starting:"
echo "  Web:      http://localhost:5173"
echo "  API docs: http://localhost:8000/docs"
echo
echo "Press Ctrl+C to stop both servers."
wait
