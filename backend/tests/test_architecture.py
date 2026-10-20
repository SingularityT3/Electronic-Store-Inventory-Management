"""Fails if module boundaries (docs/architecture.md) are violated."""

import subprocess
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_module_boundaries_respected():
    result = subprocess.run(
        ["lint-imports"], cwd=BACKEND_DIR, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
