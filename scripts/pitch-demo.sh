#!/usr/bin/env bash
# Pitch demo — one command: backend (CPU-only) + frontend + browser
# i5 / 16GB / No GPU / Venue internet = Yes (default per README)
# Usage: ./scripts/pitch-demo.sh [--no-browser] [--skip-install]
# Requires: python3, .venv or venv with requirements.txt, node/npm, curl, jq (optional)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
BACKEND_LOG="/tmp/uvicorn.log"
FRONTEND_LOG="/tmp/vite.log"
NO_BROWSER=false
SKIP_INSTALL=false

for arg in "$@"; do
  case "$arg" in
    --no-browser) NO_BROWSER=true ;;
    --skip-install) SKIP_INSTALL=true ;;
    --help|-h) echo "Usage: $0 [--no-browser] [--skip-install]"; exit 0 ;;
  esac
done

# --- 1. Env (CPU-only is default per backend/config.py:36) ---
export SATQUERY_BASE_MODEL="${SATQUERY_BASE_MODEL:-Qwen/Qwen2-VL-2B-Instruct}"
export SATQUERY_ADAPTER_PATH="${SATQUERY_ADAPTER_PATH:-imadityasarkar/satquery-phase2-vrsbench}"
export SATQUERY_FORCE_CPU="${SATQUERY_FORCE_CPU:-1}"
export SATQUERY_MAX_NEW_TOKENS="${SATQUERY_MAX_NEW_TOKENS:-256}"
# HF_TOKEN optional: export HF_TOKEN=hf_xxx if adapter is gated
if [[ -n "${HF_TOKEN:-}" ]]; then
  export HF_TOKEN
fi

# Prefer .venv, fallback to venv
if [[ -d "$ROOT/.venv" ]]; then
  VENV="$ROOT/.venv"
elif [[ -d "$ROOT/venv" ]]; then
  VENV="$ROOT/venv"
else
  VENV=""
fi
if [[ -n "$VENV" && -f "$VENV/bin/activate" ]]; then
  # shellcheck disable=SC1090
  source "$VENV/bin/activate"
  echo "✓ venv: $VENV"
else
  echo "⚠ no .venv found — using system python ($ROOT/.venv not present)"
fi

# --- 2. Install check (skip with --skip-install) ---
if [[ "$SKIP_INSTALL" == "false" ]]; then
  if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "→ pip install -r requirements.txt (CPU torch) ..."
    pip install -r "$ROOT/requirements.txt" --index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -n 20
  fi
  if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
    echo "→ npm install (frontend) ..."
    (cd "$ROOT/frontend" && npm install 2>&1 | tail -n 20)
  fi
else
  echo "→ SKIP_INSTALL: skipping pip/npm install checks"
fi

# --- 3. Cleanup old processes ---
cleanup() {
  echo ""
  echo "→ Shutting down pitch demo..."
  # Kill vite/uvicorn started by this script (by log file owning pid if tracked)
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
  # Also pkill leftover by port (best-effort, not destructive if other app uses port)
  pkill -f "uvicorn.*$BACKEND_PORT" 2>/dev/null || true
  pkill -f "vite.*$FRONTEND_PORT" 2>/dev/null || true
  echo "  backend log: $BACKEND_LOG"
  echo "  frontend log: $FRONTEND_LOG"
  exit 0
}
trap cleanup INT TERM EXIT

# Kill any stale on ports before start
pkill -f "uvicorn.*$BACKEND_PORT" 2>/dev/null || true
pkill -f "vite.*$FRONTEND_PORT" 2>/dev/null || true
sleep 1

# --- 4. Start backend ---
echo "→ Starting backend (CPU-ONLY, port $BACKEND_PORT) ..."
echo "  BASE_MODEL=$SATQUERY_BASE_MODEL"
echo "  ADAPTER_PATH=$SATQUERY_ADAPTER_PATH"
echo "  FORCE_CPU=$SATQUERY_FORCE_CPU"
mkdir -p /tmp/satquery_offload
nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
echo "  backend pid $BACKEND_PID → $BACKEND_LOG"

