#!/usr/bin/env bash
# Start / stop the whole thing (model server + web page) yourself. HOME / LOCALHOST USE ONLY.
#
#   scripts/poet.sh start [4b|9b|gemma] [--lan]   load the model (default 4b), then start the page
#   scripts/poet.sh stop                          stop the page and shut vLLM down (frees the GPU)
#   scripts/poet.sh status                        what is running
#   scripts/poet.sh ui-start [--lan] | ui-stop    the page only
#
# The page listens on 127.0.0.1 (this machine only). --lan binds it to this machine's home-network
# address instead (refused unless that address is private) so phones/laptops at home can use it.
# The model-switcher section of the page is enabled here; do not use this script to host online.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv/bin/python"
RUN="$ROOT/run"; PIDFILE="$RUN/webui.pid"; LOGFILE="$RUN/webui.log"; ADDRFILE="$RUN/webui.addr"
PORT="${VIETPOET_PORT:-7860}"
mkdir -p "$RUN"

ui_pids() { pgrep -f "python.* -m app[.]webui" || true; }

lan_address() {
  "$PY" - <<'PYEOF'
import socket, sys
sys.path.insert(0, ".")
from app.serving import is_home_request
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    s.connect(("10.255.255.255", 1))          # private address: nothing is sent, it only picks the LAN interface
    ip = s.getsockname()[0]
except OSError:
    ip = ""
print(ip if ip and is_home_request(ip, {}) else "")
PYEOF
}

ui_start() {
  local host="127.0.0.1"
  if [ "${1:-}" = "--lan" ]; then
    host="$(lan_address)"
    if [ -z "$host" ]; then echo "error: no private home-network address found; not starting on the LAN" >&2; return 1; fi
  fi
  if [ -n "$(ui_pids)" ]; then echo "page already running (pid $(ui_pids | tr '\n' ' '))"; return 0; fi
  VIETPOET_ALLOW_SWITCH="${VIETPOET_ALLOW_SWITCH:-1}" VIETPOET_HOST="$host" VIETPOET_PORT="$PORT" \
    setsid nohup "$PY" -m app.webui > "$LOGFILE" 2>&1 < /dev/null &
  echo $! > "$PIDFILE"; echo "http://$host:$PORT" > "$ADDRFILE"
  for _ in $(seq 1 40); do
    if curl -s -m 2 -o /dev/null "http://$host:$PORT/"; then echo "page: http://$host:$PORT"; return 0; fi
    sleep 1
  done
  echo "error: the page did not start; see $LOGFILE" >&2; return 1
}

ui_stop() {
  local pids; pids="$(ui_pids)"
  if [ -z "$pids" ]; then echo "page not running"; rm -f "$PIDFILE" "$ADDRFILE"; return 0; fi
  kill $pids 2>/dev/null
  for _ in $(seq 1 10); do [ -z "$(ui_pids)" ] && break; sleep 1; done
  [ -n "$(ui_pids)" ] && kill -9 $(ui_pids) 2>/dev/null
  rm -f "$PIDFILE" "$ADDRFILE"; echo "page stopped"
}

status() {
  echo "model: $("$PY" -m app.serving status)"
  if [ -n "$(ui_pids)" ]; then
    local addr; addr="$(cat "$ADDRFILE" 2>/dev/null || echo "http://127.0.0.1:$PORT")"
    echo "page:  running (pid $(ui_pids | tr '\n' ' ')) $addr"
  else
    echo "page:  not running"
  fi
}

case "${1:-status}" in
  start)
    model="4b"; lan=""
    for a in "${@:2}"; do case "$a" in --lan) lan="--lan" ;; *) model="$a" ;; esac; done
    "$ROOT/scripts/switch_model.sh" "$model" || exit 1
    ui_start $lan
    ;;
  stop)      ui_stop; "$ROOT/scripts/switch_model.sh" stop ;;
  status)    status ;;
  ui-start)  ui_start "${2:-}" ;;
  ui-stop)   ui_stop ;;
  *)         sed -n '2,12p' "$0"; exit 2 ;;
esac
