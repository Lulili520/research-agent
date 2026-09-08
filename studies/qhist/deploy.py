#!/usr/bin/env python3
"""Stage Q-HIST source without executing experiments; inspect deployment prerequisites."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

SOURCE = Path(__file__).resolve().parent / 'runtime'


def stage(workspace: Path) -> None:
    code = workspace / 'code'
    if code.exists():
        raise ValueError(f'refusing to overwrite deployed code: {code}')
    workspace.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, code, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    files = {str(p.relative_to(code)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(code.rglob('*')) if p.is_file()}
    (code / 'deployment.json').write_text(json.dumps({'files_sha256': files}, indent=2) + '\n')


def missing(workspace: Path, version: int) -> list[str]:
    required = ['code', 'toolsandbox-env/bin/python', 'precision-env/bin/python',
                'models-Qwen3-32B/config.json', f'protocol/qhist-e0-v{version}-lock.json']
    return [name for name in required if not (workspace / name).exists()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['stage', 'check'])
    parser.add_argument('workspace', type=Path)
    parser.add_argument('--version', type=int, choices=range(9, 15), default=14)
    args = parser.parse_args()
    try:
        if args.command == 'stage':
            stage(args.workspace.resolve())
            print('Source staged. Environments, model and audited protocol must be supplied separately.')
            return 0
        absent = missing(args.workspace.resolve(), args.version)
        print(json.dumps({'missing': absent, 'prerequisites_present': not absent}, indent=2))
        return int(bool(absent))
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    raise SystemExit(main())
