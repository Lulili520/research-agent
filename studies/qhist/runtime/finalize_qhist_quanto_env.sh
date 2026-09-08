#!/usr/bin/env bash
set -euo pipefail

workspace="${QHIST_WORKSPACE:?Set QHIST_WORKSPACE to the deployed protocol workspace}"
environment="$workspace/quanto-env"
manifest_dir="$workspace/manifests/quanto-env-r2"
hash_tmp="$workspace/manifests/.quanto-env-r2-files.tmp"

if [[ ! -x "$environment/bin/python" ]]; then
  printf 'installed environment is missing: %s\n' "$environment" >&2
  exit 3
fi
if [[ -e "$manifest_dir" || -e "$hash_tmp" ]]; then
  printf 'refusing to overwrite existing audit material\n' >&2
  exit 4
fi

mkdir -p "$manifest_dir/wheels"
"$environment/bin/python" - <<'PY' >"$manifest_dir/import-check.json"
import importlib.metadata
import json
import torch
import transformers

versions = {
    "optimum_quanto": importlib.metadata.version("optimum-quanto"),
    "torch": torch.__version__,
    "transformers": transformers.__version__,
}
if versions["optimum_quanto"] != "0.2.7":
    raise RuntimeError(versions)
if versions["transformers"] != "5.16.1":
    raise RuntimeError(versions)
print(json.dumps(versions, sort_keys=True))
PY
"$environment/bin/pip" download --no-deps --dest "$manifest_dir/wheels" 'optimum-quanto==0.2.7'
"$environment/bin/pip" freeze | LC_ALL=C sort >"$manifest_dir/pip-freeze.txt"
"$environment/bin/pip" show optimum-quanto >"$manifest_dir/optimum-quanto.txt"
sha256sum "$manifest_dir"/wheels/* >"$manifest_dir/wheel-sha256.txt"
find "$manifest_dir" -type f ! -name 'files-sha256.txt' -print0 \
  | sort -z \
  | xargs -0 sha256sum >"$hash_tmp"
mv "$hash_tmp" "$manifest_dir/files-sha256.txt"
