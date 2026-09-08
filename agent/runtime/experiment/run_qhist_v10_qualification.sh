#!/usr/bin/env bash
set -u

if [[ $# -ne 1 ]]; then
  printf 'usage: %s P00|P10|P01|P11|K16-shadow\n' "$0" >&2
  exit 2
fi
precision=$1
case "$precision" in
  P00|P10|P01|P11|K16-shadow) ;;
  *) printf 'unknown precision: %s\n' "$precision" >&2; exit 2 ;;
esac

workspace=/root/autodl-tmp/qhist-e0-v10
run="$workspace/runs/QHIST-E0-v10-qual-$precision-r1"
log="$workspace/logs/qual-$precision.log"
exit_file="$workspace/logs/qual-$precision.exit"
if [[ -e "$run" || -e "$exit_file" ]]; then
  printf 'refusing to overwrite audited output: %s\n' "$run" >&2
  exit 3
fi
mkdir -p "$workspace/logs"
cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0

precision-env/bin/python code/qhist_precision_qualification.py \
  --precision "$precision" \
  --model-path models-Qwen3-32B \
  --model-id Qwen/Qwen3-32B \
  --model-revision 9216db5781bf21249d130ec9da846c4624c16137 \
  --seed 20260904 \
  --max-new-tokens 128 \
  --output "$run" >"$log" 2>&1
status=$?
printf '%s\n' "$status" >"$exit_file"
exit "$status"
