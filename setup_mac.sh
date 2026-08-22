#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

for command in node npm; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command"
    echo "Install Python 3.11+ and Node.js 20+, then run this script again."
    exit 1
  fi
done

PYTHON_BIN="$(command -v python3.11 || command -v python3 || true)"
if [ -z "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
  echo "Python 3.11+ is required. Install it with: brew install python@3.11"
  exit 1
fi

echo "Setting up backend..."
cd "$ROOT/backend"
"$PYTHON_BIN" -m venv --clear .venv
source .venv/bin/activate
pip install -r requirements.txt

echo "Setting up frontend..."
cd "$ROOT/frontend"
npm install

echo
echo "Setup complete. Run: ./run_local.sh"
