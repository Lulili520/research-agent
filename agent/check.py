#!/usr/bin/env python3
"""Run the repository checks from any working directory; extra arguments go to pytest."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def main() -> int:
    agent = Path(__file__).resolve().parent
    if importlib.util.find_spec('pytest') is None:
        print(f'Install test dependencies first: {sys.executable} -m pip install -r {agent / "tests" / "requirements.txt"}', file=sys.stderr)
        return 2
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    return subprocess.call(
        [sys.executable, '-m', 'pytest', '-c', str(agent / 'tests' / 'pytest.ini'), '-q', *sys.argv[1:]],
        cwd=agent,
        env=environment,
    )


if __name__ == '__main__':
    raise SystemExit(main())
