#!/usr/bin/env bash
# Quick start for Linux and macOS: installs uv (which brings Python) and Bun if missing, installs the
# backend and frontend packages from their lockfiles, then runs both. Ctrl+C stops both.
# PORT (frontend, default 3000) and BACKEND_PORT (default 8000) change the ports.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/0.13.7/install.sh | sh
  export PATH="${XDG_BIN_HOME:-$HOME/.local/bin}:$PATH"
fi
if ! command -v bun >/dev/null; then
  echo "Installing Bun..."
  curl -fsSL https://bun.sh/install | bash -s bun-v1.4.4
  export PATH="${BUN_INSTALL:-$HOME/.bun}/bin:$PATH"
fi

uv sync --locked --directory backend # also downloads Python 3.14 if it is not there
(cd frontend && bun install --frozen-lockfile)

BACKEND_PORT="${BACKEND_PORT:-8000}"
export API_URL="http://127.0.0.1:$BACKEND_PORT"
uv run --directory backend uvicorn app.main:create_app --factory --port "$BACKEND_PORT" &
backend=$!
trap 'kill "$backend" 2>/dev/null || true' EXIT INT TERM
cd frontend && bun run dev
