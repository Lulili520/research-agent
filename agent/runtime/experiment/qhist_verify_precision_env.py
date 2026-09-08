#!/usr/bin/env python3
"""只读核验 Q-HIST v8 复用的冻结精度环境。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path


EXPECTED = {
    "torch": "2.13.0",
    "transformers": "5.16.1",
    "optimum-quanto": "0.2.7",
    "hqq": "0.2.8.post1",
    "accelerate": "1.12.0",
    "termcolor": "3.3.0",
    "numpy": "2.3.5",
}
EXPECTED_CANONICAL_FREEZE_SHA256 = "498e18cc23711fa9bcb518894e5b15939037e04b204dee9ef19056e4b96a9ff1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"输出已存在，禁止覆盖：{args.output}")
    freeze = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    freeze_sha = hashlib.sha256(freeze.encode("utf-8")).hexdigest()
    canonical_freeze = (
        "\n".join(sorted(freeze.splitlines(), key=str.casefold)) + "\n"
    )
    canonical_freeze_sha = hashlib.sha256(
        canonical_freeze.encode("utf-8")
    ).hexdigest()
    pip_check = subprocess.run(
        [sys.executable, "-m", "pip", "check"],
        capture_output=True,
        text=True,
    )
    versions = {
        package: importlib.metadata.version(package) for package in EXPECTED
    }
    from hqq.core.quantize import HQQLinear
    from optimum.quanto import QModuleMixin
    from transformers import AutoTokenizer, QuantoConfig
    from transformers.cache_utils import HQQQuantizedLayer, QuantizedCache

    imports = {
        "AutoTokenizer": AutoTokenizer.__module__,
        "QuantoConfig": QuantoConfig.__module__,
        "QModuleMixin": QModuleMixin.__module__,
        "HQQLinear": HQQLinear.__module__,
        "HQQQuantizedLayer": HQQQuantizedLayer.__module__,
        "QuantizedCache": QuantizedCache.__module__,
    }
    checks = {
        "versions_match": all(
            versions[name].split("+")[0] == expected
            for name, expected in EXPECTED.items()
        ),
        "pip_freeze_set_matches": canonical_freeze_sha
        == EXPECTED_CANONICAL_FREEZE_SHA256,
        "pip_check_clean": pip_check.returncode == 0,
        "imports_complete": len(imports) == 6,
        "toolsandbox_not_in_precision_environment": False,
    }
    try:
        importlib.metadata.version("tool-sandbox")
        checks["toolsandbox_not_in_precision_environment"] = False
    except importlib.metadata.PackageNotFoundError:
        checks["toolsandbox_not_in_precision_environment"] = True
    report = {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": 8,
        "python_executable": sys.executable,
        "versions": versions,
        "imports": imports,
        "pip_freeze_sha256": freeze_sha,
        "pip_freeze_canonical_sha256": canonical_freeze_sha,
        "pip_freeze_entries": len(freeze.splitlines()),
        "pip_check_stdout": pip_check.stdout,
        "pip_check_stderr": pip_check.stderr,
        "checks": checks,
        "passed": all(checks.values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
