#!/usr/bin/env bash
set -u

workspace="${QHIST_WORKSPACE:?Set QHIST_WORKSPACE to the deployed protocol workspace}"
run="$workspace/runs/ipc-smoke-r1"
port=18088
if [[ -e "$run" ]]; then
  printf 'refusing to overwrite audited output: %s\n' "$run" >&2
  exit 3
fi
mkdir -p "$run/server"
cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0

precision-env/bin/python code/qhist_model_server.py \
  --precision P00 \
  --model-path models-Qwen3-32B \
  --model-revision 9216db5781bf21249d130ec9da846c4624c16137 \
  --host 127.0.0.1 \
  --port "$port" \
  --seed 20260903 \
  --output "$run/server" >"$run/server.stdout.log" 2>"$run/server.stderr.log" &
server_pid=$!

cleanup() {
  if kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

precision-env/bin/python code/qhist_model_server_smoke.py \
  --endpoint "http://127.0.0.1:$port" \
  --output "$run/client-result.json" \
  >"$run/client.stdout.log" 2>"$run/client.stderr.log"
client_status=$?
wait "$server_pid"
server_status=$?
trap - EXIT
status=0
if [[ $client_status -ne 0 || $server_status -ne 0 ]]; then
  status=1
fi
printf '%s\n' "$status" >"$run/exit"
exit "$status"
