#!/usr/bin/env bash
set -euo pipefail

workspace=/root/autodl-tmp/qhist-e0-v6
base_python=/root/autodl-tmp/Research-Agent/.venvs/vllm028/bin/python
environment="$workspace/quanto-env"
manifest_dir="$workspace/manifests/quanto-env"

if [[ -e "$environment" || -e "$manifest_dir" ]]; then
  printf 'refusing to overwrite existing environment or manifest\n' >&2
  exit 3
fi

mkdir -p "$manifest_dir/wheels"
"$base_python" -m venv --system-site-packages "$environment"
"$environment/bin/pip" install --no-deps 'optimum-quanto==0.2.7'
"$environment/bin/pip" download --no-deps --dest "$manifest_dir/wheels" 'optimum-quanto==0.2.7'
"$environment/bin/pip" freeze | LC_ALL=C sort >"$manifest_dir/pip-freeze.txt"
"$environment/bin/pip" show optimum-quanto >"$manifest_dir/optimum-quanto.txt"
sha256sum "$manifest_dir"/wheels/* >"$manifest_dir/wheel-sha256.txt"
"$environment/bin/python" - <<'PY' >"$manifest_dir/import-check.json"
import importlib.metadata
import json
import torch
import transformers

print(json.dumps({
    "optimum_quanto": importlib.metadata.version("optimum-quanto"),
    "torch": torch.__version__,
    "transformers": transformers.__version__,
}, sort_keys=True))
PY
sha256sum "$manifest_dir"/* >"$manifest_dir/files-sha256.txt"
