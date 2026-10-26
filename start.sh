#!/bin/bash
# Local development only — for production use Docker instead:
#   cp .env.example .env   # then edit .env
#   docker compose up -d
cd "$(dirname "$0")"
[ -f ".env" ] && set -a && source .env && set +a

# --- single-instance guard ---------------------------------------------------
# 历史故障：8770 曾被非 launchd 启动的实例占用，launchd 每 5-10 秒拉起一次新进程、
# 绑定失败、退出、再拉起，形成崩溃循环（日志里累计 2 万次 address already in use）。
# launchd 拉起时回收端口；手动拉起时拒绝启动，避免和 launchd 互杀。
PORT="${PORT:-8770}"
occupied=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)
if [ -n "$occupied" ]; then
  if [ "$PPID" -eq 1 ] || [ "${XPC_SERVICE_NAME:-}" = "com.han.redsignal" ]; then
    echo "[start.sh] port $PORT held by stale pid(s) $occupied, reclaiming for launchd" >&2
    kill -TERM $occupied 2>/dev/null
    for _ in $(seq 1 20); do
      lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1 || break
      sleep 0.5
    done
    remaining=$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null)
    if [ -n "$remaining" ]; then
      kill -KILL $remaining 2>/dev/null
      sleep 1
    fi
  else
    echo "[start.sh] port $PORT is already served by pid(s) $occupied; refusing duplicate manual start." >&2
    lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >&2
    echo "[start.sh] managed by launchd; use: launchctl kickstart -k gui/$(id -u)/com.han.redsignal" >&2
    exit 0
  fi
fi

[ -d ".venv" ] || python3 -m venv .venv
source .venv/bin/activate
if [ ! -f .venv/.requirements-installed ] || [ requirements.txt -nt .venv/.requirements-installed ]; then
  pip install -q -r requirements.txt
  touch .venv/.requirements-installed
fi
RELOAD_ARGS=()
FILTERED_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--reload" ]; then
    RELOAD=1
  else
    FILTERED_ARGS+=("$arg")
  fi
done

if [ "${RELOAD:-0}" = "1" ]; then
  RELOAD_ARGS=(--reload --reload-dir . --reload-exclude "frontend" --reload-exclude "data" --reload-exclude "static" --reload-exclude "logs" --reload-exclude "*.db" --reload-exclude "*.log")
fi

exec uvicorn app:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8770}" "${RELOAD_ARGS[@]}" "${FILTERED_ARGS[@]}"
