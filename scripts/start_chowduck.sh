#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TUNNEL_DIR="/Users/lzz/Desktop/tunnel"
TUNNEL_CONFIG="${TUNNEL_DIR}/config.yml"
TUNNEL_NAME="chowduck-tunnel"

WEBSITE_DIR="${PROJECT_ROOT}/website"
WEB_DIR="${PROJECT_ROOT}/web"
BACKEND_DIR="${PROJECT_ROOT}/backend"

WEBSITE_PORT="4180"
WEB_PORT="5173"
BACKEND_PORT="8765"

pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
  done
}
trap cleanup EXIT INT TERM

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

port_in_use() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

start_bg() {
  local name="$1"
  shift
  echo "[start] ${name}"
  ("$@") &
  local pid=$!
  pids+=("${pid}")
  echo "[pid] ${name}: ${pid}"
}

require_cmd node
require_cmd npm
require_cmd python3
require_cmd cloudflared

if [ ! -f "${TUNNEL_CONFIG}" ]; then
  echo "Tunnel config not found: ${TUNNEL_CONFIG}" >&2
  exit 1
fi

if port_in_use "${WEBSITE_PORT}"; then
  echo "Port ${WEBSITE_PORT} already in use (website)." >&2
  exit 1
fi
if port_in_use "${WEB_PORT}"; then
  echo "Port ${WEB_PORT} already in use (web)." >&2
  exit 1
fi
if port_in_use "${BACKEND_PORT}"; then
  echo "Port ${BACKEND_PORT} already in use (backend)." >&2
  exit 1
fi

start_bg "backend" bash -lc "cd '${BACKEND_DIR}' && python3 main.py"
start_bg "website" bash -lc "cd '${WEBSITE_DIR}' && npm run dev -- --port ${WEBSITE_PORT} --host 127.0.0.1"
start_bg "web" bash -lc "cd '${WEB_DIR}' && npm run dev -- --port ${WEB_PORT} --host 127.0.0.1"

echo "[start] cloudflared tunnel (${TUNNEL_NAME})"
exec bash -lc "cd '${TUNNEL_DIR}' && cloudflared tunnel --config '${TUNNEL_CONFIG}' run '${TUNNEL_NAME}'"
