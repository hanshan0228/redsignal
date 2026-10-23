#!/bin/bash
set -e
cd "/Users/han/redsignal"
if curl -fsS http://127.0.0.1:8770/api/health >/dev/null 2>&1; then
  open http://127.0.0.1:8770
  exit 0
fi
launchctl kickstart -k "gui/$(id -u)/com.han.redsignal"
for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:8770/api/health >/dev/null 2>&1; then
    open http://127.0.0.1:8770
    exit 0
  fi
  sleep 1
done
echo "RedSignal failed to start. Check logs/launchd.err.log"
exit 1
