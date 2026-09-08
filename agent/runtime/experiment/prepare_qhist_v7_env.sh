#!/usr/bin/env bash
set -euo pipefail

workspace=/root/autodl-tmp/qhist-e0-v7
base_python=/root/autodl-tmp/Research-Agent/.venvs/vllm028/bin/python
environment="$workspace/precision-env"
manifest_dir="$workspace/manifests/precision-env-r1"
hash_tmp="$workspace/manifests/.precision-env-r1-files.tmp"

if [[ -e "$environment" || -e "$manifest_dir" || -e "$hash_tmp" ]]; then
  printf 'refusing to overwrite existing environment or audit material\n' >&2
  exit 3
fi

mkdir -p "$manifest_dir/packages"
"$base_python" -m venv --system-site-packages "$environment"
"$environment/bin/pip" install --no-deps \
  'optimum-quanto==0.2.7' \
  'hqq==0.2.8.post1' \
  'accelerate==1.12.0' \
  'termcolor==3.3.0'
"$environment/bin/pip" download --no-deps --dest "$manifest_dir/packages" \
  'optimum-quanto==0.2.7' \
  'hqq==0.2.8.post1' \
  'accelerate==1.12.0' \
  'termcolor==3.3.0'
"$environment/bin/python" - <<'PY' >"$manifest_dir/import-check.json"
import importlib.metadata
import json
import torch
import transformers
from optimum.quanto import QModuleMixin
from transformers import AutoTokenizer, QuantoConfig
from transformers.cache_utils import HQQQuantizedLayer, QuantizedCache

versions = {
    "accelerate": importlib.metadata.version("accelerate"),
    "hqq": importlib.metadata.version("hqq"),
    "optimum_quanto": importlib.metadata.version("optimum-quanto"),
    "termcolor": importlib.metadata.version("termcolor"),
    "torch": torch.__version__,
    "transformers": transformers.__version__,
}
expected = {
    "accelerate": "1.12.0",
    "hqq": "0.2.8.post1",
    "optimum_quanto": "0.2.7",
    "termcolor": "3.3.0",
    "transformers": "5.16.1",
}
for key, value in expected.items():
    if versions[key] != value:
        raise RuntimeError({"expected": expected, "actual": versions})
print(json.dumps({"versions": versions, "imports": {
    "AutoTokenizer": AutoTokenizer.__name__,
    "QuantoConfig": QuantoConfig.__name__,
    "QModuleMixin": QModuleMixin.__name__,
    "HQQQuantizedLayer": HQQQuantizedLayer.__name__,
    "QuantizedCache": QuantizedCache.__name__,
}}, sort_keys=True))
PY
"$environment/bin/pip" check >"$manifest_dir/pip-check.txt"
"$environment/bin/pip" freeze | LC_ALL=C sort >"$manifest_dir/pip-freeze.txt"
"$environment/bin/pip" show \
  optimum-quanto hqq accelerate termcolor >"$manifest_dir/packages.txt"
sha256sum "$manifest_dir"/packages/* >"$manifest_dir/package-sha256.txt"
find "$manifest_dir" -type f ! -name 'files-sha256.txt' -print0 \
  | sort -z \
  | xargs -0 sha256sum >"$hash_tmp"
mv "$hash_tmp" "$manifest_dir/files-sha256.txt"
