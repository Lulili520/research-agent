#!/usr/bin/env bash
set -euo pipefail

workspace=/root/autodl-tmp/qhist-e0-v6
environment="$workspace/quanto-env"
manifest_dir="$workspace/manifests/precision-env-r3"
hash_tmp="$workspace/manifests/.precision-env-r3-files.tmp"

if [[ ! -x "$environment/bin/python" ]]; then
  printf 'installed environment is missing: %s\n' "$environment" >&2
  exit 3
fi
if [[ -e "$manifest_dir" || -e "$hash_tmp" ]]; then
  printf 'refusing to overwrite existing audit material\n' >&2
  exit 4
fi

mkdir -p "$manifest_dir/wheels"
"$environment/bin/pip" install --no-deps 'hqq==0.2.8.post1'
"$environment/bin/pip" download --no-deps --dest "$manifest_dir/wheels" \
  'hqq==0.2.8.post1' 'optimum-quanto==0.2.7'
"$environment/bin/python" - <<'PY' >"$manifest_dir/import-check.json"
import importlib.metadata
import json
import torch
import transformers

versions = {
    "hqq": importlib.metadata.version("hqq"),
    "optimum_quanto": importlib.metadata.version("optimum-quanto"),
    "torch": torch.__version__,
    "transformers": transformers.__version__,
}
expected = {
    "hqq": "0.2.8.post1",
    "optimum_quanto": "0.2.7",
    "transformers": "5.16.1",
}
for key, value in expected.items():
    if versions[key] != value:
        raise RuntimeError({"expected": expected, "actual": versions})
print(json.dumps(versions, sort_keys=True))
PY
"$environment/bin/pip" freeze | LC_ALL=C sort >"$manifest_dir/pip-freeze.txt"
"$environment/bin/pip" show hqq optimum-quanto >"$manifest_dir/packages.txt"
sha256sum "$manifest_dir"/wheels/* >"$manifest_dir/wheel-sha256.txt"
find "$manifest_dir" -type f ! -name 'files-sha256.txt' -print0 \
  | sort -z \
  | xargs -0 sha256sum >"$hash_tmp"
mv "$hash_tmp" "$manifest_dir/files-sha256.txt"
