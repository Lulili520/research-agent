#!/usr/bin/env bash
set -u

workspace="${QHIST_WORKSPACE:?Set QHIST_WORKSPACE to the deployed protocol workspace}"
output="$workspace/runs/QHIST-E0-v12-preflight-r1/report.json"
log="$workspace/logs/v12-preflight-r1.log"
exit_file="$workspace/logs/v12-preflight-r1.exit"
if [[ -e "${output%/*}" || -e "$exit_file" ]]; then
  printf 'refusing to overwrite audited preflight: %s\n' "$output" >&2
  exit 3
fi
mkdir -p "${output%/*}" "$workspace/logs"
cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false

toolsandbox-env/bin/python code/qhist_preflight_audit_v12.py \
  --assets runs/QHIST-E0-v12-assets-r3 \
  --rendered runs/QHIST-E0-v12-rendered-r2 \
  --toolsandbox-gate runs/QHIST-E0-v12-toolsandbox-gate-r4/report.json \
  --driver-gate runs/QHIST-E0-v12-driver-gate-r4/report.json \
  --id-gate runs/QHIST-E0-v12-id-gate-r3/report.json \
  --code-root code \
  --output "$output" >"$log" 2>&1
status=$?
printf '%s\n' "$status" >"$exit_file"
exit "$status"