# --- 5. Wait for /health (and ideally is_real) ---
echo "→ Waiting for backend /health (max 120s, warmup may pull ~4GB on first run) ..."
for i in $(seq 1 120); do
  if curl -sf "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1; then
    HEALTH_JSON="$(curl -sf "http://localhost:$BACKEND_PORT/health" 2>/dev/null || echo "{}")"
    # Try to parse is_real with jq or python fallback
    IS_REAL=""
    if command -v jq >/dev/null 2>&1; then
      IS_REAL="$(echo "$HEALTH_JSON" | jq -r '.specialists.registry["vqa (real)"].is_real // empty' 2>/dev/null || true)"
      COMPUTE="$(echo "$HEALTH_JSON" | jq -r '.compute // empty' 2>/dev/null || true)"
    else
      IS_REAL="$(python3 -c "import json,sys; d=json.load(open('/dev/stdin')); print(d.get('specialists',{}).get('registry',{}).get('vqa (real)',{}).get('is_real',''))" <<< "$HEALTH_JSON" 2>/dev/null || true)"
      COMPUTE="$(python3 -c "import json,sys; d=json.load(open('/dev/stdin')); print(d.get('compute',''))" <<< "$HEALTH_JSON" 2>/dev/null || true)"
    fi
    if [[ "$IS_REAL" == "true" ]]; then
      echo "  ✓ backend ready — vqa (real) is_real=true compute=${COMPUTE:-unknown} (${i}s)"
      break
    fi
    # If still warming, show degraded but reachable
    if [[ $i -eq 10 ]]; then
      echo "  … backend reachable but vqa still loading (is_real=${IS_REAL:-unknown}, compute=${COMPUTE:-unknown}) — tail $BACKEND_LOG"
      tail -n 8 "$BACKEND_LOG" 2>/dev/null | sed 's/^/    /' || true
    fi
    if [[ $i -eq 120 ]]; then
      echo "  ⚠ backend reachable but vqa not yet REAL after 120s — check $BACKEND_LOG"
      if [[ -f "$BACKEND_LOG" ]]; then
        echo "  last 20 lines of backend log:"
        tail -n 20 "$BACKEND_LOG" | sed 's/^/    /'
      fi
      echo "  Continuing anyway (demo will show DEGRADED/STUB if model failed — check ADAPTER_PATH/HF_TOKEN)"
      break
    fi
  else
    if [[ $((i % 10)) -eq 1 ]]; then
      echo "  … waiting for backend (${i}s) — tail $BACKEND_LOG"
    fi
  fi
  sleep 1
done

curl -sf "http://localhost:$BACKEND_PORT/health" >/dev/null && echo "  health: http://localhost:$BACKEND_PORT/health" || echo "  ⚠ health not reachable"
curl -sf "http://localhost:$BACKEND_PORT/api/health" >/dev/null && echo "  health: http://localhost:$BACKEND_PORT/api/health" || true

# --- 6. Start frontend ---
echo "→ Starting frontend (port $FRONTEND_PORT) ..."
nohup npm --prefix "$ROOT/frontend" run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT" > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
echo "  frontend pid $FRONTEND_PID → $FRONTEND_LOG"

echo "→ Waiting for frontend (max 30s) ..."
for i in $(seq 1 30); do
  if curl -sf "http://localhost:$FRONTEND_PORT/" >/dev/null 2>&1; then
    echo "  ✓ frontend ready — http://localhost:$FRONTEND_PORT"
    break
  fi
  if [[ $i -eq 30 ]]; then
    echo "  ⚠ frontend not yet reachable after 30s — tail $FRONTEND_LOG"
    tail -n 20 "$FRONTEND_LOG" 2>/dev/null | sed 's/^/    /' || true
  fi
  sleep 1
done

# --- 7. Open browser ---
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  Pitch demo ready"
echo "  Frontend: http://localhost:$FRONTEND_PORT"
echo "  Backend:  http://localhost:$BACKEND_PORT (docs at /docs)"
echo "  Health:   http://localhost:$BACKEND_PORT/health"
echo "  Logs:     tail -f $BACKEND_LOG  |  tail -f $FRONTEND_LOG"
echo "════════════════════════════════════════════════════════════"
echo ""
if [[ "$NO_BROWSER" == "false" ]] && command -v xdg-open >/dev/null 2>&1; then
  echo "→ Opening browser ..."
  xdg-open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true
  # Also open backend docs in second tab if possible
  sleep 1
  xdg-open "http://localhost:$BACKEND_PORT/docs" >/dev/null 2>&1 || true
elif [[ "$NO_BROWSER" == "false" ]] && command -v open >/dev/null 2>&1; then
  open "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1 || true
else
  echo "  (no xdg-open/open — open http://localhost:$FRONTEND_PORT manually)"
fi

echo ""
echo "Press Ctrl+C to stop both servers."
# Keep script alive, show logs interleaved? Just wait.
wait
