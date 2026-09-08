#!/usr/bin/env bash
set -u

workspace="${QHIST_WORKSPACE:?Set QHIST_WORKSPACE to the deployed protocol workspace}"
assets="$workspace/runs/QHIST-E0-v11-assets-r5"
rendered="$workspace/runs/QHIST-E0-v11-rendered-r5"
toolsandbox_gate="$workspace/runs/QHIST-E0-v11-toolsandbox-gate-r5/report.json"
driver_gate="$workspace/runs/QHIST-E0-v11-driver-gate-r9/report.json"
id_gate="$workspace/runs/QHIST-E0-v11-id-gate-r3/report.json"
log="$workspace/logs/v11-preflight-r5.log"
exit_file="$workspace/logs/v11-preflight-r5.exit"

for target in \
  "$assets" \
  "$rendered" \
  "${toolsandbox_gate%/*}" \
  "${driver_gate%/*}" \
  "${id_gate%/*}" \
  "$exit_file"; do
  if [[ -e "$target" ]]; then
    printf 'refusing to overwrite audited output: %s\n' "$target" >&2
    exit 3
  fi
done
mkdir -p \
  "$workspace/logs" \
  "${toolsandbox_gate%/*}" \
  "${driver_gate%/*}" \
  "${id_gate%/*}"
cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export CUDA_VISIBLE_DEVICES=0

status=0
toolsandbox-env/bin/python code/qhist_build_e0_assets_v11.py \
  --output "$assets" \
  --toolsandbox-source toolsandbox-source \
  --seed 20260904 >>"$log" 2>&1 || status=1

if [[ $status -eq 0 ]]; then
  precision-env/bin/python code/qhist_render_stimuli_v11.py \
    --assets "$assets" \
    --model-path models-Qwen3-32B \
    --output "$rendered" \
    --seed 20260904 >>"$log" 2>&1 || status=1
fi

if [[ $status -eq 0 ]]; then
  toolsandbox-env/bin/python code/qhist_toolsandbox_gate_v11.py \
    --assets "$assets" \
    --toolsandbox-source toolsandbox-source \
    --toolsandbox-site-packages toolsandbox-env/lib/python3.11/site-packages \
    --output "$toolsandbox_gate" >>"$log" 2>&1 || status=1
fi

if [[ $status -eq 0 ]]; then
  toolsandbox-env/bin/python code/qhist_driver_integration_gate_v11.py \
    --assets "$assets" \
    --rendered "$rendered" \
    --toolsandbox-source toolsandbox-source \
    --toolsandbox-site-packages toolsandbox-env/lib/python3.11/site-packages \
    --output "$driver_gate" >>"$log" 2>&1 || status=1
fi

if [[ $status -eq 0 ]]; then
  toolsandbox-env/bin/python code/qhist_deterministic_id_gate_v11.py \
    --assets "$assets" \
    --rendered "$rendered" \
    --toolsandbox-source toolsandbox-source \
    --toolsandbox-site-packages toolsandbox-env/lib/python3.11/site-packages \
    --output "$id_gate" >>"$log" 2>&1 || status=1
fi

printf '%s\n' "$status" >"$exit_file"
exit "$status"
