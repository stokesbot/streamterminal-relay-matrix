#!/bin/bash
set -euo pipefail

# StreamTerminal Relay Matrix - Start Script
# Starts both backend (FastAPI) and frontend (Next.js) development servers

# Allow overrides via environment variables
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
WEB_HOST="${WEB_HOST:-0.0.0.0}"
WEB_PORT="${WEB_PORT:-3000}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="${SCRIPT_DIR}/apps/api"
WEB_DIR="${SCRIPT_DIR}/apps/web"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

cleanup_pids=()

cleanup() {
    log_warn "Shutting down services..."
    for pid in "${cleanup_pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    log_ok "All services stopped"
}
trap cleanup INT TERM EXIT

log_info "Starting StreamTerminal Relay Matrix"
log_info "API:  http://${API_HOST}:${API_PORT}"
log_info "Web:  http://${WEB_HOST}:${WEB_PORT}"
echo ""

# --- Backend ---
if [[ ! -d "${API_DIR}/.venv" ]]; then
    log_warn "Python venv not found in ${API_DIR}"
    log_info "Run: cd apps/api && uv sync"
    exit 1
fi

log_info "Starting FastAPI backend..."
(
    cd "${API_DIR}"
    if [[ ! -f ".env" ]]; then
        cp .env.example .env
        log_warn "Created .env from example — review and edit if needed"
    fi
    source .venv/bin/activate
    uv run uvicorn app.main:app --host "${API_HOST}" --port "${API_PORT}" &
)
cleanup_pids+=("$!")
sleep 2

# Quick backend health check
if curl -sf "http://${API_HOST}:${API_PORT}/api/health" >/dev/null 2>&1; then
    log_ok "Backend responding on port ${API_PORT}"
else
    log_warn "Backend not responding yet — may still be starting"
fi

# --- Frontend ---
if [[ ! -d "${WEB_DIR}/node_modules" ]]; then
    log_warn "node_modules not found in ${WEB_DIR}"
    log_info "Run: cd apps/web && npm install"
    exit 1
fi

log_info "Starting Next.js frontend..."
(
    cd "${WEB_DIR}"
    if [[ ! -f ".env.local" ]]; then
        cp .env.example .env.local
        log_warn "Created .env.local from example — review and edit if needed"
    fi
    npm run dev -- --hostname "${WEB_HOST}" --port "${WEB_PORT}" &
)
cleanup_pids+=("$!")
sleep 3

# Quick frontend check
if curl -sf -o /dev/null "http://${WEB_HOST}:${WEB_PORT}/"; then
    log_ok "Frontend responding on port ${WEB_PORT}"
else
    log_warn "Frontend not responding yet — may still be compiling"
fi

echo ""
log_ok "Both services started!"
log_info "Web UI: http://${WEB_HOST}:${WEB_PORT}"
log_info "API:    http://${API_HOST}:${API_PORT}/api/health"
echo ""
log_info "Press Ctrl+C to stop all services"

# Wait for all background jobs
wait
