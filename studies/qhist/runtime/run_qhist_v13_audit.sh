#!/usr/bin/env bash
set -u

workspace="${QHIST_WORKSPACE:?Set QHIST_WORKSPACE to the deployed protocol workspace}"
qualification="$workspace/runs/QHIST-E0-v13-qualification-audit-r1/report.json"
audit="$workspace/runs/QHIST-E0-v13-machine-audit-r1/report.json"
log="$workspace/logs/v13-final-audit-r1.log"
exit_file="$workspace/logs/v13-final-audit-r1.exit"
if [[ -e "${qualification%/*}" || -e "${audit%/*}" || -e "$exit_file" ]]; then
  printf 'refusing to overwrite audited output\n' >&2
  exit 3
fi
mkdir -p "${qualification%/*}" "${audit%/*}" "$workspace/logs"
cd "$workspace" || exit 4

toolsandbox-env/bin/python code/qhist_verify_v13_lock.py \
  --lock protocol/qhist-e0-v13-lock.json \
  --code-root code \
  --runs-root runs \
  --protocol-root protocol >"$log" 2>&1
status=$?

if [[ $status -eq 0 ]]; then
  precision-env/bin/python code/qhist_audit_qualification.py \
    --runs-root runs \
    --run-prefix QHIST-E0-v13-qual \
    --protocol-version 13 \
    --output "$qualification" >>"$log" 2>&1 || status=1
fi

if [[ $status -eq 0 ]]; then
  toolsandbox-env/bin/python code/qhist_audit_e0_v13.py \
    --runs-root runs \
    --run-prefix QHIST-E0-v13-traj \
    --assets runs/QHIST-E0-v13-assets-r1 \
    --rendered runs/QHIST-E0-v13-rendered-r1 \
    --preflight runs/QHIST-E0-v13-preflight-r1/report.json \
    --qualification-audit "$qualification" \
    --toolsandbox-source toolsandbox-source \
    --incremental-cost-usd 0 \
    --stage-gpu-cap-hours 8 \
    --minimum-free-disk-gb 50 \
    --output "$audit" >>"$log" 2>&1 || status=1
fi

printf '%s\n' "$status" >"$exit_file"
exit "$status"
