#!/usr/bin/env bash
set -euo pipefail

ROOT=/root/autodl-tmp/qhist-e0-v7
RUN="$ROOT/development/model-server-draft-1"
PYTHON="$ROOT/precision-env/bin/python"
PORT=18087

test ! -e "$RUN"
mkdir -p "$RUN/server"

"$PYTHON" "$ROOT/code/qhist_model_server.py" \
  --precision P00 \
  --model-path "$ROOT/models-Qwen3-32B" \
  --model-revision 9216db5781bf21249d130ec9da846c4624c16137 \
  --port "$PORT" \
  --seed 20260903 \
  --output "$RUN/server" \
  > "$RUN/server.stdout.log" 2> "$RUN/server.stderr.log" &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

"$PYTHON" "$ROOT/code/qhist_model_server_smoke.py" \
  --endpoint "http://127.0.0.1:$PORT" \
  --output "$RUN/client-result.json" \
  > "$RUN/client.stdout.log" 2> "$RUN/client.stderr.log"
wait "$SERVER_PID"
trap - EXIT
cat "$RUN/client.stdout.log"
