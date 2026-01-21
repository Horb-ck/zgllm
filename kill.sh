#!/usr/bin/env bash
set -euo pipefail

PORTS=(5002 7000 5001)

get_pids() {
  local pids=()
  for port in "${PORTS[@]}"; do
    while IFS= read -r pid; do
      [[ -n "$pid" ]] && pids+=("$pid")
    done < <(lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  done

  if ((${#pids[@]})); then
    printf "%s\n" "${pids[@]}" | sort -u
  fi
}

PIDS="$(get_pids || true)"

if [[ -z "${PIDS:-}" ]]; then
  echo "No LISTEN processes found on ports: ${PORTS[*]}"
  exit 0
fi

echo "Will kill these PIDs:"
echo "$PIDS"

echo "==> SIGTERM..."
echo "$PIDS" | xargs -r kill -TERM
sleep 2

ALIVE=$(echo "$PIDS" | xargs -r -n1 sh -c 'kill -0 "$1" 2>/dev/null && echo "$1"' sh || true)
if [[ -n "${ALIVE:-}" ]]; then
  echo "==> Still alive, SIGKILL:"
  echo "$ALIVE" | xargs -r kill -KILL
fi

echo "==> Current listeners:"
ss -lntp | egrep ':5002|:7000|:5001' || echo "Ports 5002/7000/5001 are free."
