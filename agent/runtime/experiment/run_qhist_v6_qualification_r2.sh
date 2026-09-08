#!/usr/bin/env bash
set -u

if [[ $# -ne 1 ]]; then
  printf 'usage: %s P00|P10|P01|P11|K16-shadow\n' "$0" >&2
  exit 2
fi

precision=$1
case "$precision" in
  P00|P10|P01|P11|K16-shadow) ;;
  *)
    printf 'unknown precision: %s\n' "$precision" >&2
    exit 2
    ;;
esac

workspace=/root/autodl-tmp/qhist-e0-v6
output="$workspace/runs/qualification-r2/$precision"
log="$workspace/logs/qual-r2-$precision.log"
exit_file="$workspace/logs/qual-r2-$precision.exit"

if [[ -e "$output" || -e "$exit_file" ]]; then
  printf 'refusing to overwrite existing audited output: %s\n' "$output" >&2
  exit 3
fi

cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0

quanto-env/bin/python code/qhist_precision_qualification.py \
  --precision "$precision" \
  --model-path models-Qwen3-32B \
  --model-id Qwen/Qwen3-32B \
  --model-revision 9216db5781bf21249d130ec9da846c4624c16137 \
  --seed 20260903 \
  --max-new-tokens 128 \
  --output "runs/qualification-r2/$precision" >"$log" 2>&1
status=$?
printf '%s\n' "$status" >"$exit_file"
exit "$status"
