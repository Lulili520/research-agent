#!/usr/bin/env bash
set -u

workspace=/root/autodl-tmp/qhist-e0-v9
assets="$workspace/runs/QHIST-E0-v9-assets-r2"
rendered="$workspace/runs/QHIST-E0-v9-rendered-r2"
toolsandbox_gate="$workspace/runs/QHIST-E0-v9-toolsandbox-gate-r2/report.json"
driver_gate="$workspace/runs/QHIST-E0-v9-driver-gate-r2/report.json"
log="$workspace/logs/preflight-r2.log"
exit_file="$workspace/logs/preflight-r2.exit"

for target in "$assets" "$rendered" "${toolsandbox_gate%/*}" "${driver_gate%/*}" "$exit_file"; do
  if [[ -e "$target" ]]; then
    printf 'refusing to overwrite audited output: %s\n' "$target" >&2
    exit 3
  fi
done
mkdir -p "$workspace/logs" "${toolsandbox_gate%/*}" "${driver_gate%/*}"
cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0

status=0
toolsandbox-env/bin/python code/qhist_build_e0_assets_v9.py \
  --output "$assets" \
  --toolsandbox-source toolsandbox-source \
  --seed 20260903 >>"$log" 2>&1 || status=1

if [[ $status -eq 0 ]]; then
  precision-env/bin/python code/qhist_render_stimuli_v9.py \
    --assets "$assets" \
    --model-path models-Qwen3-32B \
    --output "$rendered" \
    --seed 20260903 >>"$log" 2>&1 || status=1
fi

if [[ $status -eq 0 ]]; then
  toolsandbox-env/bin/python code/qhist_toolsandbox_gate_v9.py \
    --assets "$assets" \
    --toolsandbox-source toolsandbox-source \
    --toolsandbox-site-packages toolsandbox-env/lib/python3.11/site-packages \
    --output "$toolsandbox_gate" >>"$log" 2>&1 || status=1
fi

if [[ $status -eq 0 ]]; then
  toolsandbox-env/bin/python code/qhist_driver_integration_gate_v9.py \
    --assets "$assets" \
    --rendered "$rendered" \
    --toolsandbox-source toolsandbox-source \
    --toolsandbox-site-packages toolsandbox-env/lib/python3.11/site-packages \
    --output "$driver_gate" >>"$log" 2>&1 || status=1
fi

printf '%s\n' "$status" >"$exit_file"
exit "$status"
