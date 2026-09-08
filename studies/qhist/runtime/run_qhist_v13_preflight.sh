#!/usr/bin/env bash
set -u

workspace="${QHIST_WORKSPACE:?Set QHIST_WORKSPACE to the deployed protocol workspace}"
output="$workspace/runs/QHIST-E0-v13-preflight-r1/report.json"
log="$workspace/logs/v13-preflight-r1.log"
exit_file="$workspace/logs/v13-preflight-r1.exit"
if [[ -e "${output%/*}" || -e "$exit_file" ]]; then
  printf 'refusing to overwrite audited preflight: %s\n' "$output" >&2
  exit 3
fi
mkdir -p "${output%/*}" "$workspace/logs"
cd "$workspace" || exit 4
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false

toolsandbox-env/bin/python code/qhist_preflight_audit_v13.py \
  --assets runs/QHIST-E0-v13-assets-r1 \
  --rendered runs/QHIST-E0-v13-rendered-r1 \
  --toolsandbox-gate runs/QHIST-E0-v13-toolsandbox-gate-r1/report.json \
  --driver-gate runs/QHIST-E0-v13-driver-gate-r1/report.json \
  --id-gate runs/QHIST-E0-v13-id-gate-r1/report.json \
  --code-root code \
  --output "$output" >"$log" 2>&1
status=$?
printf '%s\n' "$status" >"$exit_file"
exit "$status"
