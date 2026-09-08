#!/usr/bin/env bash
set -u

if [[ $# -ne 1 ]]; then
  printf 'usage: %s P00|P10|P01|P11\n' "$0" >&2
  exit 2
fi
precision=$1
case "$precision" in
  P00) port=19500 ;;
  P10) port=19510 ;;
  P01) port=19501 ;;
  P11) port=19511 ;;
  *) printf 'unknown precision: %s\n' "$precision" >&2; exit 2 ;;
esac

workspace=/root/autodl-tmp/qhist-e0-v13
run="$workspace/runs/QHIST-E0-v13-traj-$precision-r1"
log="$workspace/logs/v13-trajectory-$precision.log"
exit_file="$workspace/logs/v13-trajectory-$precision.exit"
endpoint="http://127.0.0.1:$port"
if [[ -e "$run" || -e "$exit_file" ]]; then
  printf 'refusing to overwrite audited output: %s\n' "$run" >&2
  exit 3
fi
mkdir -p "$run/server" "$run/driver" "$workspace/logs"
cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0

toolsandbox-env/bin/python code/qhist_verify_v13_lock.py \
  --lock protocol/qhist-e0-v13-lock.json \
  --code-root code \
  --runs-root runs \
  --protocol-root protocol >>"$log" 2>&1
verify_status=$?
if [[ $verify_status -ne 0 ]]; then
  printf '%s\n' "$verify_status" >"$exit_file"
  exit "$verify_status"
fi

precision-env/bin/python code/qhist_model_server_v13.py \
  --precision "$precision" \
  --model-path models-Qwen3-32B \
  --model-revision 9216db5781bf21249d130ec9da846c4624c16137 \
  --host 127.0.0.1 \
  --port "$port" \
  --seed 20260904 \
  --output "$run/server" >"$run/server.stdout.log" 2>"$run/server.stderr.log" &
server_pid=$!

cleanup() {
  precision-env/bin/python code/qhist_server_control.py shutdown \
    --endpoint "$endpoint" --precision "$precision" >/dev/null 2>&1 || true
  if kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

precision-env/bin/python code/qhist_server_control.py wait \
  --endpoint "$endpoint" \
  --precision "$precision" \
  --timeout 180 \
  --output "$run/server-health.json" >>"$log" 2>&1
wait_status=$?
if [[ $wait_status -ne 0 ]]; then
  printf '%s\n' "$wait_status" >"$exit_file"
  exit "$wait_status"
fi

toolsandbox-env/bin/python code/qhist_trajectory_batch_v13.py \
  --precision "$precision" \
  --assets runs/QHIST-E0-v13-assets-r1 \
  --rendered runs/QHIST-E0-v13-rendered-r1 \
  --model-endpoint "$endpoint" \
  --toolsandbox-source toolsandbox-source \
  --toolsandbox-site-packages toolsandbox-env/lib/python3.11/site-packages \
  --seed 20260904 \
  --max-new-tokens 256 \
  --output "$run/driver" >>"$log" 2>&1
driver_status=$?

precision-env/bin/python code/qhist_server_control.py shutdown \
  --endpoint "$endpoint" --precision "$precision" >>"$log" 2>&1 || true
wait "$server_pid"
server_status=$?
trap - EXIT

precision-env/bin/python code/qhist_combine_trajectory_batch_v13.py \
  --precision "$precision" \
  --server "$run/server/summary.json" \
  --driver "$run/driver/summary.json" \
  --output "$run/summary.json" >>"$log" 2>&1
combine_status=$?

status=0
if [[ $driver_status -ne 0 || $server_status -ne 0 || $combine_status -ne 0 ]]; then
  status=1
fi
printf '%s\n' "$status" >"$exit_file"
exit "$status"
